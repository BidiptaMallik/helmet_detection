#  Helmet & Number Plate Violation Detection System

A real-time traffic violation detection system that automatically detects riders without helmets, reads their number plates using OCR, and logs violations to a cloud database.

---

##  Features

- Helmet Detection (with/without helmet)
- Number Plate Detection & OCR
- Live YouTube Stream Support
- Local Video & Image Support
- Webcam Live Detection
- MongoDB Atlas Cloud Logging
- Violation Frame Snapshots
- Real-time Bounding Box Display

---

##  Tech Stack

### Detection Models
- YOLOv8 (Ultralytics)
- Custom trained Helmet Model — 86.8% mAP50
- Custom trained Plate Model — 97.2% mAP50

### OCR
- EasyOCR

### Database
- MongoDB Atlas

### Training
- Google Colab 
- Roboflow Dataset

### Language
- Python 3.12

---

##  Folder Structure

```
helmet_detection/
├── helmet_detection_system.py
├── helmet_model.pt
├── plate_model.pt
├── violation_frames/
└── requirements.txt
```

---

##  Installation

Clone the repository

```bash
git clone https://github.com/BidiptaMallik/helmet_detection.git
```

Install dependencies

```bash
pip install ultralytics opencv-python easyocr pymongo 
```

Run the system

```bash
python helmet_detection_system.py
```

## Web App Accounts and Reports

The web app has two roles:

- Residents can create a regular account and submit traffic congestion, garbage, or pothole reports with a location, contact number, description, and photo.
- Residents can follow report status and admin messages, view the completion photo, and rate resolved work. The report page checks for updates every 30 seconds.
- Administrators can use the existing detection tools, send progress messages, attach a completion photo when resolving a report, and review resident ratings.

Add these values to `backend/.env` before starting FastAPI:

```env
MONGO_URI=<your MongoDB Atlas connection string>
ADMIN_EMAIL=<administrator email>
ADMIN_PASSWORD=<unique password with at least 12 characters>
ADMIN_NAME=City Operations
ADMIN_SETUP_KEY=<optional one-time key with at least 32 random characters>
AUTH_COOKIE_SECURE=false
FRONTEND_ORIGINS=http://localhost:5173,http://localhost:5174
```

The backend provisions an administrator from `ADMIN_EMAIL` and `ADMIN_PASSWORD` at startup. Alternatively, set a private, random `ADMIN_SETUP_KEY` and create the first admin once at `/admin/register`; that public setup closes automatically after an admin exists. Public user registration can never grant administrator access. Set `AUTH_COOKIE_SECURE=true` when serving the app over HTTPS, and set `FRONTEND_ORIGINS` to the deployed frontend origins. Keep `.env` private; uploaded complaint photos are stored under `backend/report_photos/`, which is excluded from Git.

Residents use `/login` and `/register`. Administrators use `/admin/login`; after sign-in they land on the existing detection dashboard and can open the Reports page from the admin navigation. The first administrator can be created at `/admin/register` when one-time setup is enabled.

---

##  How It Works

```
Input (Video/Stream/Image)
        ↓
Helmet Detection (YOLOv8)
        ↓
No Helmet Found?
        ↓
Number Plate Detection (YOLOv8)
        ↓
OCR reads plate text (EasyOCR)
        ↓
Save to MongoDB Atlas + Frame snapshot
```

---

##  Model Performance

| Model | Accuracy | Dataset Size |
|---|---|---|
| Helmet Detection | 86.8% mAP50 | 8,000+ images |
| Plate Detection | 97.2% mAP50 | 2,000+ images |

---



---

## Author

**Bidipta Mallik**