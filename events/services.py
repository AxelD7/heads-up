from datetime import datetime, timedelta, timezone as dt_timezone
import re
import ssl
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from django.db import transaction
from django.utils import timezone

from .models import Event


def _unescape_ics_text(text):
    """
    Convert RFC 5545 escaped sequences (\\n, \\,, \\;, \\\\) back to plain text.
    """
    if not text:
        return ""

    def _replace(match):
        token = match.group(0)
        if token == "\\\\":
            return "\\"
        if token in ("\\n", "\\N"):
            return "\n"
        if token == "\\,":
            return ","
        if token == "\\;":
            return ";"
        return token

    return re.sub(r"\\[\\nN,;]", _replace, text)


def _unfold_ics_lines(ics_content):
    """
    Decode raw bytes if needed and unfold wrapped RFC 5545 lines.
    In iCalendar files, any line starting with a space or tab continues the previous line.
    """
    if isinstance(ics_content, bytes):
        ics_content = ics_content.decode("utf-8", errors="replace")

    # Join lines where a newline is followed immediately by a single space or tab
    unfolded = re.sub(r"\r?\n[ \t]", "", ics_content)
    return unfolded.splitlines()


def _parse_ics_datetime(raw_value, params):
    """
    Parse an iCalendar DTSTART or DTEND value into a timezone-aware UTC datetime.
    Supports UTC (...Z), explicit TZID (e.g. America/Detroit), floating, and all-day dates.
    Returns (datetime_utc, is_all_day).
    """
    value = raw_value.strip()
    is_all_day = params.get("VALUE", "").upper() == "DATE" or (
        len(value) == 8 and value.isdigit()
    )

    # 1. All-day date (YYYYMMDD) -> midnight UTC
    if is_all_day:
        parsed_date = datetime.strptime(value[:8], "%Y%m%d")
        return parsed_date.replace(tzinfo=dt_timezone.utc), True

    # 2. Explicit UTC timestamp (YYYYMMDDTHHMMSSZ)
    if value.endswith("Z"):
        parsed_dt = datetime.strptime(value, "%Y%m%dT%H%M%SZ")
        return parsed_dt.replace(tzinfo=dt_timezone.utc), False

    # 3. Local or timezone-qualified timestamp (YYYYMMDDTHHMMSS)
    parsed_dt = datetime.strptime(value[:15], "%Y%m%dT%H%M%S")
    tzid = params.get("TZID", "").strip('"').strip("'")

    if tzid:
        try:
            tz = ZoneInfo(tzid)
        except ZoneInfoNotFoundError:
            # Fall back to UTC if a non-standard timezone name is encountered
            tz = dt_timezone.utc
    else:
        tz = timezone.get_current_timezone()

    aware_dt = parsed_dt.replace(tzinfo=tz)
    return aware_dt.astimezone(dt_timezone.utc), False


def _parse_property_line(line):
    """
    Split an unfolded iCal property line (e.g., 'DTSTART;TZID=America/Detroit:20261125T090000')
    into (property_name, params_dict, property_value).
    """
    if ":" not in line:
        return None, {}, ""

    left_side, value = line.split(":", 1)
    parts = left_side.split(";")
    prop_name = parts[0].strip().upper()

    params = {}
    for param in parts[1:]:
        if "=" in param:
            k, v = param.split("=", 1)
            params[k.strip().upper()] = v.strip()

    return prop_name, params, value


def parse_ics_content(ics_content):
    """
    Read raw .ics text/bytes and parse each VEVENT into a normalized dictionary
    containing internal Event fields and its SHA-256 content hash for duplicate checking.
    """
    if not ics_content:
        return []

    lines = _unfold_ics_lines(ics_content)
    parsed_events = []

    in_vevent = False
    in_valarm = False
    current_props = {}

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue

        upper_line = line.upper()

        # Enter a VEVENT block
        if upper_line == "BEGIN:VEVENT":
            in_vevent = True
            in_valarm = False
            current_props = {}
            continue

        # Ignore nested VALARM blocks inside VEVENT so alarm descriptions don't overwrite event descriptions
        if in_vevent and upper_line == "BEGIN:VALARM":
            in_valarm = True
            continue
        if in_vevent and upper_line == "END:VALARM":
            in_valarm = False
            continue

        # Exit a VEVENT block and finalize the event record
        if upper_line == "END:VEVENT":
            in_vevent = False
            event_dict = _build_event_dict(current_props)
            if event_dict is not None:
                parsed_events.append(event_dict)
            continue

        if in_vevent and not in_valarm:
            prop_name, params, value = _parse_property_line(line)
            if prop_name in ("UID", "SUMMARY", "DTSTART", "DTEND", "LOCATION", "DESCRIPTION"):
                current_props[prop_name] = (value, params)

    return parsed_events


def _build_event_dict(props):
    """
    Convert raw extracted VEVENT properties into a clean dictionary with UTC datetimes
    and a SHA-256 content hash. Returns None if DTSTART is missing or unparseable.
    """
    if "DTSTART" not in props:
        return None

    start_raw, start_params = props["DTSTART"]
    try:
        start_time, is_all_day = _parse_ics_datetime(start_raw, start_params)
    except ValueError:
        return None

    # Parse DTEND if present; otherwise assign a valid default duration so end_time > start_time
    end_time = None
    if "DTEND" in props:
        end_raw, end_params = props["DTEND"]
        try:
            end_time, _ = _parse_ics_datetime(end_raw, end_params)
        except ValueError:
            end_time = None

    if end_time is None or end_time <= start_time:
        end_time = start_time + (timedelta(days=1) if is_all_day else timedelta(hours=1))

    # Extract and unescape text fields, respecting model max_length limits
    external_id = _unescape_ics_text(props.get("UID", ("", {}))[0]).strip()[:255]
    title = _unescape_ics_text(props.get("SUMMARY", ("", {}))[0]).strip()[:200] or "Untitled Event"
    location = _unescape_ics_text(props.get("LOCATION", ("", {}))[0]).strip()[:200]
    description = _unescape_ics_text(props.get("DESCRIPTION", ("", {}))[0]).strip()

    # Generate SHA-256 hash using the Event model's built-in hash builder
    content_hash = Event.build_hash(title, start_time, end_time, location, description)

    return {
        "external_id": external_id,
        "title": title,
        "start_time": start_time,
        "end_time": end_time,
        "location": location,
        "description": description,
        "content_hash": content_hash,
    }


def sync_ics_events(user, ics_content, feed=None, category=Event.Category.ACADEMIC):
    """
    Parse .ics content and save/update internal Event records for the given user.
    Uses external_id and SHA-256 content_hash to skip duplicates and update modified events.
    Returns a summary dictionary: {"created": int, "updated": int, "skipped": int, "events": list}.
    """
    parsed_items = parse_ics_content(ics_content)
    summary = {
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "events": [],
    }

    with transaction.atomic():
        for item in parsed_items:
            external_id = item["external_id"]
            existing_event = None

            # Match existing imported events by (feed, external_id) when available
            if external_id:
                if feed is not None:
                    existing_event = Event.objects.filter(
                        feed=feed,
                        external_id=external_id,
                    ).first()
                else:
                    existing_event = Event.objects.filter(
                        user=user,
                        feed__isnull=True,
                        external_id=external_id,
                        is_imported=True,
                    ).first()

            if existing_event is None:
                # Brand new event: insert into database
                new_event = Event.objects.create(
                    user=user,
                    feed=feed,
                    title=item["title"],
                    start_time=item["start_time"],
                    end_time=item["end_time"],
                    location=item["location"],
                    description=item["description"],
                    category=category,
                    is_imported=True,
                    external_id=external_id,
                    content_hash=item["content_hash"],
                )
                summary["created"] += 1
                summary["events"].append(new_event)
            elif existing_event.content_hash != item["content_hash"]:
                # Event details changed at the source: update fields and hash
                existing_event.title = item["title"]
                existing_event.start_time = item["start_time"]
                existing_event.end_time = item["end_time"]
                existing_event.location = item["location"]
                existing_event.description = item["description"]
                existing_event.content_hash = item["content_hash"]
                existing_event.save()
                summary["updated"] += 1
                summary["events"].append(existing_event)
            else:
                # Identical hash: skip so no duplicates are created
                summary["skipped"] += 1

        if feed is not None:
            feed.last_synced_at = timezone.now()
            feed.save(update_fields=["last_synced_at"])

    return summary


def _build_ssl_context():
    """
    Build a verified SSL context using certifi's CA bundle when installed,
    falling back to the system default CA store.
    """
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def fetch_ics_from_url(feed_url, timeout=10):
    """
    Download raw .ics content from an HTTP/HTTPS calendar feed URL.
    Raises ValueError on invalid URLs, network errors, or non-iCalendar responses.
    """
    if not feed_url or not feed_url.startswith(("http://", "https://")):
        raise ValueError("Feed URL must start with http:// or https://.")

    req = Request(
        feed_url,
        headers={"User-Agent": "HeadsUpCalendarSync/1.0"},
    )
    ssl_context = _build_ssl_context()
    try:
        with urlopen(req, timeout=timeout, context=ssl_context) as response:
            raw_bytes = response.read()
    except HTTPError as exc:
        raise ValueError(f"Calendar server returned HTTP {exc.code}.") from exc
    except URLError as exc:
        if isinstance(exc.reason, ssl.SSLCertVerificationError):
            raise ValueError(
                "SSL certificate verification failed for this URL. "
                "You can export/download the .ics file in your browser and upload it below instead."
            ) from exc
        raise ValueError(f"Could not connect to calendar feed: {exc.reason}") from exc

    text = raw_bytes.decode("utf-8", errors="replace")
    if "BEGIN:VCALENDAR" not in text.upper():
        raise ValueError("The downloaded file is not a valid iCalendar (.ics) feed.")

    return text
