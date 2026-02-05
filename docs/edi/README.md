# EDI ANSI X12 Specification

## Overview

The Freight Booking Management System uses EDI ANSI X12 standard for automated data exchange with carriers. This document outlines the supported transaction sets, message structures, and integration requirements.

## Supported Transaction Sets

| Transaction | Name | Direction | Purpose |
|-------------|------|-----------|---------|
| X12 300 | Reservation (Booking Request) | Outbound | Ocean booking request to carrier |
| X12 301 | Confirmation (Ocean) | Inbound | Carrier booking confirmation |
| X12 304 | Shipping Instructions | Outbound | Bill of lading instructions |
| X12 204 | Motor Carrier Load Tender | Outbound | Trucking booking request |
| X12 990 | Response to Load Tender | Inbound | Trucking acceptance/rejection |
| X12 214 | Shipment Status Message | Inbound | Tracking/milestone updates |
| X12 210 | Freight Invoice | Inbound | Carrier billing |
| X12 997 | Functional Acknowledgment | Both | EDI receipt confirmation |

## Communication Methods

### Primary: AS2 (Applicability Statement 2)
- Secure, reliable message delivery
- Non-repudiation via digital signatures
- Automatic MDN (Message Disposition Notification)
- HTTPS-based transport

### Fallback: SFTP
- Secure file transfer
- Polling-based or push model
- Directory structure: `/inbound/` and `/outbound/`

## Message Structure

### Envelope Hierarchy
```
ISA - Interchange Control Header
  GS - Functional Group Header
    ST - Transaction Set Header
      [Transaction Data Segments]
    SE - Transaction Set Trailer
  GE - Functional Group Trailer
IEA - Interchange Control Trailer
```

### Control Number Management
- ISA control numbers: Sequential per trading partner
- GS control numbers: Sequential per functional group type
- ST control numbers: Sequential per transaction type
- All control numbers are tracked in `edi_control_numbers` table

## X12 300 - Ocean Booking Request

### Purpose
Request space on an ocean vessel for FCL shipments.

### Key Segments
| Segment | Purpose |
|---------|---------|
| B1 | Beginning Segment - Booking info |
| Y1 | Vessel Booking Information |
| Y2 | Container Details |
| N1/N3/N4 | Party Identification (Shipper, Consignee) |
| R4 | Port Information (POL, POD) |
| DTM | Date/Time References |
| W09 | Equipment Details |
| L5 | Commodity Description |
| L0 | Line Item Quantity/Weight |
| V1 | Vessel Identification |

### Sample Mapping
```
bookings.booking_number     → B1-02
bookings.cargo_ready_date   → DTM (qualifier 140)
customers.name              → N1-02 (qualifier SH)
locations.code (origin)     → R4-02 (qualifier L)
booking_containers.type     → Y2-01
booking_items.description   → L5-01
```

## X12 301 - Booking Confirmation

### Purpose
Carrier confirmation of ocean booking with vessel/voyage assignment.

### Key Segments
| Segment | Purpose |
|---------|---------|
| B1 | Beginning Segment - Carrier booking ref |
| Y1 | Vessel Assignment |
| Y2 | Container Assignment |
| DTM | Confirmed ETD/ETA |
| V1 | Vessel Details |

### Processing
1. Parse carrier booking reference
2. Match to internal booking by our reference or carrier ref
3. Update booking with vessel/voyage details
4. Update status to CONFIRMED
5. Generate 997 acknowledgment
6. Trigger notification to shipper

## X12 204 - Motor Carrier Load Tender

### Purpose
Request trucking services for FTL/LTL shipments.

### Key Segments
| Segment | Purpose |
|---------|---------|
| B2 | Beginning Segment |
| B2A | Set Purpose |
| L11 | Reference Numbers |
| N1/N3/N4 | Parties (Shipper, Consignee) |
| S5 | Stop-off Details |
| G62 | Date/Time |
| AT8 | Shipment Weight |
| OID | Order Information |

## X12 990 - Response to Load Tender

### Purpose
Carrier acceptance or rejection of trucking tender.

### Response Codes
- `A` - Accepted
- `D` - Declined
- `P` - Pending (counter-offer)

## X12 214 - Shipment Status

### Purpose
Tracking updates and milestone events.

### Key Segments
| Segment | Purpose |
|---------|---------|
| B10 | Beginning Segment |
| L11 | Reference Numbers |
| AT7 | Shipment Status Detail |
| MS1/MS2 | Equipment Location |

### Status Codes
| Code | Description |
|------|-------------|
| AF | Carrier Departed |
| AG | Estimated Delivery |
| D1 | Completed Unloading |
| X3 | Arrived at Pickup |
| X6 | Picked Up |

## X12 210 - Freight Invoice

### Purpose
Carrier billing for completed shipments.

### Key Segments
| Segment | Purpose |
|---------|---------|
| B3 | Beginning Segment for Invoice |
| N1/N3/N4 | Party Information |
| L5 | Description/Charges |
| L0 | Line Item Detail |
| L1 | Rate and Charges |

## X12 997 - Functional Acknowledgment

### Purpose
Acknowledge receipt and acceptance of EDI transactions.

### Acknowledgment Codes
| Code | Meaning |
|------|---------|
| A | Accepted |
| E | Accepted with Errors |
| R | Rejected |

### Error Codes
| Code | Description |
|------|-------------|
| 1 | Unrecognized Segment ID |
| 2 | Unexpected Segment |
| 3 | Missing Mandatory Segment |
| 4 | Loop Occurs Over Maximum |
| 5 | Segment Exceeds Maximum |

## Trading Partner Setup

### Required Information
1. Partner identification codes (ISA ID, GS ID)
2. Communication method and credentials
3. Supported transaction types
4. Element/segment separators
5. Test vs. production flag

### Certification Process
1. Connect to carrier's test environment
2. Exchange test transactions
3. Validate mapping accuracy
4. Complete carrier certification checklist
5. Move to production

## Error Handling

### Outbound Errors
- Retry queue with exponential backoff
- Maximum 3 retries before manual intervention
- Email alerts for persistent failures

### Inbound Errors
- Store raw file for manual review
- Generate 997 with error codes
- Log error details for troubleshooting

## Files

- [X12_300_Spec.md](X12_300_Spec.md) - Detailed 300 specification
- [X12_204_Spec.md](X12_204_Spec.md) - Detailed 204 specification
- [Sample_Messages/](Sample_Messages/) - Sample EDI files
