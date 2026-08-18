from datetime import datetime, timezone
import uuid

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utc_now():
    return datetime.now(timezone.utc)


def iso(value):
    if not value:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class Shipment(Base):
    __tablename__ = "shipments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    order_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    carrier: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="pending", index=True)
    origin: Mapped[str] = mapped_column(String(255), nullable=False)
    destination: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    events: Mapped[list["TrackingEvent"]] = relationship(
        back_populates="shipment", cascade="all, delete-orphan", order_by="TrackingEvent.timestamp"
    )

    def as_dict(self, include_history=False):
        data = {
            "id": self.id, "order_id": self.order_id, "carrier": self.carrier,
            "status": self.status, "origin": self.origin, "destination": self.destination,
            "created_at": iso(self.created_at), "updated_at": iso(self.updated_at),
        }
        if include_history:
            data["tracking_history"] = [event.as_dict() for event in self.events]
        return data


class TrackingEvent(Base):
    __tablename__ = "tracking_events"
    __table_args__ = (UniqueConstraint("shipment_id", "external_event_id", name="uq_shipment_external_event"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    shipment_id: Mapped[str] = mapped_column(ForeignKey("shipments.id"), nullable=False, index=True)
    external_event_id: Mapped[str | None] = mapped_column(String(150), nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    location: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)

    shipment: Mapped[Shipment] = relationship(back_populates="events")
    notifications: Mapped[list["Notification"]] = relationship(back_populates="event", cascade="all, delete-orphan")

    def as_dict(self):
        return {
            "id": self.id, "shipment_id": self.shipment_id,
            "external_event_id": self.external_event_id, "status": self.status,
            "location": self.location, "description": self.description,
            "timestamp": iso(self.timestamp),
        }


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    shipment_id: Mapped[str] = mapped_column(ForeignKey("shipments.id"), nullable=False, index=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("tracking_events.id"), nullable=False)
    channel: Mapped[str] = mapped_column(String(30), nullable=False, default="email")
    recipient: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    event: Mapped[TrackingEvent] = relationship(back_populates="notifications")

    def as_dict(self):
        return {
            "id": self.id, "shipment_id": self.shipment_id, "event_id": self.event_id,
            "event_status": self.event.status if self.event else None,
            "channel": self.channel, "recipient": self.recipient, "status": self.status,
            "attempts": self.attempts, "last_error": self.last_error,
            "created_at": iso(self.created_at), "sent_at": iso(self.sent_at),
        }
