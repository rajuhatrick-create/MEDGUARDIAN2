# Med Guardian / NestIQ App Patch

This folder contains only the web app files: `index.html`, `app.js`, and `style.css`.

## Changes
- Adds dock attachment status (`DOCKED`, `UNDOCKED`, `UNKNOWN`).
- Displays limit-switch readiness and active/released/unknown state.
- Shows telemetry freshness and the last-received timestamp.
- Shows explicit reasons why dispense requests are blocked.
- Client-side dispense guard fails closed when telemetry is stale or unknown, dock state is not confirmed undocked, the dock switch is not ready/released, lid-closed status is not confirmed, reported faults exist, or calibration/clock/actuation checks are incomplete.
- Re-checks the guard when a dispense button is clicked, not only when rendering the page.
- Blocks snooze requests from stale/offline devices.

## Install
Replace the existing deployed app's `index.html`, `app.js`, and `style.css` with these files. Keep the existing server and `/api/v1` routes. The page expects the app to be served at the same origin as the API.

## Important limitations
This is a frontend-only patch. It does not modify or secure the backend command endpoint or firmware. Browser-side checks can be bypassed; the backend and Pico firmware must independently enforce all safety interlocks. The current firmware config uses the limit switch for dock detection while the default lid interlock still expects a separate confirmed lid-closed signal. Therefore this app intentionally keeps dispensing blocked if `lid_closed` is `null` or false. Resolve the physical lid interlock/configuration in firmware before commissioning.

## Validation performed
- JavaScript syntax checked with Node.js.
- Confirmed the three app assets and this README are present.
- No live backend/browser test or hardware test was performed.
