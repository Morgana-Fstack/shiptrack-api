from flask import Flask, jsonify, request
from datetime import datetime, timezone
import sqlite3
import uuid
import os

app = Flask(__name__)
DB_PATH = os.path.join(os.path.dirname(__file__), "shiptrack.db")


# ── Database setup ────────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS shipments (
            id          TEXT PRIMARY KEY,
            order_id    TEXT NOT NULL,
            carrier     TEXT NOT NULL,
            status      TEXT NOT NULL DEFAULT 'pending',
            origin      TEXT NOT NULL,
            destination TEXT NOT NULL,
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS tracking_events (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            shipment_id TEXT NOT NULL,
            status      TEXT NOT NULL,
            location    TEXT,
            description TEXT,
            timestamp   TEXT NOT NULL,
            FOREIGN KEY (shipment_id) REFERENCES shipments(id)
        );

        CREATE TABLE IF NOT EXISTS notifications (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            shipment_id TEXT NOT NULL,
            event_id    INTEGER NOT NULL,
            channel     TEXT NOT NULL,
            recipient   TEXT NOT NULL,
            sent_at     TEXT NOT NULL,
            FOREIGN KEY (shipment_id) REFERENCES shipments(id),
            FOREIGN KEY (event_id)    REFERENCES tracking_events(id)
        );
    """)
    conn.commit()
    conn.close()


# ── Helpers ───────────────────────────────────────────────────────────────────

VALID_STATUSES = ["pending", "picked_up", "in_transit", "out_for_delivery", "delivered", "failed"]

def now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def row_to_dict(row):
    return dict(row) if row else None


# ── Routes: Shipments ─────────────────────────────────────────────────────────

@app.route("/shipments", methods=["POST"])
def create_shipment():
    """Create a new shipment."""
    data = request.get_json(silent=True) or {}
    required = ["order_id", "carrier", "origin", "destination"]
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 400

    shipment_id = str(uuid.uuid4())
    ts = now()

    conn = get_db()
    conn.execute(
        """INSERT INTO shipments (id, order_id, carrier, status, origin, destination, created_at, updated_at)
           VALUES (?, ?, ?, 'pending', ?, ?, ?, ?)""",
        (shipment_id, data["order_id"], data["carrier"], data["origin"], data["destination"], ts, ts)
    )
    # Auto-create the first tracking event
    cursor = conn.execute(
        """INSERT INTO tracking_events (shipment_id, status, location, description, timestamp)
           VALUES (?, 'pending', ?, 'Shipment registered in the system.', ?)""",
        (shipment_id, data["origin"], ts)
    )
    conn.commit()
    conn.close()

    return jsonify({
        "id": shipment_id,
        "order_id": data["order_id"],
        "carrier": data["carrier"],
        "status": "pending",
        "origin": data["origin"],
        "destination": data["destination"],
        "created_at": ts
    }), 201


@app.route("/shipments", methods=["GET"])
def list_shipments():
    """List all shipments, optionally filtered by status."""
    status_filter = request.args.get("status")
    conn = get_db()
    if status_filter:
        rows = conn.execute(
            "SELECT * FROM shipments WHERE status = ? ORDER BY created_at DESC", (status_filter,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM shipments ORDER BY created_at DESC"
        ).fetchall()
    conn.close()
    return jsonify([row_to_dict(r) for r in rows])


@app.route("/shipments/<shipment_id>", methods=["GET"])
def get_shipment(shipment_id):
    """Get a shipment and its full tracking history."""
    conn = get_db()
    shipment = conn.execute(
        "SELECT * FROM shipments WHERE id = ?", (shipment_id,)
    ).fetchone()
    if not shipment:
        conn.close()
        return jsonify({"error": "Shipment not found"}), 404

    events = conn.execute(
        "SELECT * FROM tracking_events WHERE shipment_id = ? ORDER BY timestamp ASC",
        (shipment_id,)
    ).fetchall()
    conn.close()

    result = row_to_dict(shipment)
    result["tracking_history"] = [row_to_dict(e) for e in events]
    return jsonify(result)


# ── Routes: Tracking events ───────────────────────────────────────────────────

@app.route("/shipments/<shipment_id>/events", methods=["POST"])
def add_event(shipment_id):
    """Push a new tracking event and trigger a notification."""
    conn = get_db()
    shipment = conn.execute(
        "SELECT * FROM shipments WHERE id = ?", (shipment_id,)
    ).fetchone()
    if not shipment:
        conn.close()
        return jsonify({"error": "Shipment not found"}), 404

    data = request.get_json(silent=True) or {}
    status = data.get("status")
    if status not in VALID_STATUSES:
        conn.close()
        return jsonify({"error": f"Invalid status. Valid options: {VALID_STATUSES}"}), 400

    ts = now()

    # Insert tracking event
    cursor = conn.execute(
        """INSERT INTO tracking_events (shipment_id, status, location, description, timestamp)
           VALUES (?, ?, ?, ?, ?)""",
        (shipment_id, status, data.get("location"), data.get("description"), ts)
    )
    event_id = cursor.lastrowid

    # Update shipment status
    conn.execute(
        "UPDATE shipments SET status = ?, updated_at = ? WHERE id = ?",
        (status, ts, shipment_id)
    )

    # Simulate notification dispatch
    recipient = data.get("notify", "customer@example.com")
    conn.execute(
        """INSERT INTO notifications (shipment_id, event_id, channel, recipient, sent_at)
           VALUES (?, ?, 'email', ?, ?)""",
        (shipment_id, event_id, recipient, ts)
    )

    conn.commit()
    conn.close()

    return jsonify({
        "event_id": event_id,
        "shipment_id": shipment_id,
        "status": status,
        "location": data.get("location"),
        "description": data.get("description"),
        "timestamp": ts,
        "notification_sent_to": recipient
    }), 201


# ── Routes: Notifications ─────────────────────────────────────────────────────

@app.route("/shipments/<shipment_id>/notifications", methods=["GET"])
def get_notifications(shipment_id):
    """Get all notifications sent for a shipment."""
    conn = get_db()
    rows = conn.execute(
        """SELECT n.*, e.status as event_status
           FROM notifications n
           JOIN tracking_events e ON n.event_id = e.id
           WHERE n.shipment_id = ?
           ORDER BY n.sent_at ASC""",
        (shipment_id,)
    ).fetchall()
    conn.close()
    return jsonify([row_to_dict(r) for r in rows])


# ── Health check ──────────────────────────────────────────────────────────────

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "timestamp": now()})


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000)
