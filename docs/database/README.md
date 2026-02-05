# Database Documentation

## Overview

The Freight Booking Management System uses SQL Server as the primary database. The schema follows these principles:

- **UUID Primary Keys**: All tables use UUIDs for globally unique identifiers
- **Soft Deletes**: Most entities use `is_active` flags instead of hard deletes
- **Audit Columns**: All tables include `created_at` and `updated_at` timestamps
- **Composition Pattern**: Modal-specific booking data uses OneToOne relationships

## Entity Relationship Diagram

```
                                    ┌──────────────┐
                                    │   Customer   │
                                    └──────┬───────┘
                                           │
                          ┌────────────────┼────────────────┐
                          │                │                │
                  ┌───────▼───────┐ ┌──────▼──────┐ ┌──────▼───────┐
                  │     User      │ │  Workflow   │ │   Booking    │
                  │   Profile     │ │   Config    │ │              │
                  └───────────────┘ └─────────────┘ └──────┬───────┘
                                                          │
              ┌───────────────┬───────────────┬───────────┼───────────┐
              │               │               │           │           │
      ┌───────▼──────┐┌───────▼──────┐┌───────▼──────┐┌───▼───┐┌─────▼─────┐
      │ BookingItem  ││BookingOcean  ││ BookingAir   ││ Route ││ Document  │
      │              ││    FCL       ││              ││       ││           │
      └──────────────┘└──────────────┘└──────────────┘└───────┘└───────────┘
```

## Schema Files

- [01_core_tables.sql](schema/01_core_tables.sql) - Customer, User, Audit tables
- [02_master_data.sql](schema/02_master_data.sql) - Locations, Carriers, Commodities
- [03_booking_tables.sql](schema/03_booking_tables.sql) - Booking core and items
- [04_modal_specific.sql](schema/04_modal_specific.sql) - FCL, LCL, Air, Road details
- [05_workflow_tables.sql](schema/05_workflow_tables.sql) - Workflow configuration
- [06_edi_tables.sql](schema/06_edi_tables.sql) - EDI transaction tracking
- [07_indexes.sql](schema/07_indexes.sql) - Performance indexes

## Table Summary

### Core Tables
| Table | Description | Records Est. |
|-------|-------------|--------------|
| customers | Shipper/consignee companies | 1K-10K |
| user_profiles | Extended user data | 5K-50K |
| audit_log | Immutable change history | 1M+ |

### Reference Data
| Table | Description | Records Est. |
|-------|-------------|--------------|
| locations | Ports, airports, addresses | 10K+ |
| carriers | Shipping lines, airlines | 500+ |
| commodities | HS codes, DG classes | 5K+ |
| container_types | Container specifications | 50+ |

### Transactional
| Table | Description | Records Est. |
|-------|-------------|--------------|
| bookings | Main booking records | 100K+ |
| booking_items | Cargo line items | 500K+ |
| booking_containers | FCL containers | 200K+ |
| booking_documents | File attachments | 500K+ |

### Workflow
| Table | Description | Records Est. |
|-------|-------------|--------------|
| workflow_configs | Approval rule sets | 1K |
| workflow_steps | Approval step definitions | 5K |
| booking_approvals | Approval records | 100K+ |

### EDI
| Table | Description | Records Est. |
|-------|-------------|--------------|
| edi_partners | Trading partner config | 100+ |
| edi_control_numbers | ISA/GS/ST sequences | 100+ |
| edi_transactions | Parsed EDI records | 500K+ |

## Naming Conventions

- Tables: lowercase, snake_case, plural (e.g., `booking_items`)
- Columns: lowercase, snake_case (e.g., `cargo_ready_date`)
- Primary Keys: `id` (UUID)
- Foreign Keys: `{table}_id` (e.g., `customer_id`)
- Timestamps: `{action}_at` (e.g., `created_at`, `approved_at`)
- Booleans: `is_{state}` or `has_{state}` (e.g., `is_active`, `has_dg`)
