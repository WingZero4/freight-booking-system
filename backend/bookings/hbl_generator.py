"""Draft House Bill of Lading PDF generator."""

import io
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Frame,
    PageTemplate, BaseDocTemplate,
)


def _safe(text):
    """Escape text for ReportLab Paragraph."""
    if text is None:
        return ''
    return escape(str(text))


def _format_party_block(party_data):
    """Format a party dict or BookingParty into a multi-line string."""
    if not party_data:
        return ''
    if hasattr(party_data, 'snapshot_name'):
        # BookingParty model
        lines = [party_data.snapshot_name or '']
        if party_data.snapshot_address:
            lines.append(party_data.snapshot_address)
        return '<br/>'.join(_safe(l) for l in lines if l)
    # Dict fallback
    lines = [party_data.get('name', '')]
    if party_data.get('address'):
        lines.append(party_data['address'])
    return '<br/>'.join(_safe(l) for l in lines if l)


def generate_draft_hbl(booking):
    """Generate a Draft House Bill of Lading PDF.

    Returns BytesIO containing the PDF.
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=letter,
        topMargin=0.5 * inch, bottomMargin=0.5 * inch,
        leftMargin=0.5 * inch, rightMargin=0.5 * inch,
    )
    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        'HBLTitle', parent=styles['Title'],
        fontSize=16, textColor=colors.HexColor('#1E2A4A'),
    )
    header_style = ParagraphStyle(
        'HBLHeader', parent=styles['Heading3'],
        fontSize=9, textColor=colors.HexColor('#1E2A4A'),
        spaceAfter=2,
    )
    body_style = ParagraphStyle(
        'HBLBody', parent=styles['Normal'],
        fontSize=9, leading=11,
    )
    small_style = ParagraphStyle(
        'HBLSmall', parent=styles['Normal'],
        fontSize=7, textColor=colors.grey,
    )
    draft_style = ParagraphStyle(
        'DraftWatermark', parent=styles['Title'],
        fontSize=60, textColor=colors.Color(0.9, 0.9, 0.9),
        alignment=1,
    )

    elements = []

    # DRAFT watermark
    elements.append(Paragraph('DRAFT', draft_style))
    elements.append(Spacer(1, -0.5 * inch))

    # BL Number
    bl_number = f'HBL-{booking.booking_number}'
    elements.append(Paragraph(
        f'<b>HOUSE BILL OF LADING</b>', title_style))
    elements.append(Paragraph(
        f'B/L No: <b>{_safe(bl_number)}</b>', body_style))
    elements.append(Spacer(1, 0.2 * inch))

    # Get parties
    parties = {}
    for bp in booking.booking_parties.select_related('party').all():
        parties[bp.role] = bp

    # Shipper / Consignee / Notify table
    shipper = parties.get('SHIPPER')
    consignee = parties.get('CONSIGNEE')
    notify = parties.get('NOTIFY')

    party_data = [
        [Paragraph('<b>Shipper</b>', header_style),
         Paragraph('<b>B/L Number</b>', header_style)],
        [Paragraph(_format_party_block(shipper) or 'N/A', body_style),
         Paragraph(_safe(bl_number), body_style)],
        [Paragraph('<b>Consignee</b>', header_style),
         Paragraph('<b>Reference No.</b>', header_style)],
        [Paragraph(_format_party_block(consignee) or 'N/A', body_style),
         Paragraph(_safe(booking.external_reference or booking.booking_number), body_style)],
        [Paragraph('<b>Notify Party</b>', header_style),
         Paragraph('<b>Export Reference</b>', header_style)],
        [Paragraph(_format_party_block(notify) or 'SAME AS CONSIGNEE', body_style),
         Paragraph(_safe(booking.external_reference), body_style)],
    ]
    party_table = Table(party_data, colWidths=[4 * inch, 3.5 * inch])
    party_table.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.5, colors.black),
        ('INNERGRID', (0, 0), (-1, -1), 0.25, colors.grey),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(party_table)
    elements.append(Spacer(1, 0.1 * inch))

    # Vessel / Port info
    vessel_data = [
        [Paragraph('<b>Vessel / Voyage</b>', header_style),
         Paragraph('<b>Port of Loading</b>', header_style),
         Paragraph('<b>Port of Discharge</b>', header_style)],
        [Paragraph(_safe(
            f'{booking.vessel_name or ""} / {booking.voyage_number or ""}'.strip(' /')),
            body_style),
         Paragraph(_safe(
            booking.origin_port.name if booking.origin_port else 'N/A'),
            body_style),
         Paragraph(_safe(
            booking.destination_port.name if booking.destination_port else 'N/A'),
            body_style)],
    ]
    vessel_table = Table(vessel_data, colWidths=[2.5 * inch, 2.5 * inch, 2.5 * inch])
    vessel_table.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.5, colors.black),
        ('INNERGRID', (0, 0), (-1, -1), 0.25, colors.grey),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(vessel_table)
    elements.append(Spacer(1, 0.1 * inch))

    # Cargo details table
    items = booking.items.all()
    cargo_header = [
        Paragraph('<b>Marks &amp; Numbers</b>', header_style),
        Paragraph('<b>Description of Goods</b>', header_style),
        Paragraph('<b>Packages</b>', header_style),
        Paragraph('<b>Gross Weight (KG)</b>', header_style),
        Paragraph('<b>Volume (CBM)</b>', header_style),
    ]
    cargo_data = [cargo_header]
    for item in items:
        cargo_data.append([
            Paragraph(_safe(item.marks_and_numbers or '-'), body_style),
            Paragraph(_safe(item.description), body_style),
            Paragraph(f'{item.quantity} {item.get_package_type_display()}', body_style),
            Paragraph(str(item.weight_kg), body_style),
            Paragraph(str(item.volume_cbm or '-'), body_style),
        ])

    # Add commodity description as summary row
    if booking.commodity_description:
        cargo_data.append([
            '', Paragraph(f'<i>{_safe(booking.commodity_description)}</i>', body_style),
            '', '', '',
        ])

    # Totals row
    cargo_data.append([
        '', Paragraph('<b>TOTAL</b>', body_style), '',
        Paragraph(f'<b>{booking.total_weight_kg}</b>', body_style),
        Paragraph(f'<b>{booking.total_volume_cbm}</b>', body_style),
    ])

    cargo_table = Table(
        cargo_data,
        colWidths=[1.3 * inch, 2.7 * inch, 1 * inch, 1.25 * inch, 1.25 * inch],
    )
    cargo_table.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.5, colors.black),
        ('INNERGRID', (0, 0), (-1, -1), 0.25, colors.grey),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#F0F0F0')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('LINEABOVE', (0, -1), (-1, -1), 0.5, colors.black),
    ]))
    elements.append(cargo_table)
    elements.append(Spacer(1, 0.15 * inch))

    # Freight terms
    freight_terms = booking.freight_terms or 'PREPAID'
    terms_text = f'Freight: <b>{_safe(freight_terms)}</b>'
    if booking.incoterms:
        terms_text += f'&nbsp;&nbsp;|&nbsp;&nbsp;Incoterms: <b>{_safe(booking.incoterms)}</b>'
    elements.append(Paragraph(terms_text, body_style))
    elements.append(Spacer(1, 0.1 * inch))

    # Number of originals
    originals = booking.number_of_originals or 3
    elements.append(Paragraph(
        f'Number of Original B/Ls: <b>{originals}</b>', body_style))
    elements.append(Spacer(1, 0.15 * inch))

    # Signature blocks
    sig_data = [
        [Paragraph('<b>Shipped on Board Date</b>', header_style),
         Paragraph('<b>Place of Issue</b>', header_style),
         Paragraph('<b>Date of Issue</b>', header_style)],
        [Paragraph('_________________', body_style),
         Paragraph(_safe(
            booking.origin_port.name if booking.origin_port else '___________'),
            body_style),
         Paragraph('_________________', body_style)],
    ]
    sig_table = Table(sig_data, colWidths=[2.5 * inch, 2.5 * inch, 2.5 * inch])
    sig_table.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.5, colors.black),
        ('INNERGRID', (0, 0), (-1, -1), 0.25, colors.grey),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(sig_table)

    # Footer
    elements.append(Spacer(1, 0.2 * inch))
    elements.append(Paragraph(
        'This is a DRAFT document and is not valid for shipment or customs clearance.',
        small_style))

    doc.build(elements)
    buf.seek(0)
    return buf
