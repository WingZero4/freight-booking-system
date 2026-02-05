# MVP Database Schema

## Overview

Simplified database for MVP proof of concept. Ocean FCL bookings only.

## Tables (6 total)

| Table | Purpose | Records (MVP) |
|-------|---------|---------------|
| customers | Shipper companies | 5-10 |
| user_profiles | User accounts | 10-20 |
| locations | Port codes | 8 (pre-loaded) |
| container_types | Container specs | 5 (pre-loaded) |
| bookings | FCL bookings | 50-100 |
| booking_items | Cargo items | 200-500 |

## Entity Relationship

```
customers (1) ──── (*) user_profiles
    │
    │
    └──── (*) bookings ──── (*) booking_items
                │
                │
          locations (origin/destination)
                │
          container_types
```

## Schema File

- [mvp_schema.sql](mvp_schema.sql) - Complete MVP schema with sample data

## Quick Setup

```sql
-- Run in SQL Server Management Studio
CREATE DATABASE FreightBookingMVP;
GO
USE FreightBookingMVP;
GO
-- Then run mvp_schema.sql
```
