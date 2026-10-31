# Deploying Med Guardian / NestIQ on Netlify from your GitHub repo

Repo: https://github.com/rajuhatrick-create/MEDGUARDIAN2 (branch `main`).
What Netlify hosts: the dashboard (`public/`), the API function (`netlify/functions/api.mts`) and the
database (`db/`, migrations in `netlify/database/migrations/`). The Pico firmware is NOT deployed to
Netlify; it is copied to the board over USB (see README.md).

## Part 1 - Put the updated files in your repo

The ZIP contains the full updated project. Your GitHub repo currently lacks the new firmware, tests and docs.

1. Unzip `MedGuardian_Complete.zip` to a folder.
2. In a terminal (Git installed, signed in to GitHub):
   ```
   git clone https://github.com/rajuhatrick-create/MEDGUARDIAN2.git
   cd MEDGUARDIAN2
   ```
3. Copy everything from the unzipped folder into the clone, replacing files when asked
   (do not copy any `node_modules` or `.git` folders).
4. Check that `firmware/config.py` still has empty `WIFI_SSID`, `WIFI_PASSWORD`, `DEVICE_KEY`. Never commit real values.
5. Commit and push:
   ```
   git add -A
   git commit -m "Complete four-servo firmware, dashboard updates, docs and tests"
   git push origin main
   ```
   Alternative without the command line: on GitHub use **Add file > Upload files**, drag the unzipped contents in, and commit to `main`.

## Part 2 - Create the Netlify site from the repo

1. Sign in at https://app.netlify.com (a free account works).
2. **Add new project > Import an existing project > GitHub**. Authorize Netlify for GitHub and select `MEDGUARDIAN2`.
3. Build settings (they come from `netlify.toml`, so leave the defaults):
   - Branch to deploy: `main`
   - Build command: leave empty
   - Publish directory: `public`
   - Functions directory: `netlify/functions` (default)
4. **Before the first deploy** (or immediately after), add the environment variable below, then deploy.

## Part 3 - Required environment variable

In **Project configuration > Environment variables > Add a variable**:

| Key | Value |
|---|---|
| `CAREGIVER_PASSWORD` | a password of **at least 12 characters** that you invent |

Without it, sign-in answers "Caregiver password is not set up". After adding or changing it, trigger a
redeploy (**Deploys > Trigger deploy > Deploy project without cache**). Do not put this password in the repo.

## Part 4 - Database

The API uses Netlify's built-in database (`@netlify/database` with Drizzle), so no external database
URL is needed. Check it is working:

1. Open **Deploys** and read the latest deploy log. Look for the database migration
   `20261030152932_create_med_guardian_tables` being applied.
2. If the log shows no migration step and sign-in later returns "Server error", open
   **Project configuration > Database** (or Extensions) and enable Netlify Database for the project,
   then redeploy. Netlify's database features change over time, so follow the current wording on that page.
3. If you change `db/schema.ts` later: run `npx drizzle-kit generate`, commit the new migration folder, push.

## Part 5 - First sign-in and pairing the device

1. Open your site URL (shown at the top of the project page, like `https://something.netlify.app`).
2. Sign in with `CAREGIVER_PASSWORD`.
3. Click **Register device**, keep `nestiq-01` or choose an ID, click **Generate device key**.
4. Copy the `device_id` and `device_key` immediately. The key is shown once; only its hash is stored.
5. On your computer put them into `firmware/config.py`:
   ```
   DEVICE_ID = "nestiq-01"
   DEVICE_KEY = "<the key>"
   WIFI_SSID = "<your Wi-Fi>"
   WIFI_PASSWORD = "<your Wi-Fi password>"
   SERVER_URL = "https://<your-site>.netlify.app"
   ```
   Use your actual Netlify address for `SERVER_URL` (the default in the file is from your earlier project).
6. Upload to the board with the commands in README.md. Within about 30 seconds the dashboard shows
   "Device online". The device must reach the internet over Wi-Fi.

Do not commit `config.py` after filling it in. Keep a private copy, or run `git update-index --assume-unchanged firmware/config.py`.

## Part 6 - Verify the deployment

- Site loads and shows the NestIQ sign-in page.
- Wrong password is rejected; correct password opens the dashboard.
- Registering a device returns a key.
- With the board running, telemetry appears (Dock, Limit switch, Load cell, GPS, Servo roles).
- The Dispense button shows "DISPENSING BLOCKED" with a reason until commissioning is complete. This is expected.
- Function errors: **Logs > Functions > api**.

## Common problems

| Symptom | Fix |
|---|---|
| "Caregiver password is not set up" | Add `CAREGIVER_PASSWORD` (12+ chars) and redeploy. |
| "Server error" after sign-in | Database not enabled or migration not applied (Part 4); read the function log. |
| 404 on `/api/v1/...` | Confirm `netlify/functions/api.mts` is in the repo and the function appears under Functions in the deploy summary. |
| Device never goes online | Wrong `SERVER_URL`/`DEVICE_ID`/`DEVICE_KEY`, Wi-Fi blocked, or board clock; run `mpremote connect COMx` and read the log. The key is never printed. |
| "Unknown device or wrong key" | Register again for a new key, update `config.py`, re-upload. |
| Dashboard works but nothing can dispense | Normal until commissioning is finished (README.md, PHYSICAL_TEST_CHECKLIST.md). |

## Security notes

Use HTTPS only (Netlify provides it). Anyone with the password can queue commands, so use a strong unique password.
This is an engineering prototype: use inert objects only, never real medication, until supervised testing is complete.
