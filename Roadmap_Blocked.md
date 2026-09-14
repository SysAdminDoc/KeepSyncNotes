# KeepSync Notes Blocked Roadmap

- **Google Keep API live sync:** Requires test credentials, a dedicated Keep account, and permission to verify remote writes. The existing gkeepapi path can read and plan changes, but bidirectional mutation still needs a safe live test.
- **Reminder geofences:** Time reminders and location text already work. Actual geofence activation needs a cross-platform location provider plus the operating system permission flow.
- **Local summarization:** The proposed weekly summary needs a configured local model endpoint before it can be exercised.
- **Android companion:** A Kotlin and Compose client needs a documented interchange format or synchronized database contract before it can share the same library safely.

Keyboard shortcuts were removed from the roadmap because this project intentionally avoids them.
