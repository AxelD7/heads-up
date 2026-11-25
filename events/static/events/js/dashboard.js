// Find the main HTML elements on the page that the calendar needs in order to work
const calendarGrid = document.querySelector(".calendar-grid");
const calendarDays = document.querySelector(".calendar-days");
const calendarPeriod = document.querySelector(".calendar-current-period");
const eventsElement = document.querySelector("#dashboard-events-data");

// Only run the calendar code if all required elements exist on the current page.
// This prevents JavaScript errors on pages that load this script without a calendar.
if (calendarGrid && calendarDays && calendarPeriod && eventsElement) {
  // Read the "data-time-format" HTML attribute from .calendar-grid (expected to be "12h" or "24h").
  const timeFormat = calendarGrid.dataset.timeFormat;
  const is12Hour = timeFormat !== "24h";

  // Grab references to the popup modal, its form, and the navigation/view buttons once up front
  // so we don't have to repeatedly search the HTML page every time the user clicks something.
  const quickEventDialog = document.querySelector("#quick-event-dialog");
  const quickEventForm = quickEventDialog?.querySelector("form");
  const previousButton = document.querySelector('[data-calendar-action="previous"]');
  const nextButton = document.querySelector('[data-calendar-action="next"]');
  const viewButtons = document.querySelectorAll("[data-calendar-view]");
  const actionButtons = document.querySelectorAll("[data-calendar-action]");

  // Ensure the global helper object exists, and provide a fallback function if it wasn't loaded elsewhere.
  // This converts a browser's local date/time string into a standard UTC ISO string for Django.
  window.HeadsUpTime = window.HeadsUpTime || {};
  window.HeadsUpTime.localInputToUtc =
    window.HeadsUpTime.localInputToUtc ||
    ((value) => (value ? new Date(value).toISOString() : ""));

  
  // Helper function that converts an event object from JSON format into the  structure that FullCalendar expects.
 
   
  function toCalendarEvent(rawEvent) {
    return {
      id: rawEvent.id,
      title: rawEvent.title,
      start: rawEvent.start, // Django sends timestamps in milliseconds, which FullCalendar reads directly
      end: rawEvent.end,
      // Support either "detail_url" (from initial page load) or "url" (from AJAX save response)
      url: rawEvent.detail_url || rawEvent.url,
      // Attach base styling plus a category-specific color class (e.g., "calendar-event--work") if present
      classNames: [
        "calendar-event",
        ...(rawEvent.category ? [`calendar-event--${rawEvent.category}`] : []),
      ],
    };
  }

  // Parse the JSON string embedded inside tag and convert every event into FullCalendar's format using .map().
  const initialEvents = JSON.parse(eventsElement.textContent).map(toCalendarEvent);

  // Create and configure the FullCalendar instance inside the .calendar-days container.
  const calendar = new FullCalendar.Calendar(calendarDays, {
    // Start in the monthly grid view
    initialView: "dayGridMonth",

    // Set calendar height to the full browser window height minus 290px for headers/toolbars
    height: "calc(100vh - 290px)",

    // Hide FullCalendar's built-in top toolbar because our Django template has its own custom buttons
    headerToolbar: false,

    // In month view, show up to 3 events per day cell, then collapse extras into a "+X more" link
    dayMaxEvents: 3,

    // Hide the "all-day" row at the top of week view since all events have specific start/end times
    allDaySlot: false,

    // Allow users to click or drag across dates/hours to trigger quick event creation
    selectable: true,

    // Load our formatted initial events into the calendar
    events: initialEvents,

    // Format event start times (e.g., "9:30 AM" vs "09:30") based on the user's preference
    eventTimeFormat: {
      hour: "numeric",
      minute: "2-digit",
      hour12: is12Hour,
    },

    // Format the hour labels along the left side of the week view
    slotLabelFormat: {
      hour: "numeric",
      minute: "2-digit",
      hour12: is12Hour,
    },

    // This callback runs automatically whenever the visible date range or view (month/week) changes.
    datesSet(info) {
      // Update the page's period heading 
      calendarPeriod.textContent = info.view.title;

      // Update screen-reader accessibility labels on the Previous/Next buttons
      if (previousButton) {
        previousButton.setAttribute("aria-label", `Previous ${info.view.title}`);
      }
      if (nextButton) {
        nextButton.setAttribute("aria-label", `Next ${info.view.title}`);
      }

      // Loop through the Month/Week toggle buttons and mark the active one with aria-pressed="true"
      viewButtons.forEach((button) => {
        const isMonthActive =
          button.dataset.calendarView === "month" && info.view.type === "dayGridMonth";
        const isWeekActive =
          button.dataset.calendarView === "week" && info.view.type === "timeGridWeek";

        button.setAttribute("aria-pressed", String(isMonthActive || isWeekActive));
      });
    },

    // Runs when the user clicks a single day cell in Month view
    dateClick(info) {
      if (!quickEventDialog || info.view.type !== "dayGridMonth") return;
      openQuickEventModal(info.date, null);
    },

    // Runs when the user clicks or drags across a time slot in Week view
    select(info) {
      if (!quickEventDialog || info.view.type !== "timeGridWeek") return;
      openQuickEventModal(info.start, info.start.getHours());
      // Clear FullCalendar's blue selection highlight once the modal opens
      calendar.unselect();
    },
  });


  /**
   * Formats a JavaScript Date object into "YYYY-MM-DDTHH:MM" in the user's local timezone.
   * HTML <input type="datetime-local"> fields require this exact format.
   */
  function toLocalDateTimeInput(date) {
    // Subtract the timezone offset (converted from minutes to milliseconds) so .toISOString() reflects local time
    const offsetMs = date.getTimezoneOffset() * 60000;
    const localDate = new Date(date.getTime() - offsetMs);
    // Keep only the first 16 characters: "YYYY-MM-DDTHH:MM"
    return localDate.toISOString().slice(0, 16);
  }

  // Opens the quick-event popup dialog and pre-fills its start and end time inputs.
  function openQuickEventModal(date, selectedHour = null) {
    if (!quickEventDialog || !quickEventForm) return;

    const start = new Date(date);
    // If an hour was clicked in week view, use it; otherwise default to 9:00 AM
    start.setHours(selectedHour !== null ? selectedHour : 9, 0, 0, 0);

    // Default the event duration to 1 hour
    const end = new Date(start);
    end.setHours(end.getHours() + 1);

    // Populate the form inputs and clear any leftover validation errors from previous attempts
    quickEventForm.elements.start_time.value = toLocalDateTimeInput(start);
    quickEventForm.elements.end_time.value = toLocalDateTimeInput(end);
    clearQuickEventErrors();

    // Open the native HTML <dialog> modal and put the cursor in the Title input
    quickEventDialog.showModal();
    quickEventForm.elements.title.focus();
  }

  // Resets all red error borders and error messages inside the quick-event form.
  function clearQuickEventErrors() {
    if (!quickEventForm) return;

    quickEventForm.querySelectorAll(".is-invalid").forEach((input) => {
      input.classList.remove("is-invalid");
      input.removeAttribute("aria-invalid");
    });

    quickEventForm.querySelectorAll("[data-field-errors]").forEach((target) => {
      target.textContent = "";
    });

    const formErrors = quickEventForm.querySelector("[data-form-errors]");
    if (formErrors) formErrors.textContent = "";
  }

  // Displays validation errors returned by Django next to their matching form inputs.
  function showQuickEventErrors(errors) {
    if (!quickEventForm) return;

    // Loop over each pair of field errors/message
    Object.entries(errors).forEach(([field, messages]) => {
      const input = quickEventForm.elements.namedItem(field);

      if (input) {
        // Highlight the invalid input and show its error message underneath
        input.classList.add("is-invalid");
        input.setAttribute("aria-invalid", "true");

        const errorTarget = quickEventForm.querySelector(`[data-field-errors="${field}"]`);
        if (errorTarget) errorTarget.textContent = messages.join(" ");
      } else {
        // If the error isn't tied to a specific field (e.g., "__all__"), show it in the general error area
        const formErrors = quickEventForm.querySelector("[data-form-errors]");
        if (formErrors) formErrors.textContent = messages.join(" ");
      }
    });
  }


  // Connect the custom "Month" and "Week" buttons to FullCalendar's view switcher
  viewButtons.forEach((button) => {
    button.addEventListener("click", () => {
      const viewName = button.dataset.calendarView === "week" ? "timeGridWeek" : "dayGridMonth";
      calendar.changeView(viewName);
    });
  });

  // Map button action names to their corresponding FullCalendar navigation methods
  const navigationActions = {
    previous: () => calendar.prev(),
    next: () => calendar.next(),
    today: () => calendar.today(),
  };

  // Connect the "Previous", "Next", and "Today" buttons
  actionButtons.forEach((button) => {
    button.addEventListener("click", () => {
      const action = navigationActions[button.dataset.calendarAction];
      if (action) action();
    });
  });

  // Set up modal close buttons, backdrop clicks, and AJAX form submission if the modal exists
  if (quickEventDialog && quickEventForm) {
    // Close modal when clicking any button with [data-close-quick-event] (like "Cancel" or "X")
    quickEventDialog.querySelectorAll("[data-close-quick-event]").forEach((button) => {
      button.addEventListener("click", () => quickEventDialog.close());
    });

    // Close modal when clicking the dark backdrop outside the dialog box
    quickEventDialog.addEventListener("click", (event) => {
      if (event.target === quickEventDialog) quickEventDialog.close();
    });

    // Clear errors whenever the dialog closes (including when pressing the Escape key)
    quickEventDialog.addEventListener("close", clearQuickEventErrors);

    // Intercept form submission so we can send it via AJAX (fetch) without reloading the page
    quickEventForm.addEventListener("submit", async (event) => {
      // Stop the browser's default full-page form submission
      event.preventDefault();
      clearQuickEventErrors();

      // Collect all form fields (including Django's hidden csrfmiddlewaretoken)
      const formData = new FormData(quickEventForm);

      // Convert local start_time and end_time strings into UTC timestamps before sending to Django
      for (const field of ["start_time", "end_time"]) {
        formData.set(field, window.HeadsUpTime.localInputToUtc(formData.get(field)));
      }

      try {
        // Send the POST request asynchronously and wait ("await") for Django's response
        const response = await fetch(quickEventForm.action, {
          method: "POST",
          body: formData,
          headers: { "X-Requested-With": "XMLHttpRequest" },
        });
        const result = await response.json();

        // If Django returned a 400 Bad Request (validation failed), display the errors and stop
        if (!response.ok) {
          showQuickEventErrors(result.errors || {});
          return;
        }

        // Support responses structured either as { id, title, ... } or { event: { id, title, ... } }
        const createdEvent = result.event || result;

        // Add the newly saved event directly onto the calendar UI without refreshing the page
        calendar.addEvent(toCalendarEvent(createdEvent));

        // Close and reset the form
        quickEventDialog.close();
        quickEventForm.reset();
      } catch (error) {
        // Handle network failures or unexpected server crashes gracefully
        const formErrors = quickEventForm.querySelector("[data-form-errors]");
        if (formErrors) {
          formErrors.textContent = "The event could not be saved. Please try again.";
        }
        console.error("Quick event submission failed.", error);
      }
    });
  }

  // Draw the calendar on the page for the first time
  calendar.render();
}