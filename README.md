# Freight Booking System - MVP (Version 2)

> **Proof of Concept** - Minimum Viable Product for management review

## MVP Scope

A simplified booking portal for Ocean FCL shipments only. Designed to be built quickly to demonstrate core functionality.

### In Scope (MVP)
- Customer login (email/password)
- Ocean FCL booking creation
- Cargo item entry
- Container selection
- Document upload
- Simple status tracking (Draft → Submitted → Confirmed)
- Basic email notifications
- Admin dashboard for operations team

### Out of Scope (Future Phases)
- Multi-modal support (LCL, Air, Road) → Phase 2
- Approval workflows → Phase 2
- EDI carrier integration → Phase 3
- Advanced reporting → Phase 3

## Technology Stack (Simplified)

| Component | Technology |
|-----------|------------|
| Backend | Python 3.11 / Django 4.2 / DRF |
| Database | SQL Server |
| Frontend | React (basic UI) |
| Auth | Django session auth (JWT later) |
| File Storage | Local filesystem (Azure Blob later) |
| Email | Django email (console for dev) |

## Quick Start

```bash
# Backend
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver

# Frontend
cd frontend
npm install
npm start
```

## Database (4 tables for MVP)

```
customers        → Company info
users            → Login credentials
bookings         → Ocean FCL bookings
booking_items    → Cargo line items
```

## API Endpoints (MVP)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /api/auth/login/ | Login |
| GET | /api/bookings/ | List my bookings |
| POST | /api/bookings/ | Create booking |
| GET | /api/bookings/{id}/ | Booking details |
| PATCH | /api/bookings/{id}/ | Update booking |
| POST | /api/bookings/{id}/submit/ | Submit to ops |
| POST | /api/bookings/{id}/items/ | Add cargo item |

## Timeline (1-Week Sprint)

| Day | Deliverable |
|-----|-------------|
| 1 | Django + models + admin |
| 2 | API endpoints |
| 3 | Customer UI (HTML forms) |
| 4 | Integration + bug fixes |
| 5 | Demo ready |

## Demo Scenarios

1. **Customer creates booking**
   - Login → New Booking → Add cargo → Select container → Submit

2. **Operations confirms booking**
   - Admin login → View submissions → Update status → Customer notified

---

*Full system documentation available on `master` branch*
