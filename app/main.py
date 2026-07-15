import os
import json
import asyncio
import random
from datetime import datetime, timezone, timedelta
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Depends, Form, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func

from . import models
from .database import engine, get_db, SessionLocal
from .auth import hash_password, verify_password
from .seed import seed_database


# ---------------------------------------------------------------------------
# WebSocket connection manager
# ---------------------------------------------------------------------------
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        dead = []
        for conn in self.active_connections:
            try:
                await conn.send_text(message)
            except Exception:
                dead.append(conn)
        for d in dead:
            self.disconnect(d)


manager = ConnectionManager()


# ---------------------------------------------------------------------------
# Background simulator — updates active infusions every 3 seconds
# ---------------------------------------------------------------------------
async def simulate_realtime_data():
    while True:
        await asyncio.sleep(3)
        db = SessionLocal()
        try:
            active = (
                db.query(models.Infusion)
                .options(joinedload(models.Infusion.patient).joinedload(models.Patient.room))
                .filter(models.Infusion.status == "ACTIVE")
                .all()
            )

            updates = []
            for inf in active:
                drop = (inf.target_flow_rate / 3600) * 3  # ml consumed in 3 sec
                inf.current_volume = round(max(0, inf.current_volume - drop), 2)

                alarm = False
                alarm_reason = None
                if inf.current_volume <= 0:
                    inf.status = "COMPLETED"
                    inf.ended_at = datetime.now(timezone.utc)
                    alarm = True
                    alarm_reason = "Infus habis"
                elif inf.current_volume < 20:
                    alarm = True
                    alarm_reason = "Volume kritis"

                est_empty = None
                if inf.target_flow_rate > 0 and inf.current_volume > 0:
                    hours_left = inf.current_volume / inf.target_flow_rate
                    est_empty = datetime.now(timezone.utc) + timedelta(hours=hours_left)

                # Save monitoring snapshot every ~15 seconds (1 in 5 ticks)
                if random.random() < 0.2:
                    db.add(models.MonitoringData(
                        infusion_id=inf.id,
                        volume=inf.current_volume,
                        flow_rate=inf.target_flow_rate,
                        estimated_empty=est_empty,
                        alarm_active=alarm,
                        alarm_reason=alarm_reason,
                    ))

                updates.append({
                    "id": inf.id,
                    "patient_name": inf.patient.name if inf.patient else "",
                    "room_name": inf.patient.room.name if inf.patient and inf.patient.room else "",
                    "medication": inf.medication_name,
                    "volume": inf.current_volume,
                    "initial_volume": inf.initial_volume,
                    "flow_rate": inf.target_flow_rate,
                    "status": inf.status,
                    "alarm": alarm,
                    "alarm_reason": alarm_reason or "",
                    "est_empty": est_empty.isoformat() if est_empty else None,
                })

            db.commit()

            if updates and manager.active_connections:
                await manager.broadcast(json.dumps(updates))
        except Exception:
            db.rollback()
        finally:
            db.close()


# ---------------------------------------------------------------------------
# Lifespan — runs on startup / shutdown
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    models.Base.metadata.create_all(bind=engine)
    seed_database()
    task = asyncio.create_task(simulate_realtime_data())
    yield
    # Shutdown
    task.cancel()


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = FastAPI(title="Infusion Monitoring System", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))


# ---------------------------------------------------------------------------
# Auth middleware — redirect to /login if not authenticated
# ---------------------------------------------------------------------------
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    public_paths = ["/login", "/static"]
    path = request.url.path
    if any(path.startswith(p) for p in public_paths):
        return await call_next(request)
    user_name = request.cookies.get("user_name")
    if not user_name:
        return RedirectResponse(url="/login", status_code=303)
    return await call_next(request)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
def get_dashboard_stats(db: Session):
    active = db.query(models.Infusion).filter(models.Infusion.status == "ACTIVE").count()
    low = db.query(models.Infusion).filter(
        models.Infusion.status == "ACTIVE",
        models.Infusion.current_volume < 50,
    ).count()
    alarms = db.query(models.MonitoringData).filter(models.MonitoringData.alarm_active == True).count()
    total_patients = db.query(models.Patient).count()
    return {"active": active, "low": low, "alarms": alarms, "total_patients": total_patients}


def _redirect_with_msg(url: str, msg: str, msg_type: str = "success"):
    """Create a redirect response with a flash-like message cookie."""
    sep = "&" if "?" in url else "?"
    response = RedirectResponse(url=url, status_code=303)
    response.set_cookie("flash_msg", msg, max_age=5)
    response.set_cookie("flash_type", msg_type, max_age=5)
    return response


# ===========================================================================
# PAGE ROUTES
# ===========================================================================

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db)):
    stats = get_dashboard_stats(db)
    infusions = (
        db.query(models.Infusion)
        .options(joinedload(models.Infusion.patient).joinedload(models.Patient.room))
        .filter(models.Infusion.status == "ACTIVE")
        .all()
    )
    return templates.TemplateResponse(request, "dashboard.html", {
        "stats": stats,
        "infusions": infusions,
        "page": "dashboard",
    })


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {"is_auth_page": True, "error": ""})


@app.post("/login", response_class=HTMLResponse)
async def login_submit(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == username).first()
    if user and verify_password(password, user.hashed_password):
        response = RedirectResponse(url="/", status_code=303)
        response.set_cookie("user_name", user.name)
        response.set_cookie("user_role", user.role)
        return response
    return templates.TemplateResponse(request, "login.html", {"is_auth_page": True, "error": "Username atau password salah!"})


@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("user_name")
    response.delete_cookie("user_role")
    return response


@app.get("/monitoring", response_class=HTMLResponse)
async def monitoring_page(request: Request, db: Session = Depends(get_db)):
    infusions = (
        db.query(models.Infusion)
        .options(joinedload(models.Infusion.patient).joinedload(models.Patient.room))
        .filter(models.Infusion.status == "ACTIVE")
        .all()
    )
    return templates.TemplateResponse(request, "monitoring.html", {
        "infusions": infusions,
        "page": "monitoring",
    })


@app.get("/history", response_class=HTMLResponse)
async def history_page(
    request: Request,
    patient: str = Query("", alias="patient"),
    room: str = Query("", alias="room"),
    date: str = Query("", alias="date"),
    status: str = Query("", alias="status"),
    db: Session = Depends(get_db),
):
    query = (
        db.query(models.MonitoringData)
        .join(models.Infusion)
        .join(models.Patient)
        .join(models.Room)
        .options(
            joinedload(models.MonitoringData.infusion)
            .joinedload(models.Infusion.patient)
            .joinedload(models.Patient.room)
        )
    )

    if patient:
        query = query.filter(models.Patient.name.ilike(f"%{patient}%"))
    if room:
        query = query.filter(models.Room.name.ilike(f"%{room}%"))
    if status:
        query = query.filter(models.Infusion.status == status)
    if date:
        try:
            d = datetime.strptime(date, "%Y-%m-%d")
            query = query.filter(
                models.MonitoringData.timestamp >= d,
                models.MonitoringData.timestamp < d + timedelta(days=1),
            )
        except ValueError:
            pass

    records = query.order_by(models.MonitoringData.timestamp.desc()).limit(100).all()

    rooms = db.query(models.Room).all()
    patients_list = db.query(models.Patient).all()

    return templates.TemplateResponse(request, "history.html", {
        "records": records,
        "rooms": rooms,
        "patients": patients_list,
        "filters": {"patient": patient, "room": room, "date": date, "status": status},
        "page": "history",
    })


# ===========================================================================
# CRUD — PATIENTS
# ===========================================================================

@app.get("/patients", response_class=HTMLResponse)
async def patients_page(request: Request, db: Session = Depends(get_db)):
    patients = db.query(models.Patient).options(joinedload(models.Patient.room)).all()
    rooms = db.query(models.Room).all()
    return templates.TemplateResponse(request, "patients.html", {
        "patients": patients, "rooms": rooms, "page": "patients",
    })


@app.post("/patients/add")
async def add_patient(name: str = Form(...), medical_id: str = Form(...), room_id: int = Form(...), db: Session = Depends(get_db)):
    try:
        db.add(models.Patient(name=name, medical_id=medical_id, room_id=room_id))
        db.commit()
        return _redirect_with_msg("/patients", "Pasien berhasil ditambahkan!")
    except IntegrityError:
        db.rollback()
        return _redirect_with_msg("/patients", "Gagal: No. Rekam Medis sudah terdaftar!", "error")


@app.post("/patients/edit/{patient_id}")
async def edit_patient(patient_id: int, name: str = Form(...), medical_id: str = Form(...), room_id: int = Form(...), db: Session = Depends(get_db)):
    p = db.get(models.Patient, patient_id)
    if not p:
        return _redirect_with_msg("/patients", "Pasien tidak ditemukan!", "error")
    try:
        p.name = name
        p.medical_id = medical_id
        p.room_id = room_id
        db.commit()
        return _redirect_with_msg("/patients", "Data pasien berhasil diperbarui!")
    except IntegrityError:
        db.rollback()
        return _redirect_with_msg("/patients", "Gagal: No. Rekam Medis sudah digunakan!", "error")


@app.post("/patients/delete/{patient_id}")
async def delete_patient(patient_id: int, db: Session = Depends(get_db)):
    p = db.get(models.Patient, patient_id)
    if p:
        db.delete(p)
        db.commit()
        return _redirect_with_msg("/patients", "Pasien berhasil dihapus!")
    return _redirect_with_msg("/patients", "Pasien tidak ditemukan!", "error")


# ===========================================================================
# CRUD — ROOMS
# ===========================================================================

@app.get("/rooms", response_class=HTMLResponse)
async def rooms_page(request: Request, db: Session = Depends(get_db)):
    rooms = db.query(models.Room).all()
    return templates.TemplateResponse(request, "rooms.html", {
        "rooms": rooms, "page": "rooms",
    })


@app.post("/rooms/add")
async def add_room(name: str = Form(...), capacity: int = Form(...), db: Session = Depends(get_db)):
    try:
        db.add(models.Room(name=name, capacity=capacity))
        db.commit()
        return _redirect_with_msg("/rooms", "Ruangan berhasil ditambahkan!")
    except IntegrityError:
        db.rollback()
        return _redirect_with_msg("/rooms", "Gagal: Nama ruangan sudah ada!", "error")


@app.post("/rooms/edit/{room_id}")
async def edit_room(room_id: int, name: str = Form(...), capacity: int = Form(...), db: Session = Depends(get_db)):
    r = db.get(models.Room, room_id)
    if not r:
        return _redirect_with_msg("/rooms", "Ruangan tidak ditemukan!", "error")
    try:
        r.name = name
        r.capacity = capacity
        db.commit()
        return _redirect_with_msg("/rooms", "Data ruangan berhasil diperbarui!")
    except IntegrityError:
        db.rollback()
        return _redirect_with_msg("/rooms", "Gagal: Nama ruangan sudah digunakan!", "error")


@app.post("/rooms/delete/{room_id}")
async def delete_room(room_id: int, db: Session = Depends(get_db)):
    r = db.get(models.Room, room_id)
    if r:
        db.delete(r)
        db.commit()
        return _redirect_with_msg("/rooms", "Ruangan berhasil dihapus!")
    return _redirect_with_msg("/rooms", "Ruangan tidak ditemukan!", "error")


# ===========================================================================
# CRUD — INFUSIONS
# ===========================================================================

@app.get("/infusions", response_class=HTMLResponse)
async def infusions_page(request: Request, db: Session = Depends(get_db)):
    infusions = (
        db.query(models.Infusion)
        .options(joinedload(models.Infusion.patient).joinedload(models.Patient.room))
        .all()
    )
    patients = db.query(models.Patient).all()
    return templates.TemplateResponse(request, "infusions.html", {
        "infusions": infusions, "patients": patients, "page": "infusions",
    })


@app.post("/infusions/add")
async def add_infusion(
    patient_id: int = Form(...),
    medication_name: str = Form(...),
    total_volume: float = Form(...),
    flow_rate: float = Form(...),
    db: Session = Depends(get_db),
):
    try:
        db.add(models.Infusion(
            patient_id=patient_id,
            medication_name=medication_name,
            initial_volume=total_volume,
            current_volume=total_volume,
            target_flow_rate=flow_rate,
            status="ACTIVE",
        ))
        db.commit()
        return _redirect_with_msg("/infusions", "Infus berhasil ditambahkan!")
    except IntegrityError:
        db.rollback()
        return _redirect_with_msg("/infusions", "Gagal menambahkan infus!", "error")


@app.post("/infusions/edit/{infusion_id}")
async def edit_infusion(
    infusion_id: int,
    medication_name: str = Form(...),
    flow_rate: float = Form(...),
    status: str = Form(...),
    db: Session = Depends(get_db),
):
    inf = db.get(models.Infusion, infusion_id)
    if not inf:
        return _redirect_with_msg("/infusions", "Infus tidak ditemukan!", "error")
    inf.medication_name = medication_name
    inf.target_flow_rate = flow_rate
    inf.status = status
    if status == "COMPLETED" and not inf.ended_at:
        inf.ended_at = datetime.now(timezone.utc)
    db.commit()
    return _redirect_with_msg("/infusions", "Data infus berhasil diperbarui!")


@app.post("/infusions/delete/{infusion_id}")
async def delete_infusion(infusion_id: int, db: Session = Depends(get_db)):
    inf = db.get(models.Infusion, infusion_id)
    if inf:
        db.delete(inf)
        db.commit()
        return _redirect_with_msg("/infusions", "Infus berhasil dihapus!")
    return _redirect_with_msg("/infusions", "Infus tidak ditemukan!", "error")


# ===========================================================================
# CRUD — USERS
# ===========================================================================

@app.get("/users", response_class=HTMLResponse)
async def users_page(request: Request, db: Session = Depends(get_db)):
    users = db.query(models.User).all()
    return templates.TemplateResponse(request, "users.html", {
        "users": users, "page": "users",
    })


@app.post("/users/add")
async def add_user(
    username: str = Form(...),
    password: str = Form(...),
    name: str = Form(...),
    role: str = Form(...),
    db: Session = Depends(get_db),
):
    try:
        db.add(models.User(
            username=username,
            hashed_password=hash_password(password),
            name=name,
            role=role,
        ))
        db.commit()
        return _redirect_with_msg("/users", "Pengguna berhasil ditambahkan!")
    except IntegrityError:
        db.rollback()
        return _redirect_with_msg("/users", "Gagal: Username sudah terdaftar!", "error")


@app.post("/users/edit/{user_id}")
async def edit_user(
    user_id: int,
    name: str = Form(...),
    role: str = Form(...),
    password: str = Form(""),
    db: Session = Depends(get_db),
):
    u = db.get(models.User, user_id)
    if not u:
        return _redirect_with_msg("/users", "Pengguna tidak ditemukan!", "error")
    u.name = name
    u.role = role
    if password.strip():
        u.hashed_password = hash_password(password)
    db.commit()
    return _redirect_with_msg("/users", "Data pengguna berhasil diperbarui!")


@app.post("/users/delete/{user_id}")
async def delete_user(user_id: int, db: Session = Depends(get_db)):
    u = db.get(models.User, user_id)
    if u:
        db.delete(u)
        db.commit()
        return _redirect_with_msg("/users", "Pengguna berhasil dihapus!")
    return _redirect_with_msg("/users", "Pengguna tidak ditemukan!", "error")


# ===========================================================================
# WebSocket
# ===========================================================================

@app.websocket("/ws/monitoring")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
