# API Documentation

## Overview

The Freight Booking Management System exposes a RESTful API built with Django REST Framework. All endpoints use JSON for request/response bodies and JWT for authentication.

## Base URL

```
Development: http://localhost:8000/api/v1/
Production:  https://api.yourcompany.com/api/v1/
```

## Authentication

### Obtain Token
```http
POST /api/v1/auth/login/
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "your-password"
}
```

Response:
```json
{
  "access": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "refresh": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "user": {
    "id": "uuid",
    "email": "user@example.com",
    "role": "OPERATOR"
  }
}
```

### Using Token
Include the access token in the Authorization header:
```http
Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...
```

### Refresh Token
```http
POST /api/v1/auth/refresh/
Content-Type: application/json

{
  "refresh": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
}
```

## Response Format

### Success Response
```json
{
  "success": true,
  "data": { ... },
  "meta": {
    "timestamp": "2024-01-15T10:30:00Z",
    "request_id": "req-abc123"
  }
}
```

### List Response (Paginated)
```json
{
  "success": true,
  "data": [ ... ],
  "meta": {
    "total": 150,
    "page": 1,
    "page_size": 50,
    "total_pages": 3,
    "next": "/api/v1/bookings/?page=2",
    "previous": null
  }
}
```

### Error Response
```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid booking data",
    "details": {
      "cargo_ready_date": ["Date must be in the future"]
    }
  },
  "meta": {
    "timestamp": "2024-01-15T10:30:00Z",
    "request_id": "req-abc123"
  }
}
```

## Endpoints

### Bookings

#### List Bookings
```http
GET /api/v1/bookings/
```

Query Parameters:
| Parameter | Type | Description |
|-----------|------|-------------|
| status | string | Filter by status (DRAFT, PENDING_APPROVAL, etc.) |
| transport_mode | string | Filter by mode (OCEAN_FCL, AIR, etc.) |
| customer_id | uuid | Filter by customer |
| cargo_ready_from | date | Filter by cargo ready date (from) |
| cargo_ready_to | date | Filter by cargo ready date (to) |
| page | int | Page number |
| page_size | int | Items per page (max 100) |

#### Create Booking
```http
POST /api/v1/bookings/
Content-Type: application/json

{
  "transport_mode": "OCEAN_FCL",
  "origin_location_id": "uuid",
  "destination_location_id": "uuid",
  "cargo_ready_date": "2024-02-15",
  "incoterm": "FOB",
  "special_instructions": "Handle with care"
}
```

#### Get Booking Details
```http
GET /api/v1/bookings/{id}/
```

#### Update Booking
```http
PATCH /api/v1/bookings/{id}/
Content-Type: application/json

{
  "cargo_ready_date": "2024-02-20",
  "special_instructions": "Updated instructions"
}
```

#### Submit Booking
```http
POST /api/v1/bookings/{id}/submit/
```

Validates booking completeness and initiates workflow.

#### Approve Booking
```http
POST /api/v1/bookings/{id}/approve/
Content-Type: application/json

{
  "comments": "Approved for shipment"
}
```

#### Reject Booking
```http
POST /api/v1/bookings/{id}/reject/
Content-Type: application/json

{
  "comments": "Incomplete documentation"
}
```

### Booking Items

#### List Items
```http
GET /api/v1/bookings/{booking_id}/items/
```

#### Add Item
```http
POST /api/v1/bookings/{booking_id}/items/
Content-Type: application/json

{
  "commodity_description": "Electronic Components",
  "hs_code": "8542.31",
  "package_type": "CARTON",
  "package_count": 50,
  "gross_weight_kg": 250.5,
  "length_cm": 40,
  "width_cm": 30,
  "height_cm": 25
}
```

### Containers (FCL)

#### List Containers
```http
GET /api/v1/bookings/{booking_id}/containers/
```

#### Add Container
```http
POST /api/v1/bookings/{booking_id}/containers/
Content-Type: application/json

{
  "container_type_id": "uuid",
  "quantity": 2,
  "cargo_weight_kg": 15000
}
```

### Documents

#### List Documents
```http
GET /api/v1/bookings/{booking_id}/documents/
```

#### Upload Document
```http
POST /api/v1/bookings/{booking_id}/documents/
Content-Type: multipart/form-data

file: [binary]
document_type: COMMERCIAL_INVOICE
description: Invoice for shipment
```

#### Download Document
```http
GET /api/v1/bookings/{booking_id}/documents/{doc_id}/
```

Returns temporary download URL.

### Approvals

#### List Pending Approvals
```http
GET /api/v1/approvals/pending/
```

Returns bookings awaiting approval by current user.

### Master Data

#### Locations
```http
GET /api/v1/locations/
GET /api/v1/locations/search/?q=shanghai&type=SEAPORT
```

#### Carriers
```http
GET /api/v1/carriers/
GET /api/v1/carriers/?carrier_type=OCEAN
```

#### Container Types
```http
GET /api/v1/container-types/
```

#### Commodities
```http
GET /api/v1/commodities/
GET /api/v1/commodities/search/?hs_code=8542
```

## Rate Limiting

| Endpoint Type | Rate Limit |
|---------------|------------|
| Authentication | 20/minute |
| Booking Create | 100/hour |
| General API | 1000/hour |

## Error Codes

| Code | Description |
|------|-------------|
| VALIDATION_ERROR | Request validation failed |
| NOT_FOUND | Resource not found |
| PERMISSION_DENIED | Insufficient permissions |
| CONFLICT | Resource conflict (duplicate, etc.) |
| WORKFLOW_ERROR | Workflow transition not allowed |
| RATE_LIMIT_EXCEEDED | Too many requests |

## Webhooks (Future)

Planned webhook support for:
- Booking status changes
- Approval requests
- EDI confirmations received

## OpenAPI Specification

Full OpenAPI 3.0 specification available at:
```
GET /api/v1/schema/
GET /api/v1/docs/  (Swagger UI)
```
