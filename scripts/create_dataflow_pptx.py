"""
Generate PowerPoint presentation for Freight Booking System Data Flow Diagrams
"""

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE

# Create presentation with widescreen format
prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)

# Define colors
DARK_BLUE = RGBColor(0, 51, 102)
LIGHT_BLUE = RGBColor(0, 112, 192)
GREEN = RGBColor(0, 128, 0)
ORANGE = RGBColor(255, 153, 0)
GRAY = RGBColor(128, 128, 128)


def add_title_slide(prs, title, subtitle):
    """Add a title slide"""
    slide_layout = prs.slide_layouts[6]  # Blank
    slide = prs.slides.add_slide(slide_layout)

    # Title
    title_box = slide.shapes.add_textbox(Inches(0.5), Inches(2.5), Inches(12.333), Inches(1.5))
    tf = title_box.text_frame
    p = tf.paragraphs[0]
    p.text = title
    p.font.size = Pt(44)
    p.font.bold = True
    p.font.color.rgb = DARK_BLUE
    p.alignment = PP_ALIGN.CENTER

    # Subtitle
    sub_box = slide.shapes.add_textbox(Inches(0.5), Inches(4), Inches(12.333), Inches(1))
    tf = sub_box.text_frame
    p = tf.paragraphs[0]
    p.text = subtitle
    p.font.size = Pt(24)
    p.font.color.rgb = GRAY
    p.alignment = PP_ALIGN.CENTER

    return slide


def add_section_slide(prs, title):
    """Add a section divider slide"""
    slide_layout = prs.slide_layouts[6]
    slide = prs.slides.add_slide(slide_layout)

    # Background shape
    shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, Inches(2.5), Inches(13.333), Inches(2.5))
    shape.fill.solid()
    shape.fill.fore_color.rgb = DARK_BLUE
    shape.line.fill.background()

    # Title
    title_box = slide.shapes.add_textbox(Inches(0.5), Inches(3), Inches(12.333), Inches(1.5))
    tf = title_box.text_frame
    p = tf.paragraphs[0]
    p.text = title
    p.font.size = Pt(40)
    p.font.bold = True
    p.font.color.rgb = RGBColor(255, 255, 255)
    p.alignment = PP_ALIGN.CENTER

    return slide


def add_content_slide(prs, title, content_lines, font_size=14):
    """Add a content slide with text"""
    slide_layout = prs.slide_layouts[6]
    slide = prs.slides.add_slide(slide_layout)

    # Title
    title_box = slide.shapes.add_textbox(Inches(0.5), Inches(0.3), Inches(12.333), Inches(0.8))
    tf = title_box.text_frame
    p = tf.paragraphs[0]
    p.text = title
    p.font.size = Pt(28)
    p.font.bold = True
    p.font.color.rgb = DARK_BLUE

    # Content
    content_box = slide.shapes.add_textbox(Inches(0.5), Inches(1.2), Inches(12.333), Inches(5.8))
    tf = content_box.text_frame
    tf.word_wrap = True

    for i, line in enumerate(content_lines):
        if i == 0:
            p = tf.paragraphs[0]
        else:
            p = tf.add_paragraph()
        p.text = line
        p.font.size = Pt(font_size)
        p.font.name = 'Consolas'

    return slide


def add_table_slide(prs, title, headers, rows):
    """Add a slide with a table"""
    slide_layout = prs.slide_layouts[6]
    slide = prs.slides.add_slide(slide_layout)

    # Title
    title_box = slide.shapes.add_textbox(Inches(0.5), Inches(0.3), Inches(12.333), Inches(0.8))
    tf = title_box.text_frame
    p = tf.paragraphs[0]
    p.text = title
    p.font.size = Pt(28)
    p.font.bold = True
    p.font.color.rgb = DARK_BLUE

    # Table
    num_rows = len(rows) + 1
    num_cols = len(headers)
    table = slide.shapes.add_table(num_rows, num_cols, Inches(0.5), Inches(1.3), Inches(12.333), Inches(5.5)).table

    # Set column widths
    col_width = Inches(12.333 / num_cols)
    for i in range(num_cols):
        table.columns[i].width = col_width

    # Headers
    for i, header in enumerate(headers):
        cell = table.cell(0, i)
        cell.text = header
        cell.fill.solid()
        cell.fill.fore_color.rgb = DARK_BLUE
        p = cell.text_frame.paragraphs[0]
        p.font.bold = True
        p.font.size = Pt(12)
        p.font.color.rgb = RGBColor(255, 255, 255)

    # Data rows
    for row_idx, row in enumerate(rows):
        for col_idx, value in enumerate(row):
            cell = table.cell(row_idx + 1, col_idx)
            cell.text = str(value)
            p = cell.text_frame.paragraphs[0]
            p.font.size = Pt(11)

    return slide


# =============================================================================
# CREATE PRESENTATION
# =============================================================================

# Slide 1: Title
add_title_slide(
    prs,
    "Freight Booking Management System",
    "Data Flow Architecture & EDI X12 Integration"
)

# Slide 2: Agenda
add_content_slide(prs, "Agenda", [
    "1. System Overview",
    "",
    "2. EDI X12 Transaction Sets",
    "",
    "3. System Context Diagram (Level 0)",
    "",
    "4. Data Flow Diagram (Level 1)",
    "",
    "5. Booking Lifecycle Flow",
    "",
    "6. EDI Processing Flows",
    "",
    "7. Data Stores Overview",
], font_size=20)

# Slide 3: Section - System Overview
add_section_slide(prs, "System Overview")

# Slide 4: System Overview Content
add_content_slide(prs, "System Overview", [
    "PURPOSE:",
    "  B2B booking portal for freight forwarding customers (shippers)",
    "  Submit multi-modal freight bookings with automated carrier EDI",
    "",
    "KEY CAPABILITIES:",
    "  • Multi-modal support: Ocean FCL/LCL, Air Freight, Road/Trucking",
    "  • Customer-configurable approval workflows",
    "  • EDI ANSI X12 carrier integration (AS2/SFTP)",
    "  • Document management with Azure Blob storage",
    "  • Email notifications for status changes",
    "  • Complete audit trail",
    "",
    "TECHNOLOGY STACK:",
    "  • Backend: Python/Django + Django REST Framework",
    "  • Database: SQL Server",
    "  • Frontend: React with TypeScript",
    "  • Task Queue: Celery + Redis",
], font_size=16)

# Slide 5: Section - EDI Transaction Sets
add_section_slide(prs, "EDI ANSI X12 Transaction Sets")

# Slide 6: EDI Table
add_table_slide(prs, "EDI X12 Transaction Sets Used",
    ["Transaction", "Name", "Direction", "Purpose"],
    [
        ["X12 300", "Reservation (Booking Request)", "Outbound", "Ocean booking request to carrier"],
        ["X12 301", "Confirmation (Ocean)", "Inbound", "Carrier booking confirmation"],
        ["X12 304", "Shipping Instructions", "Outbound", "Bill of lading instructions"],
        ["X12 204", "Motor Carrier Load Tender", "Outbound", "Trucking booking request"],
        ["X12 990", "Response to Load Tender", "Inbound", "Trucking acceptance/rejection"],
        ["X12 214", "Shipment Status Message", "Inbound", "Tracking/milestone updates"],
        ["X12 210", "Freight Invoice", "Inbound", "Carrier billing"],
        ["X12 997", "Functional Acknowledgment", "Both", "EDI receipt confirmation"],
    ]
)

# Slide 7: Section - System Context
add_section_slide(prs, "System Context Diagram")

# Slide 8: Context Diagram
context_diagram = [
    "                         EXTERNAL ENTITIES",
    "    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐",
    "    │   SHIPPER    │    │   CARRIER    │    │  CONSIGNEE   │",
    "    │  (Customer)  │    │  (Shipping   │    │  (Receiver)  │",
    "    │              │    │   Line/Air/  │    │              │",
    "    │              │    │   Trucking)  │    │              │",
    "    └──────┬───────┘    └──────┬───────┘    └──────┬───────┘",
    "           │                   │                   │",
    "           │ Web Portal        │ EDI X12           │ Email",
    "           │ (HTTPS/JSON)      │ (AS2/SFTP)        │ Notifications",
    "           │                   │                   │",
    "           ▼                   ▼                   ▼",
    "    ╔═══════════════════════════════════════════════════════╗",
    "    ║     FREIGHT BOOKING MANAGEMENT SYSTEM                 ║",
    "    ║  ┌─────────┐  ┌─────────┐  ┌─────────────┐           ║",
    "    ║  │ Web API │  │   EDI   │  │Notification │           ║",
    "    ║  │  Layer  │  │ Gateway │  │   Service   │           ║",
    "    ║  └─────────┘  └─────────┘  └─────────────┘           ║",
    "    ╚═══════════════════════════════════════════════════════╝",
    "           │                   │                   │",
    "           ▼                   ▼                   ▼",
    "    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐",
    "    │  SQL Server  │    │ Azure Blob   │    │    Redis     │",
    "    │   Database   │    │   Storage    │    │   (Queue)    │",
    "    └──────────────┘    └──────────────┘    └──────────────┘",
]
add_content_slide(prs, "System Context Diagram (Level 0)", context_diagram, font_size=11)

# Slide 9: Section - Data Flow
add_section_slide(prs, "Data Flow Diagram (Level 1)")

# Slide 10: Inputs
inputs_content = [
    "                              I N P U T S",
    "",
    "  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐",
    "  │ SHIPPER INPUT   │    │ CARRIER INPUT   │    │ SYSTEM INPUT    │",
    "  │                 │    │ (EDI Inbound)   │    │                 │",
    "  │ • Booking Data  │    │                 │    │ • Master Data   │",
    "  │ • Cargo Details │    │ • X12 301 Conf  │    │   (Locations,   │",
    "  │ • Party Info    │    │ • X12 990 Resp  │    │    Carriers)    │",
    "  │ • Documents     │    │ • X12 214 Status│    │ • User Accounts │",
    "  │ • Instructions  │    │ • X12 210 Inv   │    │ • Workflow Cfg  │",
    "  │                 │    │ • X12 997 Ack   │    │                 │",
    "  └─────────────────┘    └─────────────────┘    └─────────────────┘",
]
add_content_slide(prs, "Data Flow - Inputs", inputs_content, font_size=13)

# Slide 11: Processing
processing_content = [
    "                        P R O C E S S I N G",
    "",
    "  1. BOOKING MANAGEMENT",
    "     [Validate] ─▶ [Create/Update] ─▶ [Apply Rules] ─▶ [Generate #]",
    "",
    "  2. WORKFLOW ENGINE",
    "     [Match Config] ─▶ [Create Steps] ─▶ [Process Decision] ─▶ [Update Status]",
    "",
    "  3. EDI GATEWAY",
    "     [Map to X12] ─▶ [Generate Envelope] ─▶ [Transmit AS2/SFTP] ─▶ [Parse Inbound]",
    "",
    "  4. DOCUMENT MANAGEMENT",
    "     [Validate Type] ─▶ [Store Azure Blob] ─▶ [Generate Access URLs]",
    "",
    "  5. NOTIFICATION ENGINE",
    "     [Queue Event] ─▶ [Render Template] ─▶ [Send via SMTP]",
]
add_content_slide(prs, "Data Flow - Processing", processing_content, font_size=14)

# Slide 12: Outputs
outputs_content = [
    "                              O U T P U T S",
    "",
    "  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐",
    "  │ TO SHIPPER      │    │ TO CARRIER      │    │ TO INTERNAL     │",
    "  │                 │    │ (EDI Outbound)  │    │                 │",
    "  │ • Booking Conf  │    │                 │    │ • Audit Logs    │",
    "  │ • Status Updates│    │ • X12 300 Book  │    │ • Reports       │",
    "  │ • Email Alerts  │    │ • X12 304 SI    │    │ • Dashboards    │",
    "  │ • Documents     │    │ • X12 204 Tender│    │ • Analytics     │",
    "  │ • Tracking Info │    │ • X12 997 Ack   │    │                 │",
    "  │                 │    │                 │    │                 │",
    "  └─────────────────┘    └─────────────────┘    └─────────────────┘",
]
add_content_slide(prs, "Data Flow - Outputs", outputs_content, font_size=13)

# Slide 13: Section - Booking Lifecycle
add_section_slide(prs, "Booking Lifecycle Flow")

# Slide 14: Booking Lifecycle Part 1
lifecycle1 = [
    "  SHIPPER              SYSTEM                 CARRIER",
    "     │                    │                      │",
    "     │ 1. Create Booking  │                      │",
    "     │───────────────────▶│                      │",
    "     │                    │                      │",
    "     │               ┌────┴────┐                 │",
    "     │               │  DRAFT  │                 │",
    "     │               └────┬────┘                 │",
    "     │                    │                      │",
    "     │ 2. Add Cargo       │                      │",
    "     │ 3. Upload Docs     │                      │",
    "     │ 4. Submit          │                      │",
    "     │───────────────────▶│                      │",
    "     │                    │                      │",
    "     │               ┌────┴────┐                 │",
    "     │               │VALIDATE │                 │",
    "     │               │& CHECK  │                 │",
    "     │               │WORKFLOW │                 │",
    "     │               └────┬────┘                 │",
]
add_content_slide(prs, "Booking Lifecycle - Submission", lifecycle1, font_size=12)

# Slide 15: Booking Lifecycle Part 2
lifecycle2 = [
    "  SHIPPER              SYSTEM                 CARRIER (EDI)",
    "     │                    │                      │",
    "     │               ┌────┴────┐                 │",
    "     │               │PENDING_ │                 │",
    "     │               │APPROVAL │                 │",
    "     │               └────┬────┘                 │",
    "     │                    │                      │",
    "     │◀──Email: Approval──│                      │",
    "     │   Required         │                      │",
    "     │                    │                      │",
    "     │  [Approver Action] │                      │",
    "     │                    │                      │",
    "     │               ┌────┴────┐                 │",
    "     │               │APPROVED │                 │",
    "     │               └────┬────┘                 │",
    "     │                    │                      │",
    "     │◀──Email: Approved──│  5. Send X12 300    │",
    "     │                    │─────────────────────▶│",
    "     │                    │                      │",
]
add_content_slide(prs, "Booking Lifecycle - Approval & EDI", lifecycle2, font_size=12)

# Slide 16: Booking Lifecycle Part 3
lifecycle3 = [
    "  SHIPPER              SYSTEM                 CARRIER (EDI)",
    "     │                    │                      │",
    "     │                    │  6. Receive X12 997  │",
    "     │                    │◀─────────────────────│",
    "     │                    │  [Functional Ack]    │",
    "     │                    │                      │",
    "     │               ┌────┴────┐                 │",
    "     │               │SUBMITTED│                 │",
    "     │               │TO_CARRIER                 │",
    "     │               └────┬────┘                 │",
    "     │                    │                      │",
    "     │                    │  7. Receive X12 301  │",
    "     │                    │◀─────────────────────│",
    "     │                    │  [Booking Confirm]   │",
    "     │                    │                      │",
    "     │               ┌────┴────┐                 │",
    "     │               │CONFIRMED│                 │",
    "     │               └────┬────┘                 │",
    "     │◀──Email: Confirmed─│                      │",
]
add_content_slide(prs, "Booking Lifecycle - Carrier Confirmation", lifecycle3, font_size=12)

# Slide 17: Booking Lifecycle Part 4
lifecycle4 = [
    "  SHIPPER              SYSTEM                 CARRIER (EDI)",
    "     │                    │                      │",
    "     │                    │  8. Receive X12 214  │",
    "     │                    │◀─────────────────────│",
    "     │                    │  [Status Updates]    │",
    "     │                    │                      │",
    "     │               ┌────┴────┐                 │",
    "     │               │IN_TRANSIT                 │",
    "     │               └────┬────┘                 │",
    "     │                    │                      │",
    "     │◀──Email: Updates───│                      │",
    "     │                    │                      │",
    "     │                    │  9. Final X12 214    │",
    "     │                    │◀─────────────────────│",
    "     │                    │  [Delivery Confirm]  │",
    "     │                    │                      │",
    "     │               ┌────┴────┐                 │",
    "     │               │DELIVERED│                 │",
    "     │               └────┬────┘                 │",
    "     │◀──Email: Delivered─│                      │",
]
add_content_slide(prs, "Booking Lifecycle - Tracking & Delivery", lifecycle4, font_size=12)

# Slide 18: Section - EDI Processing
add_section_slide(prs, "EDI Processing Flows")

# Slide 19: EDI Outbound Flow
edi_outbound = [
    "                    EDI OUTBOUND PROCESSING FLOW",
    "",
    "  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐",
    "  │   Booking   │   │     EDI     │   │     EDI     │   │   Carrier   │",
    "  │   Approved  │──▶│    Mapper   │──▶│  Transmit   │──▶│   System    │",
    "  │    Event    │   │   Service   │   │   Service   │   │ (AS2/SFTP)  │",
    "  └─────────────┘   └─────────────┘   └─────────────┘   └─────────────┘",
    "",
    "  Processing Steps:",
    "  ─────────────────────────────────────────────────────────────────────",
    "  1. Booking status changes to APPROVED",
    "  2. System triggers EDI generation job",
    "  3. EDI Mapper loads booking + related data",
    "  4. Maps internal fields to X12 segments",
    "  5. Generates ISA/GS/ST envelope with control numbers",
    "  6. Validates EDI syntax",
    "  7. Queues for transmission",
    "  8. Transmit via AS2 (preferred) or SFTP",
    "  9. Log transmission status",
    " 10. Update booking.status = SUBMITTED_TO_CARRIER",
]
add_content_slide(prs, "EDI Outbound Processing Flow", edi_outbound, font_size=11)

# Slide 20: EDI Inbound Flow
edi_inbound = [
    "                    EDI INBOUND PROCESSING FLOW",
    "",
    "  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐",
    "  │   Carrier   │   │     EDI     │   │     EDI     │   │   Booking   │",
    "  │   System    │──▶│  Receiver   │──▶│   Parser    │──▶│   Updater   │",
    "  │ (AS2/SFTP)  │   │   Service   │   │   Service   │   │   Service   │",
    "  └─────────────┘   └─────────────┘   └─────────────┘   └─────────────┘",
    "",
    "  Processing Steps:",
    "  ─────────────────────────────────────────────────────────────────────",
    "  1. Receive EDI file via AS2/SFTP polling",
    "  2. Store raw file with timestamp and source identifier",
    "  3. Parse ISA/GS/ST envelope, extract control numbers",
    "  4. Identify transaction type (301, 214, 210, etc.)",
    "  5. Parse transaction segments into structured data",
    "  6. Match to internal booking (via booking # or carrier ref)",
    "  7. Apply updates to booking record",
    "  8. Log changes to audit trail",
    "  9. Generate X12 997 Functional Acknowledgment",
    " 10. Transmit 997 back to carrier",
    " 11. Trigger notifications to shipper if status changed",
]
add_content_slide(prs, "EDI Inbound Processing Flow", edi_inbound, font_size=11)

# Slide 21: Section - Data Stores
add_section_slide(prs, "Data Stores Overview")

# Slide 22: Data Stores
datastores = [
    "  ┌────────────────────────────────────────────────────────────────┐",
    "  │                    SQL SERVER DATABASE                         │",
    "  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │",
    "  │  │TRANSACTIONAL │  │  REFERENCE   │  │    AUDIT     │         │",
    "  │  │• bookings    │  │• locations   │  │• audit_log   │         │",
    "  │  │• booking_*   │  │• carriers    │  │• status_hist │         │",
    "  │  │• customers   │  │• commodities │  │• edi_log     │         │",
    "  │  │• approvals   │  │• containers  │  │              │         │",
    "  │  └──────────────┘  └──────────────┘  └──────────────┘         │",
    "  │  ┌─────────────────────────────────────────────────────┐      │",
    "  │  │                   EDI TABLES                         │      │",
    "  │  │ • edi_partners  • edi_outbound_queue  • edi_trans   │      │",
    "  │  └─────────────────────────────────────────────────────┘      │",
    "  └────────────────────────────────────────────────────────────────┘",
    "",
    "  ┌────────────────────────────┐  ┌────────────────────────────┐",
    "  │    AZURE BLOB STORAGE      │  │    REDIS (MESSAGE QUEUE)   │",
    "  │ /documents/{booking}/      │  │ • email_notifications      │",
    "  │ /edi/outbound/             │  │ • edi_outbound             │",
    "  │ /edi/inbound/              │  │ • edi_inbound              │",
    "  └────────────────────────────┘  └────────────────────────────┘",
]
add_content_slide(prs, "Data Stores Overview", datastores, font_size=11)

# Slide 23: Data Mapping - Internal to X12
mapping1 = [
    "                BOOKING DATA → EDI X12 300 MAPPING",
    "",
    "  Internal Model                    EDI X12 300 Segment",
    "  ═══════════════════════════════════════════════════════════════",
    "",
    "  bookings.booking_number      →    B1-02 (Reservation Number)",
    "  bookings.cargo_ready_date    →    DTM-02 where DTM-01 = \"140\"",
    "  bookings.estimated_departure →    DTM-02 where DTM-01 = \"370\"",
    "",
    "  customers.name               →    N1-02 where N1-01 = \"SH\"",
    "  customers.address_line1      →    N3-01",
    "",
    "  locations.code (origin)      →    R4-02 where R4-01 = \"L\" (POL)",
    "  locations.code (destination) →    R4-02 where R4-01 = \"D\" (POD)",
    "",
    "  booking_ocean_fcl.vessel     →    V1-02 (Vessel Name)",
    "  booking_containers.type      →    Y2-01 (Equipment Type)",
    "",
    "  booking_items.commodity_desc →    L5-01 (Description)",
    "  booking_items.gross_weight   →    L0-04 (Weight)",
]
add_content_slide(prs, "Data Mapping: Internal → EDI X12", mapping1, font_size=12)

# Slide 24: Questions
add_title_slide(
    prs,
    "Questions?",
    "Freight Booking Management System - Data Flow Architecture"
)

# Save the presentation
output_path = r"C:\Users\micha\freight-booking-system\docs\DataFlow_Presentation.pptx"
prs.save(output_path)
print(f"Presentation saved to: {output_path}")
