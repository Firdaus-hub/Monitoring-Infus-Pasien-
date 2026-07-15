# 💧 InfuMonitor — Sistem Monitoring Infus Rumah Sakit

Aplikasi web real-time untuk memonitor infus pasien di rumah sakit, dibangun dengan **FastAPI** + **SQLAlchemy** + **Jinja2**.

## ✨ Fitur

- **Dashboard** — Ringkasan status infus aktif, hampir habis, dan alarm
- **Live Monitoring** — Pemantauan real-time via WebSocket dengan update tiap 3 detik
- **Riwayat** — Histori data monitoring dengan filter (pasien, ruangan, tanggal, status)
- **CRUD Data Master** — Kelola Pasien, Ruangan, Infus, dan Pengguna (Tambah, Edit, Hapus)
- **Login/Logout** — Proteksi halaman dengan autentikasi cookie
- **Responsive** — Tampilan mobile dengan hamburger menu

## 🚀 Cara Menjalankan

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Jalankan Server

```bash
python run.py
```

### 3. Buka Browser

Akses [http://127.0.0.1:8000](http://127.0.0.1:8000)

## 🔐 Akun Demo

| Username  | Password     | Role     |
|-----------|-------------|----------|
| admin     | admin123    | Admin    |
| perawat   | perawat123  | Perawat  |
| teknisi   | teknisi123  | Teknisi  |

## 📁 Struktur Proyek

```
Tugas UAS Daus/
├── app/
│   ├── __init__.py        # Package init
│   ├── main.py            # FastAPI routes & WebSocket
│   ├── models.py          # SQLAlchemy models
│   ├── database.py        # Database engine & session
│   ├── auth.py            # Password hashing & verification
│   ├── seed.py            # Sample data seeder
│   ├── static/
│   │   └── css/style.css  # Stylesheet
│   └── templates/         # Jinja2 HTML templates
├── requirements.txt       # Python dependencies
├── run.py                 # Entry point
└── README.md
```

## 🛠️ Teknologi

- **Backend**: Python 3.10+, FastAPI, SQLAlchemy, Jinja2
- **Frontend**: HTML5, CSS3, JavaScript (Vanilla), Chart.js
- **Database**: SQLite
- **Real-time**: WebSocket
