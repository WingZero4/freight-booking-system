"""Shared PDF generation utility using ReportLab."""
import io
from datetime import date
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable,
)


def build_booking_pdf(booking, include_internal=False):
    """Build a PDF document for a booking.

    Args:
        booking: Booking instance (with related objects prefetched)
        include_internal: If True, include contract_number, carrier refs,
                          container numbers, bill of lading numbers (staff only)

    Returns:
        BytesIO buffer containing the PDF
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=20 * mm, bottomMargin=20 * mm,
    )

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        'DocTitle', parent=styles['Title'], fontSize=16, spaceAfter=4 * mm,
    ))
    styles.add(ParagraphStyle(
        'SectionHead', parent=styles['Heading2'], fontSize=12,
        spaceBefore=6 * mm, spaceAfter=2 * mm,
        textColor=colors.HexColor('#1E2A4A'),
    ))
    styles.add(ParagraphStyle(
        'SmallText', parent=styles['Normal'], fontSize=8, textColor=colors.grey,
    ))

    elements = []

    # --- Header ---
    doc_type = 'Shipping Advice' if include_internal else 'Booking Confirmation'
    elements.append(Paragraph(doc_type, styles['DocTitle']))
    elements.append(HRFlowable(width='100%', thickness=1, color=colors.HexColor('#1E2A4A')))
    elements.append(Spacer(1, 4 * mm))

    # --- Booking Info ---
    info_data = [
        ['Booking Number:', booking.booking_number, 'Status:', booking.get_status_display()],
        ['Transport Mode:', booking.get_transport_mode_display(), 'INCOTERMS:', booking.get_incoterms_display()],
        ['Origin:', f"{booking.origin_port.name} ({booking.origin_port.code})",
         'Destination:', f"{booking.destination_port.name} ({booking.destination_port.code})"],
        ['Cargo Ready:', _fmt_date(booking.cargo_ready_date), 'Created:', _fmt_date(booking.created_at)],
    ]

    if booking.container_type:
        info_data.append([
            'Container:', f"{booking.container_count}x {booking.container_type.code}",
            '', '',
        ])

    if booking.etd or booking.eta:
        info_data.append([
            'ETD:', _fmt_date(booking.etd), 'ETA:', _fmt_date(booking.eta),
        ])

    if booking.carrier_name or booking.vessel_name:
        vessel = booking.vessel_name or booking.flight_number or ''
        info_data.append([
            'Carrier:', booking.carrier_name, 'Vessel/Flight:', vessel,
        ])
        if booking.voyage_number:
            info_data.append(['Voyage:', booking.voyage_number, '', ''])

    if include_internal:
        if booking.contract_number:
            info_data.append(['Contract #:', booking.contract_number, '', ''])
        if booking.carrier_booking_ref:
            info_data.append(['Carrier Ref:', booking.carrier_booking_ref, '', ''])
        if booking.carrier_confirmation_ref:
            info_data.append(['Carrier Confirm Ref:', booking.carrier_confirmation_ref, '', ''])
        if booking.hbl_number or booking.mbl_number:
            info_data.append(['HBL:', booking.hbl_number, 'MBL:', booking.mbl_number])
        if booking.hawb_number or booking.mawb_number:
            info_data.append(['HAWB:', booking.hawb_number, 'MAWB:', booking.mawb_number])
        if booking.container_numbers:
            info_data.append(['Containers:', booking.container_numbers.replace('\n', ', '), '', ''])
        if booking.cargo_cutoff_date:
            info_data.append(['Cargo Cutoff:', _fmt_date(booking.cargo_cutoff_date), '', ''])
        if booking.actual_departure_date:
            info_data.append(['Actual Departure:', _fmt_date(booking.actual_departure_date), '', ''])
        if booking.actual_arrival_date:
            info_data.append(['Actual Arrival:', _fmt_date(booking.actual_arrival_date), '', ''])

    info_table = Table(info_data, colWidths=[85, 150, 85, 150])
    info_table.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold'),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#555555')),
        ('TEXTCOLOR', (2, 0), (2, -1), colors.HexColor('#555555')),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
    ]))
    elements.append(info_table)

    # --- Cargo Items ---
    items = list(booking.items.all())
    if items:
        elements.append(Paragraph('Cargo Items', styles['SectionHead']))

        cargo_header = ['#', 'Description', 'Pkg Type', 'Qty', 'Weight (kg)', 'CBM', 'HS Code', 'DG']
        cargo_data = [cargo_header]
        for i, item in enumerate(items, 1):
            cargo_data.append([
                str(i),
                _truncate(item.description, 40),
                item.get_package_type_display(),
                str(item.quantity),
                f"{item.weight_kg:,.2f}",
                f"{item.volume_cbm:,.3f}" if item.volume_cbm else '-',
                item.hs_code or '-',
                'Yes' if item.is_hazardous else 'No',
            ])

        # Totals row
        cargo_data.append([
            '', 'TOTAL', '',
            str(sum(i.quantity for i in items)),
            f"{booking.total_weight_kg:,.2f}" if booking.total_weight_kg else '-',
            f"{booking.total_volume_cbm:,.3f}" if booking.total_volume_cbm else '-',
            '', '',
        ])

        cargo_table = Table(cargo_data, colWidths=[20, 130, 55, 30, 60, 45, 55, 25])
        cargo_table.setStyle(TableStyle([
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E2A4A')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (3, 0), (-1, -1), 'RIGHT'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CCCCCC')),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            # Totals row styling
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('LINEABOVE', (0, -1), (-1, -1), 1, colors.HexColor('#1E2A4A')),
        ]))
        elements.append(cargo_table)

    # --- Parties ---
    parties = list(booking.booking_parties.all())
    if parties:
        elements.append(Paragraph('Parties', styles['SectionHead']))

        for bp in parties:
            party_info = f"<b>{escape(bp.get_role_display())}</b>: {escape(bp.company_name)}"
            if bp.contact_name:
                party_info += f" (Attn: {escape(bp.contact_name)})"
            if bp.address_text:
                party_info += f"<br/>{escape(bp.address_text)}"
            contact_parts = []
            if bp.email:
                contact_parts.append(escape(bp.email))
            if bp.phone:
                contact_parts.append(escape(bp.phone))
            if contact_parts:
                party_info += f"<br/>{' | '.join(contact_parts)}"
            elements.append(Paragraph(party_info, styles['Normal']))
            elements.append(Spacer(1, 2 * mm))

    # --- Special Instructions ---
    if booking.special_instructions:
        elements.append(Paragraph('Special Instructions', styles['SectionHead']))
        elements.append(Paragraph(escape(booking.special_instructions), styles['Normal']))

    # --- Commodity Description ---
    if booking.commodity_description:
        elements.append(Paragraph('Commodity Description', styles['SectionHead']))
        desc = escape(booking.commodity_description)
        if booking.is_hazardous:
            desc += ' <font color="red"><b>[HAZARDOUS CARGO]</b></font>'
        elements.append(Paragraph(desc, styles['Normal']))

    # --- Footer ---
    elements.append(Spacer(1, 10 * mm))
    elements.append(HRFlowable(width='100%', thickness=0.5, color=colors.grey))
    elements.append(Paragraph(
        f'Generated on {date.today().strftime("%B %d, %Y")} | '
        f'Booking {booking.booking_number}',
        styles['SmallText'],
    ))

    doc.build(elements)
    buffer.seek(0)
    return buffer


def _fmt_date(val):
    """Format a date or datetime for display."""
    if val is None:
        return '-'
    if hasattr(val, 'strftime'):
        return val.strftime('%b %d, %Y')
    return str(val)


def _truncate(text, max_len):
    """Truncate text to max_len characters."""
    if len(text) <= max_len:
        return text
    return text[:max_len - 3] + '...'
