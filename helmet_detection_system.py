

import cv2
import easyocr
import datetime
import os
import sys
import time
from pathlib import Path
from ultralytics import YOLO
from pymongo import MongoClient


HELMET_MODEL_PATH  = "helmet_model.pt"      
PLATE_MODEL_PATH   = "plate_model.pt"       
MONGO_URI          = "mongodb+srv://helmet_detection:m7hkqM07UK1fsLzI@cluster1.xrtpvme.mongodb.net/?appName=Cluster1"
MONGO_DB           = "traffic_violations"
MONGO_COLLECTION   = "no_helmet_records"
SAVE_FRAMES_DIR    = "violation_frames"     
CONFIDENCE_HELMET  = 0.2                    
CONFIDENCE_PLATE   = 0.2                   



def connect_mongodb():
    
    client = MongoClient(MONGO_URI)
    db     = client[MONGO_DB]
    col    = db[MONGO_COLLECTION]
    print(f"[DB] Connected to MongoDB → {MONGO_DB}.{MONGO_COLLECTION}")
    return col


def save_violation(collection, plate_text, frame, source_name):
   
    os.makedirs(SAVE_FRAMES_DIR, exist_ok=True)

    timestamp  = datetime.datetime.now()
    frame_name = f"{timestamp.strftime('%Y%m%d_%H%M%S_%f')}.jpg"
    frame_path = os.path.join(SAVE_FRAMES_DIR, frame_name)
    cv2.imwrite(frame_path, frame)

    record = {
        "plate_number" : plate_text.strip().upper(),
        "timestamp"    : timestamp,
        "source"       : source_name,
        "frame_saved"  : frame_path,
    }
    result = collection.insert_one(record)
    print(f"[DB] Saved violation → plate: {plate_text}  id: {result.inserted_id}")
    return record


def detect_and_record(source, collection):
   

    print("[Model] Loading helmet model...")
    helmet_model = YOLO(HELMET_MODEL_PATH)

    print("[Model] Loading plate model...")
    plate_model  = YOLO(PLATE_MODEL_PATH)

    print("[OCR] Initialising EasyOCR...")
    reader = easyocr.Reader(["en"], gpu=False)   

    is_image = isinstance(source, str) and source.lower().endswith(
        (".jpg", ".jpeg", ".png", ".bmp", ".webp")
    )

    if is_image:
        frames     = [cv2.imread(source)]
        source_tag = os.path.basename(source)
    else:
        cap        = cv2.VideoCapture(source)
        source_tag = str(source)
        if not cap.isOpened():
            print(f"[Error] Cannot open source: {source}")
            return

  
    saved_plates = set()

    print(f"\n[Run] Starting detection on: {source_tag}")
    print("      Press  Q  to quit\n")

    frame_idx = 0

    while True:
        
        if is_image:
            if frame_idx >= len(frames):
                break
            frame = frames[frame_idx]
            frame_idx += 1
        else:
            ret, frame = cap.read()
            if not ret:
                print("[Run] End of video / stream.")
                break
            frame_idx += 1
            if frame_idx % 5 != 0:
                continue

        if frame is None:
            break

        display = frame.copy()
        frame = cv2.resize(frame, (640, 360))
        display = frame.copy()

       
        helmet_results = helmet_model(frame, conf=CONFIDENCE_HELMET, verbose=False, imgsz=640)

        for det in helmet_results[0].boxes:
            cls_id     = int(det.cls[0])
            label      = helmet_model.names[cls_id]
            conf       = float(det.conf[0])
            x1, y1, x2, y2 = map(int, det.xyxy[0])

            if label.lower() in ("with helmet", "with_helmet", "helmet"):
               
                cv2.rectangle(display, (x1, y1), (x2, y2), (0, 200, 0), 2)
                cv2.putText(display, f"Helmet {conf:.2f}",
                            (x1, y1 - 8), cv2.FONT_HERSHEY_SIMPLEX,
                            0.55, (0, 200, 0), 2)

            else:
              
                cv2.rectangle(display, (x1, y1), (x2, y2), (0, 0, 220), 2)
                cv2.putText(display, f"NO HELMET {conf:.2f}",
                            (x1, y1 - 8), cv2.FONT_HERSHEY_SIMPLEX,
                            0.6, (0, 0, 220), 2)

             
                plate_results = plate_model(frame, conf=CONFIDENCE_PLATE, verbose=False)

                if len(plate_results[0].boxes) == 0:
                    if "NO PLATE FOUND" not in saved_plates:
                        save_violation(collection, "NO PLATE FOUND", display.copy(), source_tag)
                        saved_plates.add("NO PLATE FOUND")
                else:
                    for pdet in plate_results[0].boxes:
                        px1, py1, px2, py2 = map(int, pdet.xyxy[0])

                        plate_crop = frame[py1:py2, px1:px2]
                        if plate_crop.size == 0:
                            continue

                        
                        ocr_results = reader.readtext(plate_crop)
                        plate_text  = " ".join([r[1] for r in ocr_results]).strip()

                        if not plate_text:
                            plate_text = "UNREADABLE"

                        cv2.rectangle(display, (px1, py1), (px2, py2), (0, 140, 255), 2)
                        cv2.putText(display, plate_text,
                                    (px1, py2 + 20), cv2.FONT_HERSHEY_SIMPLEX,
                                    0.7, (0, 140, 255), 2)

                      
                        if plate_text not in saved_plates:
                            save_violation(collection, plate_text, display.copy(), source_tag)
                            saved_plates.add(plate_text)


        cv2.putText(display, f"Frame {frame_idx}",
                    (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 1)
        cv2.imshow("Helmet Detection — press Q to quit", display)

        key = cv2.waitKey(150 if not is_image else 0) & 0xFF
        if key == ord("q"):
            break

    if not is_image:
        cap.release()
    cv2.destroyAllWindows()
    print(f"\n[Done] Processed {frame_idx} frame(s). Violations saved: {len(saved_plates)}")


def train_helmet_model():
   
    model = YOLO("yolov8n.pt")  
    model.train(
        data   = "helmet_dataset.yaml",
        epochs = 50,
        imgsz  = 640,
        batch  = 16,
        name   = "helmet_detector",
        device = "cpu",         
    )
    print("[Train] Done! Best weights saved to: runs/detect/helmet_detector/weights/best.pt")
    print("        Copy that file and rename it to:  helmet_model.pt")


def train_plate_model():
   
    model = YOLO("yolov8n.pt")
    model.train(
        data   = "plate_dataset.yaml",
        epochs = 50,
        imgsz  = 640,
        batch  = 16,
        name   = "plate_detector",
        device = "cpu",
    )
    print("[Train] Done! Best weights saved to: runs/detect/plate_detector/weights/best.pt")
    print("        Copy that file and rename it to:  plate_model.pt")


def show_violations(collection):
  
    records = list(collection.find({}, {"_id": 0}).sort("timestamp", -1))
    if not records:
        print("[DB] No violations found.")
        return
    print(f"\n[DB] {len(records)} violation(s) on record:\n")
    print(f"{'Plate':<20} {'Timestamp':<25} {'Source'}")
    print("-" * 65)
    for r in records:
        print(f"{r['plate_number']:<20} {str(r['timestamp']):<25} {r['source']}")


if __name__ == "__main__":
    collection = connect_mongodb()

    print("""

   Helmet Detection System            

  1. Run on video file                
  2. Run on webcam (live)             
  3. Run on image                     
  4. Show saved violations (MongoDB)  
  5. Train helmet model               
  6. Train plate model                

    """)

    choice = input("Choose (1-6): ").strip()

    if choice == "1":
        path = input("Enter video file path: ").strip()
        detect_and_record(path, collection)

    elif choice == "2":
        detect_and_record(0, collection)   

    elif choice == "3":
        path = input("Enter image file path: ").strip()
        detect_and_record(path, collection)

    elif choice == "4":
        show_violations(collection)

    elif choice == "5":
        train_helmet_model()

    elif choice == "6":
        train_plate_model()

    else:
        print("Invalid choice.")