from datetime import datetime, timezone, timedelta
from .database import SessionLocal
from . import models
from .auth import hash_password


def seed_database():
    """Seed database with initial sample data if tables are empty."""
    db = SessionLocal()
    try:
        # --- Users ---
        if db.query(models.User).count() == 0:
            users = [
                models.User(
                    username="admin",
                    hashed_password=hash_password("admin123"),
                    name="Administrator",
                    role="ADMIN",
                ),
                models.User(
                    username="perawat",
                    hashed_password=hash_password("perawat123"),
                    name="Suster Rina",
                    role="PERAWAT",
                ),
                models.User(
                    username="teknisi",
                    hashed_password=hash_password("teknisi123"),
                    name="Budi Teknisi",
                    role="TEKNISI",
                ),
            ]
            db.add_all(users)
            db.commit()

        # --- Rooms ---
        if db.query(models.Room).count() == 0:
            rooms = [
                models.Room(name="Melati 101", capacity=4),
                models.Room(name="Melati 102", capacity=2),
                models.Room(name="Mawar 201", capacity=4),
                models.Room(name="Mawar 202", capacity=3),
                models.Room(name="Anggrek 301", capacity=2),
            ]
            db.add_all(rooms)
            db.commit()

        # --- Patients ---
        if db.query(models.Patient).count() == 0:
            rooms = db.query(models.Room).all()
            patients = [
                models.Patient(name="Budi Santoso", medical_id="RM-2026-001", room_id=rooms[0].id),
                models.Patient(name="Siti Aminah", medical_id="RM-2026-002", room_id=rooms[0].id),
                models.Patient(name="Ahmad Fauzi", medical_id="RM-2026-003", room_id=rooms[1].id),
                models.Patient(name="Dewi Lestari", medical_id="RM-2026-004", room_id=rooms[2].id),
                models.Patient(name="Rini Wulandari", medical_id="RM-2026-005", room_id=rooms[2].id),
                models.Patient(name="Hendra Wijaya", medical_id="RM-2026-006", room_id=rooms[3].id),
                models.Patient(name="Nurul Hidayah", medical_id="RM-2026-007", room_id=rooms[4].id),
            ]
            db.add_all(patients)
            db.commit()

        # --- Infusions ---
        if db.query(models.Infusion).count() == 0:
            patients = db.query(models.Patient).all()
            now = datetime.now(timezone.utc)
            infusions = [
                models.Infusion(
                    patient_id=patients[0].id,
                    medication_name="NaCl 0.9%",
                    initial_volume=500.0,
                    current_volume=420.0,
                    target_flow_rate=100.0,
                    status="ACTIVE",
                    started_at=now - timedelta(hours=1),
                ),
                models.Infusion(
                    patient_id=patients[1].id,
                    medication_name="Ringer Lactate",
                    initial_volume=500.0,
                    current_volume=45.0,  # hampir habis
                    target_flow_rate=60.0,
                    status="ACTIVE",
                    started_at=now - timedelta(hours=6),
                ),
                models.Infusion(
                    patient_id=patients[2].id,
                    medication_name="Dextrose 5%",
                    initial_volume=250.0,
                    current_volume=180.0,
                    target_flow_rate=40.0,
                    status="ACTIVE",
                    started_at=now - timedelta(hours=2),
                ),
                models.Infusion(
                    patient_id=patients[3].id,
                    medication_name="NaCl 0.9%",
                    initial_volume=500.0,
                    current_volume=350.0,
                    target_flow_rate=80.0,
                    status="ACTIVE",
                    started_at=now - timedelta(hours=2),
                ),
                models.Infusion(
                    patient_id=patients[4].id,
                    medication_name="Aminofluid",
                    initial_volume=500.0,
                    current_volume=12.0,  # kritis!
                    target_flow_rate=50.0,
                    status="ACTIVE",
                    started_at=now - timedelta(hours=9),
                ),
                models.Infusion(
                    patient_id=patients[5].id,
                    medication_name="Ringer Lactate",
                    initial_volume=500.0,
                    current_volume=0.0,
                    target_flow_rate=100.0,
                    status="COMPLETED",
                    started_at=now - timedelta(hours=10),
                    ended_at=now - timedelta(hours=5),
                ),
                models.Infusion(
                    patient_id=patients[6].id,
                    medication_name="Metronidazole",
                    initial_volume=100.0,
                    current_volume=70.0,
                    target_flow_rate=30.0,
                    status="PAUSED",
                    started_at=now - timedelta(hours=1),
                ),
            ]
            db.add_all(infusions)
            db.commit()

            # --- Monitoring Data (history) ---
            for inf in infusions:
                if inf.status in ("COMPLETED", "ACTIVE"):
                    for i in range(5):
                        vol = inf.initial_volume - (inf.initial_volume - inf.current_volume) * (i + 1) / 5
                        mon = models.MonitoringData(
                            infusion_id=inf.id,
                            volume=round(max(0, vol), 1),
                            flow_rate=inf.target_flow_rate,
                            alarm_active=vol < 50,
                            alarm_reason="Volume rendah" if vol < 50 else None,
                            timestamp=inf.started_at + timedelta(hours=i),
                        )
                        db.add(mon)
            db.commit()

    finally:
        db.close()
