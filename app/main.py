import logging
import os

from flask import Flask, jsonify, request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.database import configure_database, get_session, init_db
from app.models import Notification, Shipment, TrackingEvent, iso, utc_now
from app.notifications import NotificationDeliveryError, attempt_delivery


VALID_STATUSES = {"pending", "picked_up", "in_transit", "out_for_delivery", "delivered", "failed"}


def create_app(database_url=None):
    application = Flask(__name__)
    configure_database(database_url)
    init_db()

    @application.post("/shipments")
    def create_shipment():
        data = request.get_json(silent=True) or {}
        required = ["order_id", "carrier", "origin", "destination"]
        missing = [field for field in required if not data.get(field)]
        if missing:
            return jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 400

        with get_session() as session:
            shipment = Shipment(
                order_id=data["order_id"], carrier=data["carrier"],
                origin=data["origin"], destination=data["destination"]
            )
            shipment.events.append(TrackingEvent(
                status="pending", location=data["origin"],
                description="Shipment registered in the system."
            ))
            session.add(shipment)
            session.commit()
            return jsonify(shipment.as_dict()), 201

    @application.get("/shipments")
    def list_shipments():
        status_filter = request.args.get("status")
        page = max(request.args.get("page", 1, type=int), 1)
        per_page = min(max(request.args.get("per_page", 50, type=int), 1), 100)
        statement = select(Shipment).order_by(Shipment.created_at.desc())
        if status_filter:
            statement = statement.where(Shipment.status == status_filter)
        statement = statement.offset((page - 1) * per_page).limit(per_page)
        with get_session() as session:
            shipments = session.scalars(statement).all()
            return jsonify([shipment.as_dict() for shipment in shipments])

    @application.get("/shipments/<shipment_id>")
    def get_shipment(shipment_id):
        with get_session() as session:
            shipment = session.get(Shipment, shipment_id)
            if not shipment:
                return jsonify({"error": "Shipment not found"}), 404
            return jsonify(shipment.as_dict(include_history=True))

    @application.post("/shipments/<shipment_id>/events")
    def add_event(shipment_id):
        data = request.get_json(silent=True) or {}
        status = data.get("status")
        if status not in VALID_STATUSES:
            return jsonify({"error": f"Invalid status. Valid options: {sorted(VALID_STATUSES)}"}), 400

        with get_session() as session:
            shipment = session.get(Shipment, shipment_id)
            if not shipment:
                return jsonify({"error": "Shipment not found"}), 404

            external_event_id = data.get("external_event_id")
            if external_event_id:
                existing = session.scalar(select(TrackingEvent).where(
                    TrackingEvent.shipment_id == shipment_id,
                    TrackingEvent.external_event_id == external_event_id,
                ))
                if existing:
                    response = existing.as_dict()
                    response["duplicate"] = True
                    return jsonify(response), 200

            event = TrackingEvent(
                shipment_id=shipment_id, external_event_id=external_event_id,
                status=status, location=data.get("location"), description=data.get("description")
            )
            shipment.status = status
            shipment.updated_at = utc_now()
            session.add(event)
            try:
                session.flush()
            except IntegrityError:
                session.rollback()
                return jsonify({"error": "Duplicate tracking event"}), 409

            notification = Notification(
                shipment_id=shipment_id, event_id=event.id,
                channel=data.get("channel", "email"),
                recipient=data.get("notify", "customer@example.com"),
            )
            session.add(notification)
            session.flush()
            attempt_delivery(notification)
            session.commit()

            return jsonify({
                **event.as_dict(), "notification": notification.as_dict(),
                "notification_sent_to": notification.recipient,
            }), 201

    @application.get("/shipments/<shipment_id>/notifications")
    def get_notifications(shipment_id):
        with get_session() as session:
            rows = session.scalars(
                select(Notification)
                .where(Notification.shipment_id == shipment_id)
                .order_by(Notification.created_at.asc())
            ).all()
            return jsonify([notification.as_dict() for notification in rows])

    @application.post("/notifications/<int:notification_id>/retry")
    def retry_notification(notification_id):
        with get_session() as session:
            notification = session.get(Notification, notification_id)
            if not notification:
                return jsonify({"error": "Notification not found"}), 404
            try:
                attempt_delivery(notification)
            except NotificationDeliveryError as error:
                return jsonify({"error": str(error), **notification.as_dict()}), 409
            session.commit()
            return jsonify(notification.as_dict()), 200

    @application.get("/health")
    def health():
        try:
            with get_session() as session:
                session.execute(select(1))
            return jsonify({"status": "ok", "timestamp": iso(utc_now())})
        except Exception:
            logging.exception("Database health check failed")
            return jsonify({"status": "unhealthy"}), 503

    return application


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=os.getenv("FLASK_DEBUG") == "1")
