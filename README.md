# Satark Sarthi - AI Document Screening & Verification System

An advanced automated document screening, forgery detection, and identity verification system designed for checkpoint oversight, border management, and enterprise KYC verification.

## 🚀 Key Features

- **Document Analysis & OCR**: Automated optical character recognition extracting data from Passports, Visas, Aadhaar, Driving Licenses, and Permits using native Windows OCR (WinRT).
- **AI Face Detection & Matching**: Integrated OpenCV YuNet for face detection and SFace deep learning model for facial biometric recognition and cosine similarity verification.
- **Digital Forgery Detection**: Multi-faceted document forensics including Error Level Analysis (ELA), noise pattern distribution analysis, and font/tampering consistency checks.
- **Asynchronous Task Processing**: High-throughput processing pipeline using Celery and Redis message broker.
- **Audit & Case Management**: MongoDB persistence for screening audit trails, officer verdicts, and case management.
- **Interactive Web Dashboards**: Officer checkpoint screening interface and corporate dashboard suite with real-time screening results and live alerts.

## 🛠️ Tech Stack

- **Backend**: Python, Flask, Celery, Redis, PyMongo
- **AI / Computer Vision**: OpenCV (YuNet, SFace ONNX models), Pillow, scikit-image
- **OCR Engine**: WinRT Windows Media OCR
- **Frontend**: HTML5, Vanilla JavaScript, CSS3, SVG Icons

## 📋 Prerequisites

- Python 3.10+
- MongoDB instance running locally on `localhost:27017`
- Redis server running on `localhost:6379`
- Windows OS (for Windows Media OCR engine)

## ⚙️ Installation & Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/nimeshkapoor100-pixel/document-screening-system.git
   cd document-screening-system
   ```

2. **Create and activate a virtual environment:**
   ```bash
   python -m venv venv
   .\venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Seed initial users / test database (optional):**
   ```bash
   python seed_db.py
   ```

5. **Start Redis server & Celery worker:**
   ```bash
   celery -A tasks.celery worker --loglevel=info -P solo
   ```

6. **Run the Flask application:**
   ```bash
   python app.py
   ```
   Open your browser at `http://localhost:5000` to access the officer login and screening portal.

## 📄 License
MIT License
