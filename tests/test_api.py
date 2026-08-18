import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.main import app, init_db


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Set up a fresh test database for each test."""
    test_db = str(tmp_path / "test_shiptrack.db")
    monkeypatch.setattr("app.main.DB_PATH", test_db)
    with app.test_client() as client:
        with app.app_context():
            init_db()
        yield client


def create_shipment(client, **kwargs):
    payload = {
        "order_id": "ORD-001",
        "carrier": "DHL",
        "origin": "Florence, IT",
        "destination": "Curitiba, BR",
        **kwargs
    }
    return client.post("/shipments", json=payload)


# ── Health ────────────────────────────────────────────────────────────────────

def test_health(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.get_json()["status"] == "ok"


# ── Shipments ─────────────────────────────────────────────────────────────────

def test_create_shipment(client):
    res = create_shipment(client)
    assert res.status_code == 201
    data = res.get_json()
    assert data["status"] == "pending"
    assert data["carrier"] == "DHL"
    assert "id" in data


def test_create_shipment_missing_fields(client):
    res = client.post("/shipments", json={"order_id": "ORD-002"})
    assert res.status_code == 400
    assert "Missing fields" in res.get_json()["error"]


def test_list_shipments(client):
    create_shipment(client, order_id="ORD-001")
    create_shipment(client, order_id="ORD-002")
    res = client.get("/shipments")
    assert res.status_code == 200
    assert len(res.get_json()) == 2


def test_list_shipments_filter_by_status(client):
    create_shipment(client, order_id="ORD-001")
    res = client.get("/shipments?status=pending")
    assert res.status_code == 200
    assert all(s["status"] == "pending" for s in res.get_json())


def test_get_shipment_with_history(client):
    shipment_id = create_shipment(client).get_json()["id"]
    res = client.get(f"/shipments/{shipment_id}")
    assert res.status_code == 200
    data = res.get_json()
    assert "tracking_history" in data
    assert len(data["tracking_history"]) == 1  # auto-created on registration


def test_get_shipment_not_found(client):
    res = client.get("/shipments/nonexistent-id")
    assert res.status_code == 404


# ── Tracking events ───────────────────────────────────────────────────────────

def test_add_tracking_event(client):
    shipment_id = create_shipment(client).get_json()["id"]
    res = client.post(f"/shipments/{shipment_id}/events", json={
        "status": "in_transit",
        "location": "São Paulo, BR",
        "description": "Package arrived at sorting facility.",
        "notify": "user@test.com"
    })
    assert res.status_code == 201
    data = res.get_json()
    assert data["status"] == "in_transit"
    assert data["notification_sent_to"] == "user@test.com"


def test_add_event_invalid_status(client):
    shipment_id = create_shipment(client).get_json()["id"]
    res = client.post(f"/shipments/{shipment_id}/events", json={
        "status": "flying_through_space"
    })
    assert res.status_code == 400


def test_status_updates_on_event(client):
    shipment_id = create_shipment(client).get_json()["id"]
    client.post(f"/shipments/{shipment_id}/events", json={"status": "delivered"})
    updated = client.get(f"/shipments/{shipment_id}").get_json()
    assert updated["status"] == "delivered"


# ── Notifications ─────────────────────────────────────────────────────────────

def test_notifications_logged(client):
    shipment_id = create_shipment(client).get_json()["id"]
    client.post(f"/shipments/{shipment_id}/events", json={
        "status": "out_for_delivery",
        "notify": "buyer@shop.com"
    })
    res = client.get(f"/shipments/{shipment_id}/notifications")
    assert res.status_code == 200
    notifs = res.get_json()
    assert len(notifs) == 1
    assert notifs[0]["recipient"] == "buyer@shop.com"
