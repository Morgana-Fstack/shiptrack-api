# ShipTrack API 📦

A lightweight REST API for shipment tracking and notifications, built with Python and SQLite.

Inspired by real-world logistics challenges — tracking high-volume shipment data across multiple carriers, keeping customers informed at every step.

---

## Why this project?

Shipping platforms need to answer one question reliably: *"Where is my order?"*

This API models the core of that problem:
- How do you structure shipment data so it's queryable and auditable?
- How do you record tracking events without losing history?
- How do you trigger notifications at the right moment?

The schema reflects those decisions deliberately — separate tables for shipments, events, and notifications, so each concern has a clean boundary.

---

## Tech Stack

- **Python 3.11+**
- **Flask** — lightweight HTTP layer
- **SQLite** — relational database (swap for PostgreSQL in production)
- **pytest** — full test coverage

---

## Data Model

```
shipments
  id (PK, UUID)
  order_id
  carrier
  status         → pending | picked_up | in_transit | out_for_delivery | delivered | failed
  origin
  destination
  created_at
  updated_at

tracking_events
  id (PK, autoincrement)
  shipment_id    → FK shipments.id
  status
  location
  description
  timestamp

notifications
  id (PK, autoincrement)
  shipment_id    → FK shipments.id
  event_id       → FK tracking_events.id
  channel        → email | sms | webhook
  recipient
  sent_at
```

Each shipment update creates a tracking event, which in turn triggers a notification — keeping a full audit trail of what happened and when.

---

## Getting Started

```bash
# 1. Clone the repo
git clone https://github.com/Morgana-Fstack/shiptrack-api.git
cd shiptrack-api

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the API
python app/main.py
```

The server starts at `http://localhost:5000`.

---

## API Reference

### Health check
```
GET /health
```

---

### Shipments

**Create a shipment**
```
POST /shipments
Content-Type: application/json

{
  "order_id": "ORD-2024-001",
  "carrier": "DHL",
  "origin": "Florence, IT",
  "destination": "Curitiba, BR"
}
```

**List all shipments**
```
GET /shipments
GET /shipments?status=in_transit
```

**Get shipment + full tracking history**
```
GET /shipments/{shipment_id}
```

---

### Tracking Events

**Push a new status update**
```
POST /shipments/{shipment_id}/events
Content-Type: application/json

{
  "status": "in_transit",
  "location": "São Paulo, BR",
  "description": "Package arrived at sorting facility.",
  "notify": "customer@example.com"
}
```

Valid status values: `pending` → `picked_up` → `in_transit` → `out_for_delivery` → `delivered` | `failed`

---

### Notifications

**Get notification log for a shipment**
```
GET /shipments/{shipment_id}/notifications
```

---

## Running Tests

```bash
pytest tests/ -v
```

---

## Design Decisions

**Why SQLite?** Zero setup for local development. The schema is fully compatible with PostgreSQL — swap the connection string and it runs in production.

**Why separate the `tracking_events` table?** Mutating the shipment status in place would lose history. A separate events table makes the full timeline queryable and auditable — which matters when customers dispute a delivery.

**Why log notifications as a table?** So you can answer: *"Was the customer notified about this event?"* — critical for debugging and compliance.

---

## Author

**Morgana Petterle da Cunha**  
Full Stack Developer  
[linkedin.com/in/morgana-petterle](https://linkedin.com/in/morgana-petterle) · [github.com/Morgana-Fstack](https://github.com/Morgana-Fstack)
