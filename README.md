# 🚦 Helmet & Number Plate Violation Detection System

A real-time traffic violation detection system that automatically detects riders without helmets, reads their number plates using OCR, and logs violations to a cloud database.

---

## 🚀 Features

- Helmet Detection (with/without helmet)
- Number Plate Detection & OCR
- Live YouTube Stream Support
- Local Video & Image Support
- Webcam Live Detection
- MongoDB Atlas Cloud Logging
- Violation Frame Snapshots
- Real-time Bounding Box Display

---

## 🛠 Tech Stack

### Detection Models
- YOLOv8 (Ultralytics)
- Custom trained Helmet Model — 86.8% mAP50
- Custom trained Plate Model — 97.2% mAP50

### OCR
- EasyOCR

### Database
- MongoDB Atlas

### Training
- Google Colab (Tesla T4 GPU)
- Roboflow Dataset

### Language
- Python 3.12

---

## 📂 Folder Structure
helmet_detection/
├── helmet_detection_system.py
├── helmet_model.pt
├── plate_model.pt
├── violation_frames/
└── requirements.txt

---

## ⚙️ Installation

Clone the repository

```bash
git clone https://github.com/BidiptaMallik/helmet_detection.git
```

Install dependencies

```bash
pip install ultralytics opencv-python easyocr pymongo yt-dlp
```

Run the system

```bash
python helmet_detection_system.py
```

---

## 🎯 How It Works

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

---

## 📊 Model Performance

| Model | Accuracy | Dataset Size |
|---|---|---|
| Helmet Detection | 86.8% mAP50 | 8,000+ images |
| Plate Detection | 97.2% mAP50 | 2,000+ images |

---

## 📸 Screenshots


---

## Author

**Bidipta Mallik**