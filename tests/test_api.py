import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.main import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app(f"sqlite:///{tmp_path / 'test_shiptrack.db'}")
    app.config.update(TESTING=True)
    with app.test_client() as test_client:
        yield test_client


def create_shipment(client, **kwargs):
    payload = {
        "order_id": "ORD-001", "carrier": "DHL",
        "origin": "Florence, IT", "destination": "Curitiba, BR", **kwargs,
    }
    return client.post("/shipments", json=payload)


def add_event(client, shipment_id, **kwargs):
    payload = {
        "status": "in_transit", "location": "São Paulo, BR",
        "description": "Package arrived at sorting facility.",
        "notify": "user@test.com", **kwargs,
    }
    return client.post(f"/shipments/{shipment_id}/events", json=payload)


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json()["status"] == "ok"


def test_create_shipment(client):
    response = create_shipment(client)
    assert response.status_code == 201
    assert response.get_json()["status"] == "pending"
    assert response.get_json()["carrier"] == "DHL"


def test_create_shipment_missing_fields(client):
    response = client.post("/shipments", json={"order_id": "ORD-002"})
    assert response.status_code == 400
    assert "Missing fields" in response.get_json()["error"]


def test_list_shipments_with_filter_and_pagination(client):
    create_shipment(client, order_id="ORD-001")
    create_shipment(client, order_id="ORD-002")
    response = client.get("/shipments?status=pending&page=1&per_page=1")
    assert response.status_code == 200
    assert len(response.get_json()) == 1


def test_get_shipment_with_history(client):
    shipment_id = create_shipment(client).get_json()["id"]
    response = client.get(f"/shipments/{shipment_id}")
    assert response.status_code == 200
    assert len(response.get_json()["tracking_history"]) == 1


def test_get_shipment_not_found(client):
    assert client.get("/shipments/nonexistent-id").status_code == 404


def test_add_tracking_event_sends_notification(client):
    shipment_id = create_shipment(client).get_json()["id"]
    response = add_event(client, shipment_id)
    assert response.status_code == 201
    assert response.get_json()["notification"]["status"] == "sent"
    assert response.get_json()["notification"]["attempts"] == 1


def test_add_event_invalid_status(client):
    shipment_id = create_shipment(client).get_json()["id"]
    response = add_event(client, shipment_id, status="flying_through_space")
    assert response.status_code == 400


def test_event_idempotency(client):
    shipment_id = create_shipment(client).get_json()["id"]
    first = add_event(client, shipment_id, external_event_id="DHL-123")
    duplicate = add_event(client, shipment_id, external_event_id="DHL-123")
    assert first.status_code == 201
    assert duplicate.status_code == 200
    assert duplicate.get_json()["duplicate"] is True


def test_failed_notification_is_visible_and_retryable(client):
    shipment_id = create_shipment(client).get_json()["id"]
    created = add_event(client, shipment_id, notify="provider@fail.test")
    notification = created.get_json()["notification"]
    assert notification["status"] == "failed"
    assert notification["attempts"] == 1
    assert notification["last_error"] == "Notification provider unavailable"

    retry = client.post(f"/notifications/{notification['id']}/retry")
    assert retry.status_code == 200
    assert retry.get_json()["attempts"] == 2
    assert retry.get_json()["status"] == "failed"


def test_retry_stops_after_maximum_attempts(client):
    shipment_id = create_shipment(client).get_json()["id"]
    notification = add_event(client, shipment_id, notify="provider@fail.test").get_json()["notification"]
    client.post(f"/notifications/{notification['id']}/retry")
    client.post(f"/notifications/{notification['id']}/retry")
    response = client.post(f"/notifications/{notification['id']}/retry")
    assert response.status_code == 409
    assert response.get_json()["error"] == "Maximum delivery attempts reached"


def test_notifications_log_contains_delivery_state(client):
    shipment_id = create_shipment(client).get_json()["id"]
    add_event(client, shipment_id, status="out_for_delivery", notify="buyer@shop.com")
    response = client.get(f"/shipments/{shipment_id}/notifications")
    assert response.status_code == 200
    assert response.get_json()[0]["status"] == "sent"
    assert response.get_json()[0]["recipient"] == "buyer@shop.com"
