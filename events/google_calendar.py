from datetime import datetime, timedelta, timezone as dt_timezone
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import Event, ExternalFeed
from .services import _build_ssl_context

GOOGLE_AUTH_BASE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_CALENDAR_EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
GOOGLE_CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar.readonly"


def build_google_auth_url(state):
    """
    Build the Google OAuth 2.0 authorization URL so users can sign in
    and grant HeadsUp read-only access to their Google Calendar.
    """
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": GOOGLE_CALENDAR_SCOPE,
        "access_type": "offline",
        "include_granted_scopes": "true",
        "prompt": "consent",
        "state": state,
    }
    return f"{GOOGLE_AUTH_BASE_URL}?{urlencode(params)}"


def exchange_code_for_tokens(code):
    """
    Exchange the temporary authorization code from Google for an OAuth access token.
    Raises ValueError if the token exchange fails.
    """
    payload = urlencode({
        "code": code,
        "client_id": settings.GOOGLE_CLIENT_ID,
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "grant_type": "authorization_code",
    }).encode("utf-8")

    req = Request(
        GOOGLE_TOKEN_URL,
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )

    try:
        with urlopen(req, timeout=10, context=_build_ssl_context()) as response:
            data = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise ValueError(f"Google token exchange failed (HTTP {exc.code}): {body}") from exc
    except URLError as exc:
        raise ValueError(f"Could not reach Google OAuth server: {exc.reason}") from exc

    if "access_token" not in data:
        raise ValueError("Google response did not include an access token.")

    return data


def fetch_google_calendar_events(access_token, time_min=None):
    """
    Fetch events from the authenticated user's primary Google Calendar via REST API v3.
    Defaults to fetching events starting from 30 days ago onward.
    """
    if time_min is None:
        time_min = (timezone.now() - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")

    params = urlencode({
        "singleEvents": "true",
        "orderBy": "startTime",
        "maxResults": 250,
        "timeMin": time_min,
    })
    url = f"{GOOGLE_CALENDAR_EVENTS_URL}?{params}"

    req = Request(
        url,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        },
    )

    try:
        with urlopen(req, timeout=10, context=_build_ssl_context()) as response:
            data = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code == 401:
            raise ValueError("Google access token expired. Please reconnect your Google Calendar.") from exc
        raise ValueError(f"Google Calendar API returned HTTP {exc.code}.") from exc
    except URLError as exc:
        raise ValueError(f"Could not reach Google Calendar API: {exc.reason}") from exc

    return data.get("items", [])


def parse_google_datetime(dt_dict):
    """
    Convert a Google Calendar 'start' or 'end' dictionary into a UTC datetime.
    Handles both timed events ('dateTime') and all-day events ('date').
    Returns (datetime_utc, is_all_day).
    """
    if not dt_dict:
        return None, False

    if "dateTime" in dt_dict:
        raw_dt = dt_dict["dateTime"].strip()
        # Normalize trailing 'Z' to '+00:00' for Python 3.10 fromisoformat compatibility
        if raw_dt.endswith("Z"):
            raw_dt = raw_dt[:-1] + "+00:00"
        parsed = datetime.fromisoformat(raw_dt)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt_timezone.utc)
        return parsed.astimezone(dt_timezone.utc), False

    if "date" in dt_dict:
        parsed_date = datetime.strptime(dt_dict["date"].strip(), "%Y-%m-%d")
        return parsed_date.replace(tzinfo=dt_timezone.utc), True

    return None, False


def sync_google_events(user, access_token, feed=None, category=Event.Category.PERSONAL):
    """
    Pull events from Google Calendar API, convert to UTC, hash with SHA-256,
    and save/update Event records without creating duplicates.
    """
    items = fetch_google_calendar_events(access_token)

    if feed is None:
        feed, _ = ExternalFeed.objects.get_or_create(
            user=user,
            source_type="Google",
            feed_url=GOOGLE_CALENDAR_EVENTS_URL,
        )

    summary = {
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "events": [],
    }

    with transaction.atomic():
        for item in items:
            # Skip events that were canceled/deleted in Google Calendar
            if item.get("status") == "cancelled":
                continue

            start_time, is_all_day = parse_google_datetime(item.get("start"))
            if start_time is None:
                continue

            end_time, _ = parse_google_datetime(item.get("end"))
            if end_time is None or end_time <= start_time:
                end_time = start_time + (timedelta(days=1) if is_all_day else timedelta(hours=1))

            external_id = (item.get("id") or "").strip()[:255]
            title = (item.get("summary") or "Untitled Event").strip()[:200]
            location = (item.get("location") or "").strip()[:200]
            description = (item.get("description") or "").strip()

            content_hash = Event.build_hash(title, start_time, end_time, location, description)

            existing_event = None
            if external_id:
                existing_event = Event.objects.filter(
                    feed=feed,
                    external_id=external_id,
                ).first()

            if existing_event is None:
                new_event = Event.objects.create(
                    user=user,
                    feed=feed,
                    title=title,
                    start_time=start_time,
                    end_time=end_time,
                    location=location,
                    description=description,
                    category=category,
                    is_imported=True,
                    external_id=external_id,
                    content_hash=content_hash,
                )
                summary["created"] += 1
                summary["events"].append(new_event)
            elif existing_event.content_hash != content_hash:
                existing_event.title = title
                existing_event.start_time = start_time
                existing_event.end_time = end_time
                existing_event.location = location
                existing_event.description = description
                existing_event.content_hash = content_hash
                existing_event.save()
                summary["updated"] += 1
                summary["events"].append(existing_event)
            else:
                summary["skipped"] += 1

        feed.last_synced_at = timezone.now()
        feed.save(update_fields=["last_synced_at"])

    return summary
