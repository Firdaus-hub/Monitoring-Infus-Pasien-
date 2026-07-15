from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime, timezone

from .database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    name = Column(String, nullable=False)
    role = Column(String, nullable=False)  # ADMIN, PERAWAT, TEKNISI


class Room(Base):
    __tablename__ = "rooms"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    capacity = Column(Integer, default=1)

    patients = relationship("Patient", back_populates="room", cascade="all, delete-orphan")


class Patient(Base):
    __tablename__ = "patients"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    medical_id = Column(String, unique=True, index=True, nullable=False)
    room_id = Column(Integer, ForeignKey("rooms.id"), nullable=False)

    room = relationship("Room", back_populates="patients")
    infusions = relationship("Infusion", back_populates="patient", cascade="all, delete-orphan")


class Infusion(Base):
    __tablename__ = "infusions"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    medication_name = Column(String, nullable=False)
    initial_volume = Column(Float, nullable=False)   # volume awal (ml)
    current_volume = Column(Float, nullable=False)    # volume saat ini (ml)
    target_flow_rate = Column(Float, nullable=False)  # ml/jam
    status = Column(String, default="ACTIVE")         # ACTIVE, COMPLETED, PAUSED, ERROR
    started_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    ended_at = Column(DateTime, nullable=True)

    patient = relationship("Patient", back_populates="infusions")
    monitorings = relationship("MonitoringData", back_populates="infusion", cascade="all, delete-orphan")


class MonitoringData(Base):
    __tablename__ = "monitoring_data"

    id = Column(Integer, primary_key=True, index=True)
    infusion_id = Column(Integer, ForeignKey("infusions.id"), nullable=False)
    volume = Column(Float, nullable=False)
    flow_rate = Column(Float, nullable=False)
    estimated_empty = Column(DateTime, nullable=True)
    alarm_active = Column(Boolean, default=False)
    alarm_reason = Column(String, nullable=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    infusion = relationship("Infusion", back_populates="monitorings")
