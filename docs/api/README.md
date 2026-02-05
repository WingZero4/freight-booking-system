# MVP API Documentation

## Base URL

```
http://localhost:8000/api/
```

## Authentication

Using Django session auth for MVP (JWT in full version).

```http
POST /api/auth/login/
Content-Type: application/json

{
  "username": "user@example.com",
  "password": "password"
}
```

## Endpoints

### Bookings

#### List My Bookings
```http
GET /api/bookings/
```

Response:
```json
{
  "results": [
    {
      "id": 1,
      "booking_number": "BK-202402-0001",
      "status": "DRAFT",
      "origin_port": "CNSHA",
      "destination_port": "USLAX",
      "cargo_ready_date": "2024-02-15",
      "container_type": "40HC",
      "container_count": 2,
      "created_at": "2024-02-01T10:00:00Z"
    }
  ]
}
```

#### Create Booking
```http
POST /api/bookings/
Content-Type: application/json

{
  "origin_port_id": 1,
  "destination_port_id": 4,
  "cargo_ready_date": "2024-02-15",
  "container_type_id": 3,
  "container_count": 2,
  "special_instructions": "Handle with care"
}
```

#### Get Booking Details
```http
GET /api/bookings/{id}/
```

#### Update Booking (Draft only)
```http
PATCH /api/bookings/{id}/
Content-Type: application/json

{
  "cargo_ready_date": "2024-02-20"
}
```

#### Submit Booking
```http
POST /api/bookings/{id}/submit/
```

Changes status from DRAFT to SUBMITTED.

### Booking Items

#### Add Cargo Item
```http
POST /api/bookings/{id}/items/
Content-Type: application/json

{
  "description": "Electronic components",
  "package_type": "CARTON",
  "quantity": 100,
  "weight_kg": 500
}
```

#### List Cargo Items
```http
GET /api/bookings/{id}/items/
```

### Reference Data

#### List Ports
```http
GET /api/ports/
```

#### List Container Types
```http
GET /api/container-types/
```

## Status Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 201 | Created |
| 400 | Bad Request |
| 401 | Not Authenticated |
| 403 | Permission Denied |
| 404 | Not Found |

## Booking Status Flow

```
DRAFT ──submit──▶ SUBMITTED ──confirm──▶ CONFIRMED
                       │
                       └──cancel──▶ CANCELLED
```
