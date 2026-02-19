"""Tests for EDI parser, generator, and import service."""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase

from bookings.models import Booking, Customer, Port, ContainerType, UserProfile
from bookings.tests.helpers import get_default_org

from .edi.iftmbf_parser import parse_iftmbf, IFTMBFParseError
from .edi.iftmbc_generator import generate_iftmbc
from .edi.edi_service import process_edi_file


# ---------------------------------------------------------------------------
# Sample EDI messages
# ---------------------------------------------------------------------------

SAMPLE_IFTMBF = (
    "UNH+1+IFTMBF:D:99B:UN'"
    "BGM+335+REF12345+9'"
    "DTM+133:20260301:102'"
    "TSR+17++FCL'"
    "FTX+AAA+++Handle with care'"
    "LOC+88+CNSHA'"
    "LOC+11+USNYC'"
    "NAD+CZ+++Test Shipper+123 Main St+Shanghai'"
    "NAD+CN+++Test Consignee+456 Broadway+New York'"
    "GID+1+10:CT+Electronic components'"
    "MEA+WT+AAA+KGM:500'"
    "MEA+VOL+AAW+MTQ:2.5'"
    "GID+2+5:PL+Machine parts'"
    "MEA+WT+AAA+KGM:1200'"
    "DGS+IMD+1234+3'"
    "UNT+15+1'"
)

MINIMAL_IFTMBF = (
    "UNH+1+IFTMBF:D:99B:UN'"
    "BGM+335+MIN001+9'"
    "LOC+88+CNSHA'"
    "LOC+11+USNYC'"
    "GID+1+1:PK+Cargo'"
    "MEA+WT+AAA+KGM:10'"
    "UNT+6+1'"
)

EMPTY_MESSAGE = ""


class TestIFTMBFParser(TestCase):

    def test_parse_full_message(self):
        result = parse_iftmbf(SAMPLE_IFTMBF)
        bd = result['booking_data']
        self.assertEqual(bd['origin_port_code'], 'CNSHA')
        self.assertEqual(bd['destination_port_code'], 'USNYC')
        self.assertEqual(bd['cargo_ready_date'], date(2026, 3, 1))
        self.assertEqual(bd['transport_mode'], 'SEA_FCL')
        self.assertEqual(bd['special_instructions'], 'Handle with care')
        self.assertEqual(result['external_reference'], 'REF12345')

    def test_parse_items(self):
        result = parse_iftmbf(SAMPLE_IFTMBF)
        items = result['items_data']
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]['quantity'], 10)
        self.assertEqual(items[0]['package_type'], 'CARTON')
        self.assertEqual(items[0]['weight_kg'], 500)
        self.assertEqual(items[0]['volume_cbm'], 2.5)
        self.assertEqual(items[1]['quantity'], 5)
        self.assertTrue(items[1]['is_hazardous'])
        self.assertEqual(items[1]['un_number'], '1234')
        self.assertEqual(items[1]['imo_class'], '3')

    def test_parse_parties(self):
        result = parse_iftmbf(SAMPLE_IFTMBF)
        parties = result['parties_data']
        self.assertEqual(len(parties), 2)
        roles = {p['role'] for p in parties}
        self.assertIn('SHIPPER', roles)
        self.assertIn('CONSIGNEE', roles)

    def test_parse_minimal_message(self):
        result = parse_iftmbf(MINIMAL_IFTMBF)
        self.assertEqual(result['booking_data']['origin_port_code'], 'CNSHA')
        self.assertEqual(len(result['items_data']), 1)
        # Defaults applied
        self.assertEqual(result['booking_data']['transport_mode'], 'SEA_FCL')
        self.assertEqual(result['booking_data']['incoterms'], 'FOB')

    def test_parse_empty_message_raises(self):
        with self.assertRaises(IFTMBFParseError):
            parse_iftmbf(EMPTY_MESSAGE)

    def test_parse_no_gid_warns(self):
        msg = "UNH+1+IFTMBF:D:99B:UN'BGM+335+X+9'LOC+88+CNSHA'LOC+11+USNYC'UNT+4+1'"
        result = parse_iftmbf(msg)
        self.assertEqual(len(result['items_data']), 0)
        self.assertTrue(any('No goods items' in w for w in result['issues']))


class TestIFTMBCGenerator(TestCase):

    def setUp(self):
        self.customer = Customer.objects.create(
            name='Gen Corp', code='GEN01', is_active=True,
            organization=get_default_org(),
        )
        self.origin = Port.objects.create(code='CNSHA', name='Shanghai', country='CN')
        self.dest = Port.objects.create(code='USNYC', name='New York', country='US')
        ctype = ContainerType.objects.create(code='20GP', name='20ft GP', size_ft=20)
        user = User.objects.create_user('genuser', 'gen@test.com', 'pass123')
        self.booking = Booking.objects.create(
            customer=self.customer,
            created_by=user,
            transport_mode='SEA_FCL',
            origin_port=self.origin,
            destination_port=self.dest,
            cargo_ready_date=date.today() + timedelta(days=7),
            container_type=ctype,
            container_count=2,
            incoterms='FOB',
            status='CONFIRMED',
            carrier_booking_ref='CBR123',
        )
        self.booking.items.create(
            description='Test item',
            quantity=10,
            weight_kg=Decimal('500.00'),
            package_type='CARTON',
        )

    def test_generate_contains_booking_number(self):
        output = generate_iftmbc(self.booking)
        self.assertIn(self.booking.booking_number, output)

    def test_generate_contains_ports(self):
        output = generate_iftmbc(self.booking)
        self.assertIn('LOC+88+CNSHA', output)
        self.assertIn('LOC+11+USNYC', output)

    def test_generate_contains_carrier_ref(self):
        output = generate_iftmbc(self.booking)
        self.assertIn('RFF+BN:CBR123', output)

    def test_generate_contains_items(self):
        output = generate_iftmbc(self.booking)
        self.assertIn('GID+1+10:CT', output)
        self.assertIn('MEA+WT+AAA+KGM:500', output)

    def test_generate_has_header_and_trailer(self):
        output = generate_iftmbc(self.booking)
        self.assertTrue(output.startswith('UNH+1+IFTMBC'))
        self.assertIn('UNT+', output)

    def test_generate_message_date(self):
        output = generate_iftmbc(self.booking)
        self.assertIn('DTM+137:', output)


class TestEDIImportService(TestCase):

    def setUp(self):
        self.customer = Customer.objects.create(
            name='EDI Corp', code='EDI01', is_active=True,
            organization=get_default_org(),
        )
        Port.objects.create(code='CNSHA', name='Shanghai', country='CN')
        Port.objects.create(code='USNYC', name='New York', country='US')
        self.user = User.objects.create_user('ediuser', 'edi@test.com', 'pass123')

    def test_process_valid_edi(self):
        result = process_edi_file(SAMPLE_IFTMBF, self.customer, self.user)
        self.assertEqual(len(result['errors']), 0)
        self.assertEqual(len(result['created']), 1)
        booking = Booking.objects.first()
        self.assertEqual(booking.source_channel, 'EDI')
        self.assertEqual(booking.customer, self.customer)
        self.assertEqual(booking.items.count(), 2)

    def test_process_edi_sets_ports(self):
        result = process_edi_file(SAMPLE_IFTMBF, self.customer, self.user)
        self.assertEqual(len(result['created']), 1)
        booking = Booking.objects.first()
        self.assertEqual(booking.origin_port.code, 'CNSHA')
        self.assertEqual(booking.destination_port.code, 'USNYC')

    def test_process_edi_unknown_port(self):
        msg = MINIMAL_IFTMBF.replace('CNSHA', 'XXXXX')
        result = process_edi_file(msg, self.customer, self.user)
        self.assertGreater(len(result['errors']), 0)
        self.assertEqual(len(result['created']), 0)

    def test_process_edi_empty_message(self):
        result = process_edi_file('', self.customer, self.user)
        self.assertGreater(len(result['errors']), 0)
        self.assertEqual(len(result['created']), 0)

    def test_process_edi_no_items(self):
        msg = "UNH+1+IFTMBF:D:99B:UN'BGM+335+X+9'LOC+88+CNSHA'LOC+11+USNYC'UNT+4+1'"
        result = process_edi_file(msg, self.customer, self.user)
        self.assertGreater(len(result['errors']), 0)
        self.assertIn('No cargo items', result['errors'][0])

    def test_process_edi_defaults_cargo_ready_date(self):
        result = process_edi_file(MINIMAL_IFTMBF, self.customer, self.user)
        self.assertEqual(len(result['created']), 1)
        booking = Booking.objects.first()
        self.assertIsNotNone(booking.cargo_ready_date)
        self.assertTrue(
            any('cargo ready date' in w.lower() for w in result['warnings']),
        )

    def test_process_edi_parties_created(self):
        result = process_edi_file(SAMPLE_IFTMBF, self.customer, self.user)
        booking = Booking.objects.first()
        self.assertEqual(booking.booking_parties.count(), 2)


# ---------------------------------------------------------------------------
# EDI validation (cross-field checks in edi_service)
# ---------------------------------------------------------------------------


class TestEDIValidation(TestCase):
    """Tests for cross-field validation in the EDI import pipeline."""

    def setUp(self):
        self.customer = Customer.objects.create(
            name='Val Corp', code='VAL01', is_active=True,
            organization=get_default_org(),
        )
        Port.objects.create(code='CNSHA', name='Shanghai', country='CN')
        Port.objects.create(code='USNYC', name='New York', country='US')
        self.user = User.objects.create_user('valuser', 'val@test.com', 'pass123')

    def test_edi_same_origin_dest_port_fails(self):
        msg = MINIMAL_IFTMBF.replace('LOC+11+USNYC', 'LOC+11+CNSHA')
        result = process_edi_file(msg, self.customer, self.user)
        self.assertGreater(len(result['errors']), 0)
        self.assertEqual(len(result['created']), 0)

    def test_edi_fcl_no_container_creates_with_warning(self):
        # SAMPLE_IFTMBF is FCL (TSR+17++FCL) but has no container info.
        # Container fields should be soft warnings, not hard errors.
        result = process_edi_file(SAMPLE_IFTMBF, self.customer, self.user)
        self.assertEqual(len(result['created']), 1)
        container_warnings = [
            w for w in result['warnings']
            if 'container' in w.lower()
        ]
        self.assertGreater(len(container_warnings), 0)

    def test_edi_past_cargo_ready_date_fails(self):
        msg = SAMPLE_IFTMBF.replace('DTM+133:20260301:102', 'DTM+133:20200101:102')
        result = process_edi_file(msg, self.customer, self.user)
        self.assertGreater(len(result['errors']), 0)
        self.assertTrue(
            any('cargo_ready_date' in e or 'past' in e.lower() for e in result['errors']),
        )
        self.assertEqual(len(result['created']), 0)

    def test_edi_invalid_incoterms_fails(self):
        # Inject a bad incoterms via a modified parser output — easiest way
        # is to create a message with TSR that sets incoterms to an invalid code.
        # For this test, we patch the parser return value.
        from unittest.mock import patch
        parsed = {
            'booking_data': {
                'origin_port_code': 'CNSHA',
                'destination_port_code': 'USNYC',
                'transport_mode': 'SEA_FCL',
                'incoterms': 'INVALID',
                'cargo_ready_date': date.today() + timedelta(days=7),
            },
            'items_data': [
                {'description': 'Test', 'quantity': 1, 'weight_kg': 10},
            ],
            'parties_data': [],
            'issues': [],
        }
        with patch('integrations.edi.edi_service.parse_iftmbf', return_value=parsed):
            result = process_edi_file('dummy', self.customer, self.user)
        self.assertGreater(len(result['errors']), 0)
        self.assertTrue(
            any('incoterms' in e.lower() for e in result['errors']),
        )

    def test_edi_air_mode_no_container_no_warning(self):
        # AIR mode should NOT produce container warnings
        from unittest.mock import patch
        parsed = {
            'booking_data': {
                'origin_port_code': 'CNSHA',
                'destination_port_code': 'USNYC',
                'transport_mode': 'AIR',
                'incoterms': 'FOB',
                'cargo_ready_date': date.today() + timedelta(days=7),
            },
            'items_data': [
                {'description': 'Air cargo', 'quantity': 1, 'weight_kg': 50},
            ],
            'parties_data': [],
            'issues': [],
        }
        with patch('integrations.edi.edi_service.parse_iftmbf', return_value=parsed):
            result = process_edi_file('dummy', self.customer, self.user)
        self.assertEqual(len(result['created']), 1)
        container_warnings = [
            w for w in result['warnings'] if 'container' in w.lower()
        ]
        self.assertEqual(len(container_warnings), 0)


class TestEDIValidationEdgeCases(TestCase):
    """Edge case tests for EDI validation."""

    def setUp(self):
        self.customer = Customer.objects.create(
            name='Edge Corp', code='EDGE01', is_active=True,
            organization=get_default_org(),
        )
        Port.objects.create(code='CNSHA', name='Shanghai', country='CN')
        Port.objects.create(code='USNYC', name='New York', country='US')
        self.user = User.objects.create_user('edgeuser', 'edge@test.com', 'pass123')

    def test_edi_container_warnings_include_operator_message(self):
        result = process_edi_file(SAMPLE_IFTMBF, self.customer, self.user)
        container_warnings = [
            w for w in result['warnings'] if 'container' in w.lower()
        ]
        for w in container_warnings:
            self.assertIn('operator', w.lower())

    def test_edi_multiple_hard_errors_all_reported(self):
        # Same ports + bad incoterms + past date = multiple errors
        from unittest.mock import patch
        parsed = {
            'booking_data': {
                'origin_port_code': 'CNSHA',
                'destination_port_code': 'CNSHA',  # same port
                'transport_mode': 'SEA_FCL',
                'incoterms': 'INVALID',
                'cargo_ready_date': date(2020, 1, 1),  # past date
            },
            'items_data': [
                {'description': 'Test', 'quantity': 1, 'weight_kg': 10},
            ],
            'parties_data': [],
            'issues': [],
        }
        # Same-port error triggers early return before validation, so
        # use valid different ports but test incoterms + past date together.
        parsed['booking_data']['destination_port_code'] = 'USNYC'
        with patch('integrations.edi.edi_service.parse_iftmbf', return_value=parsed):
            result = process_edi_file('dummy', self.customer, self.user)
        # Should have both incoterms and cargo_ready_date errors
        self.assertGreaterEqual(len(result['errors']), 2)
