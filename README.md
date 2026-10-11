# City Detection and Community Reports

A full-stack application for reviewing traffic, helmet use, garbage, and potholes from video, webcam, or CCTV sources. Residents can submit location-based reports with photos; administrators can manage detection events and update residents as work progresses.

## Features

- Four detection models: traffic congestion, helmet and number plate, garbage, and potholes.
- A consolidated multi-camera workspace. Select a model once, then choose Video, Webcam, or CCTV for each panel; add or delete panels as needed.
- Live camera alerts for high traffic congestion and for garbage/pothole detections, identified by camera panel.
- An admin dashboard with model totals, filtered recent-event logs, image previews, and deletion controls.
- Resident accounts and issue reports for traffic congestion, garbage, or potholes. Reports include contact information, location, description, and an area photo.
- Admin progress messages with photos. A completion photo is required to resolve a report; residents can follow updates and rate resolved work.
- Four model-specific MongoDB collections, plus collections for accounts, sessions, reports, and report updates.

## Requirements

- Python 3.10 or newer
- Node.js and npm
- MongoDB Atlas connection string
- Model weights in `backend/models/`

## Configure the backend

Create a `.env` file in the repository root (or in `backend/`) with your private Atlas connection string and admin setup configuration:

```env
MONGO_URI=<your MongoDB Atlas connection string>
ADMIN_SETUP_KEY=<a private random key of at least 32 characters>
AUTH_COOKIE_SECURE=false
FRONTEND_ORIGINS=http://localhost:5173,http://localhost:5174,http://localhost:5175
```

Alternatively, provision an admin from environment variables:

```env
ADMIN_EMAIL=<administrator email>
ADMIN_PASSWORD=<unique password of at least 12 characters>
ADMIN_NAME=City Operations
```

Keep `.env` private and never commit it. Set `AUTH_COOKIE_SECURE=true` when serving over HTTPS, and set `FRONTEND_ORIGINS` to the exact deployed frontend origins.

On startup, the backend ensures these model collections exist in the `traffic_violations` database:

| Detection type | Collection |
| --- | --- |
| Helmet and plate violations | `no_helmet_records` |
| Traffic congestion | `traffic_records` |
| Garbage | `garbage_records` |
| Potholes | `pothole_records` |

It also uses `users`, `user_sessions`, `auth_settings`, `issue_reports`, and `report_updates`. Existing records in the legacy `smart_city_records` collection remain readable. Report photos are stored under `backend/report_photos/`, which is Git-ignored.

## Run locally

Install backend dependencies from the repository root:

```powershell
python -m pip install -r backend/requirements.txt
```

Start the backend from the repository root:

```powershell
uvicorn --app-dir backend app:app --reload --port 8000
```

Install and start the frontend in a second terminal:

```powershell
cd traffic-frontend
npm install
npm run dev
```

Vite prints the local URL. If port 5173 is already in use, it automatically chooses another port; add that origin to `FRONTEND_ORIGINS` in `.env` and restart the backend if the port is not already listed.

## Accounts and pages

- Residents: `/register` to create a user account, `/login` to sign in, `/report` to submit and follow reports.
- First administrator: set `ADMIN_SETUP_KEY`, then open `/admin/register` once. Initial setup closes after an admin account is created.
- Administrators: `/admin/login`; Home is `/welcome`, the overview is `/dashboard`, the consolidated model/source workspace is `/multistream`, and community reports are at `/admin/reports`.

Public registration always creates a regular user. Backend authorization protects admin pages, detection APIs, event deletion, report updates, and report photos.

## Detection workspace

Choose Traffic, Helmet, Garbage, or Pothole in **Multiple videos**. Each panel has independent source controls:

- **Video:** upload a recorded clip for frame-by-frame analysis.
- **Webcam:** choose a local camera index and analyze a short frame capture.
- **CCTV:** enter an RTSP address for a network camera.

Each source creates its own panel state. Traffic panels show high-congestion alerts; Garbage and Pothole panels show camera-specific alerts when detections are present.

## Resident report workflow

Residents can report traffic congestion, garbage, or potholes with their name, mobile number, location, description, and a photo. The user report page refreshes updates periodically. Administrators can send status and progress messages with photos; a completion photo is required to mark a report resolved. Residents can view each update and its photo, then leave one 1–5 star rating with an optional comment.

Reports can be deleted by their owner or an administrator. Deletion removes the MongoDB report and update records, plus their stored photos. Detection event deletion is available to administrators and removes the model record and its saved frame when no other event references it.

## Models and files

| Model | File |
| --- | --- |
| Traffic congestion | `backend/models/congestion.pt` |
| Helmet detection | `backend/models/helmet_model.pt` |
| Number plates | `backend/models/plate_model.pt` |
| Garbage | `backend/models/garbage_model.pt` |
| Potholes | `backend/models/pathhole.pt` |

The backend loads models on demand. Keep the weight files in `backend/models/` and do not commit private credentials or uploaded report photos.