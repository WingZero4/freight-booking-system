"""
Tests for bookings.validators — pure validation functions (no database).

Uses SimpleTestCase for speed (no DB setup/teardown).
"""
from datetime import date, timedelta
from decimal import Decimal

from django.test import SimpleTestCase

from bookings import validators


# ─── Booking-level validators ────────────────────────────────────────


class TestValidatePortsDifferent(SimpleTestCase):

    def test_different_ports_valid(self):
        self.assertIsNone(validators.validate_ports_different(1, 2))

    def test_same_ports_invalid(self):
        err = validators.validate_ports_different(5, 5)
        self.assertIn('different', err)

    def test_none_origin_skipped(self):
        self.assertIsNone(validators.validate_ports_different(None, 2))

    def test_none_destination_skipped(self):
        self.assertIsNone(validators.validate_ports_different(1, None))

    def test_both_none_skipped(self):
        self.assertIsNone(validators.validate_ports_different(None, None))


class TestValidateCargoReadyDate(SimpleTestCase):

    def test_future_date_valid(self):
        self.assertIsNone(validators.validate_cargo_ready_date(date.today() + timedelta(days=7)))

    def test_today_valid(self):
        self.assertIsNone(validators.validate_cargo_ready_date(date.today()))

    def test_past_date_invalid(self):
        err = validators.validate_cargo_ready_date(date.today() - timedelta(days=1))
        self.assertIn('past', err)

    def test_edit_unchanged_date_allowed(self):
        past = date.today() - timedelta(days=5)
        self.assertIsNone(validators.validate_cargo_ready_date(past, existing_date=past))

    def test_edit_changed_past_date_invalid(self):
        err = validators.validate_cargo_ready_date(
            date.today() - timedelta(days=3),
            existing_date=date.today() - timedelta(days=5),
        )
        self.assertIn('past', err)

    def test_invalid_type_returns_error(self):
        err = validators.validate_cargo_ready_date('not-a-date')
        self.assertIn('Invalid date', err)


class TestValidateContainerCount(SimpleTestCase):

    def test_valid_count(self):
        self.assertIsNone(validators.validate_container_count(5))

    def test_min_boundary(self):
        self.assertIsNone(validators.validate_container_count(1))

    def test_max_boundary(self):
        self.assertIsNone(validators.validate_container_count(999))

    def test_zero_invalid(self):
        err = validators.validate_container_count(0)
        self.assertIn('between 1 and 999', err)

    def test_negative_invalid(self):
        err = validators.validate_container_count(-1)
        self.assertIsNotNone(err)

    def test_over_max_invalid(self):
        err = validators.validate_container_count(1000)
        self.assertIn('between 1 and 999', err)

    def test_non_numeric_invalid(self):
        err = validators.validate_container_count('abc')
        self.assertIn('number', err)

    def test_none_invalid(self):
        err = validators.validate_container_count(None)
        self.assertIn('number', err)


class TestValidateIncoterms(SimpleTestCase):

    def test_all_valid_codes(self):
        for code in validators.INCOTERMS_CODES:
            self.assertIsNone(validators.validate_incoterms(code), msg=f'{code} should be valid')

    def test_lowercase_accepted(self):
        self.assertIsNone(validators.validate_incoterms('fob'))

    def test_invalid_code(self):
        err = validators.validate_incoterms('XYZ')
        self.assertIn('Invalid INCOTERMS', err)

    def test_empty_required(self):
        err = validators.validate_incoterms('')
        self.assertIn('required', err)

    def test_none_required(self):
        err = validators.validate_incoterms(None)
        self.assertIn('required', err)


# ─── Cargo item validators ───────────────────────────────────────────


class TestValidateQuantity(SimpleTestCase):

    def test_valid_quantity(self):
        self.assertIsNone(validators.validate_quantity(10))

    def test_min_boundary(self):
        self.assertIsNone(validators.validate_quantity(1))

    def test_max_boundary(self):
        self.assertIsNone(validators.validate_quantity(99999))

    def test_zero_invalid(self):
        err = validators.validate_quantity(0)
        self.assertIn('at least 1', err)

    def test_negative_invalid(self):
        err = validators.validate_quantity(-5)
        self.assertIn('at least 1', err)

    def test_over_max_invalid(self):
        err = validators.validate_quantity(100000)
        self.assertIn('exceed', err)

    def test_non_numeric_invalid(self):
        err = validators.validate_quantity('abc')
        self.assertIn('whole number', err)

    def test_string_number_valid(self):
        self.assertIsNone(validators.validate_quantity('50'))


class TestValidateWeightKg(SimpleTestCase):

    def test_valid_weight(self):
        self.assertIsNone(validators.validate_weight_kg(100))

    def test_decimal_weight(self):
        self.assertIsNone(validators.validate_weight_kg(Decimal('50.55')))

    def test_max_boundary(self):
        self.assertIsNone(validators.validate_weight_kg(99999999))

    def test_zero_invalid(self):
        err = validators.validate_weight_kg(0)
        self.assertIn('greater than 0', err)

    def test_negative_invalid(self):
        err = validators.validate_weight_kg(-10)
        self.assertIn('greater than 0', err)

    def test_over_max_invalid(self):
        err = validators.validate_weight_kg(100000000)
        self.assertIn('exceeds maximum', err)

    def test_non_numeric_invalid(self):
        err = validators.validate_weight_kg('abc')
        self.assertIn('number', err)

    def test_string_number_valid(self):
        self.assertIsNone(validators.validate_weight_kg('250.5'))


class TestValidateVolumeCbm(SimpleTestCase):

    def test_valid_volume(self):
        self.assertIsNone(validators.validate_volume_cbm(Decimal('5.5')))

    def test_none_allowed(self):
        self.assertIsNone(validators.validate_volume_cbm(None))

    def test_empty_string_allowed(self):
        self.assertIsNone(validators.validate_volume_cbm(''))

    def test_zero_invalid(self):
        err = validators.validate_volume_cbm(0)
        self.assertIn('greater than 0', err)

    def test_negative_invalid(self):
        err = validators.validate_volume_cbm(-1)
        self.assertIn('greater than 0', err)

    def test_over_max_invalid(self):
        err = validators.validate_volume_cbm(10000000)
        self.assertIn('exceeds maximum', err)

    def test_max_boundary(self):
        self.assertIsNone(validators.validate_volume_cbm(9999999))

    def test_non_numeric_invalid(self):
        err = validators.validate_volume_cbm('abc')
        self.assertIn('number', err)


class TestValidateDimensions(SimpleTestCase):

    def test_all_valid(self):
        self.assertIsNone(validators.validate_dimensions(100, 50, 30))

    def test_all_none_valid(self):
        self.assertIsNone(validators.validate_dimensions(None, None, None))

    def test_all_empty_valid(self):
        self.assertIsNone(validators.validate_dimensions('', '', ''))

    def test_partial_dimensions_invalid(self):
        err = validators.validate_dimensions(100, None, 30)
        self.assertIn('all three', err)

    def test_one_provided_invalid(self):
        err = validators.validate_dimensions(100, None, None)
        self.assertIn('all three', err)

    def test_zero_dimension_invalid(self):
        err = validators.validate_dimensions(100, 0, 30)
        self.assertIn('greater than 0', err)

    def test_negative_dimension_invalid(self):
        err = validators.validate_dimensions(100, -5, 30)
        self.assertIn('greater than 0', err)

    def test_over_max_invalid(self):
        err = validators.validate_dimensions(1000000, 50, 30)
        self.assertIn('exceeds maximum', err)

    def test_non_numeric_invalid(self):
        err = validators.validate_dimensions('abc', 50, 30)
        self.assertIn('number', err)

    def test_max_boundary_valid(self):
        self.assertIsNone(validators.validate_dimensions(999999, 999999, 999999))


class TestValidateHsCode(SimpleTestCase):

    def test_six_digits_valid(self):
        self.assertIsNone(validators.validate_hs_code('852872'))

    def test_eight_digits_valid(self):
        self.assertIsNone(validators.validate_hs_code('85287200'))

    def test_ten_digits_valid(self):
        self.assertIsNone(validators.validate_hs_code('8528720000'))

    def test_empty_allowed(self):
        self.assertIsNone(validators.validate_hs_code(''))

    def test_none_allowed(self):
        self.assertIsNone(validators.validate_hs_code(None))

    def test_five_digits_invalid(self):
        err = validators.validate_hs_code('85287')
        self.assertIn('6 to 10 digits', err)

    def test_eleven_digits_invalid(self):
        err = validators.validate_hs_code('85287200001')
        self.assertIn('6 to 10 digits', err)

    def test_letters_invalid(self):
        err = validators.validate_hs_code('8528AB')
        self.assertIn('6 to 10 digits', err)

    def test_with_whitespace_stripped(self):
        self.assertIsNone(validators.validate_hs_code('  852872  '))


class TestValidateHazardousFields(SimpleTestCase):

    def test_not_hazardous_returns_none(self):
        self.assertIsNone(validators.validate_hazardous_fields(False))

    def test_hazardous_with_both_fields_valid(self):
        self.assertIsNone(validators.validate_hazardous_fields(True, '1234', '3'))

    def test_hazardous_missing_un_number(self):
        err = validators.validate_hazardous_fields(True, '', '3')
        self.assertIn('UN number is required', err)

    def test_hazardous_missing_imo_class(self):
        err = validators.validate_hazardous_fields(True, '1234', '')
        self.assertIn('IMO class is required', err)

    def test_hazardous_missing_both(self):
        err = validators.validate_hazardous_fields(True, '', '')
        self.assertIn('UN number', err)
        self.assertIn('IMO class', err)

    def test_invalid_un_number_format(self):
        err = validators.validate_hazardous_fields(True, '12', '3')
        self.assertIn('4 digits', err)

    def test_un_number_letters_invalid(self):
        err = validators.validate_hazardous_fields(True, 'ABCD', '3')
        self.assertIn('4 digits', err)


class TestValidateCountryCode(SimpleTestCase):

    def test_valid_code(self):
        self.assertIsNone(validators.validate_country_code('US'))

    def test_lowercase_uppercased(self):
        self.assertIsNone(validators.validate_country_code('cn'))

    def test_empty_allowed(self):
        self.assertIsNone(validators.validate_country_code(''))

    def test_none_allowed(self):
        self.assertIsNone(validators.validate_country_code(None))

    def test_three_letters_invalid(self):
        err = validators.validate_country_code('USA')
        self.assertIn('2-letter', err)

    def test_one_letter_invalid(self):
        err = validators.validate_country_code('U')
        self.assertIn('2-letter', err)

    def test_digits_invalid(self):
        err = validators.validate_country_code('12')
        self.assertIn('2-letter', err)


class TestValidatePackageType(SimpleTestCase):

    def test_all_valid_types(self):
        for ptype in validators.PACKAGE_TYPES:
            self.assertIsNone(validators.validate_package_type(ptype), msg=f'{ptype} should be valid')

    def test_lowercase_accepted(self):
        self.assertIsNone(validators.validate_package_type('pallet'))

    def test_invalid_type(self):
        err = validators.validate_package_type('CONTAINER')
        self.assertIn('Invalid package type', err)

    def test_empty_required(self):
        err = validators.validate_package_type('')
        self.assertIn('required', err)

    def test_none_required(self):
        err = validators.validate_package_type(None)
        self.assertIn('required', err)


# ─── Party validators ────────────────────────────────────────────────


class TestValidatePartyRole(SimpleTestCase):

    def test_all_valid_roles(self):
        for role in validators.PARTY_ROLES:
            self.assertIsNone(validators.validate_party_role(role), msg=f'{role} should be valid')

    def test_lowercase_accepted(self):
        self.assertIsNone(validators.validate_party_role('shipper'))

    def test_invalid_role(self):
        err = validators.validate_party_role('CAPTAIN')
        self.assertIn('Invalid party role', err)

    def test_empty_required(self):
        err = validators.validate_party_role('')
        self.assertIn('required', err)

    def test_none_required(self):
        err = validators.validate_party_role(None)
        self.assertIn('required', err)


class TestValidatePartyCompanyName(SimpleTestCase):

    def test_valid_name(self):
        self.assertIsNone(validators.validate_party_company_name('Acme Corp'))

    def test_empty_required(self):
        err = validators.validate_party_company_name('')
        self.assertIn('required', err)

    def test_whitespace_only_required(self):
        err = validators.validate_party_company_name('   ')
        self.assertIn('required', err)

    def test_none_required(self):
        err = validators.validate_party_company_name(None)
        self.assertIn('required', err)

    def test_max_length_valid(self):
        self.assertIsNone(validators.validate_party_company_name('A' * 255))

    def test_over_max_length_invalid(self):
        err = validators.validate_party_company_name('A' * 256)
        self.assertIn('255', err)


# ─── Document validators ─────────────────────────────────────────────


class TestValidateFileExtension(SimpleTestCase):

    def test_pdf_valid(self):
        self.assertIsNone(validators.validate_file_extension('invoice.pdf'))

    def test_jpg_valid(self):
        self.assertIsNone(validators.validate_file_extension('photo.jpg'))

    def test_jpeg_valid(self):
        self.assertIsNone(validators.validate_file_extension('photo.jpeg'))

    def test_png_valid(self):
        self.assertIsNone(validators.validate_file_extension('scan.png'))

    def test_xlsx_valid(self):
        self.assertIsNone(validators.validate_file_extension('data.xlsx'))

    def test_csv_valid(self):
        self.assertIsNone(validators.validate_file_extension('import.csv'))

    def test_exe_blocked(self):
        err = validators.validate_file_extension('virus.exe')
        self.assertIn('not allowed', err)

    def test_no_extension_blocked(self):
        err = validators.validate_file_extension('noext')
        self.assertIn('not allowed', err)

    def test_empty_filename(self):
        err = validators.validate_file_extension('')
        self.assertIn('No file', err)

    def test_none_filename(self):
        err = validators.validate_file_extension(None)
        self.assertIn('No file', err)

    def test_uppercase_extension_valid(self):
        # rsplit + .lower() in the code should handle this
        self.assertIsNone(validators.validate_file_extension('INVOICE.PDF'))


class TestValidateFileSize(SimpleTestCase):

    def test_under_limit_valid(self):
        self.assertIsNone(validators.validate_file_size(1024))

    def test_at_limit_valid(self):
        self.assertIsNone(validators.validate_file_size(10 * 1024 * 1024))

    def test_over_limit_invalid(self):
        err = validators.validate_file_size(10 * 1024 * 1024 + 1)
        self.assertIn('exceeds maximum', err)

    def test_zero_valid(self):
        self.assertIsNone(validators.validate_file_size(0))

    def test_large_file_shows_size_in_mb(self):
        err = validators.validate_file_size(15 * 1024 * 1024)
        self.assertIn('15.0 MB', err)


class TestValidateDocumentType(SimpleTestCase):

    def test_all_valid_types(self):
        for dt in validators.DOCUMENT_TYPES:
            self.assertIsNone(validators.validate_document_type(dt), msg=f'{dt} should be valid')

    def test_lowercase_accepted(self):
        self.assertIsNone(validators.validate_document_type('other'))

    def test_invalid_type(self):
        err = validators.validate_document_type('PHOTO')
        self.assertIn('Invalid document type', err)

    def test_empty_required(self):
        err = validators.validate_document_type('')
        self.assertIn('required', err)

    def test_none_required(self):
        err = validators.validate_document_type(None)
        self.assertIn('required', err)


# ─── Composite validators ────────────────────────────────────────────


class TestValidateBookingData(SimpleTestCase):

    def _valid_data(self, **overrides):
        data = {
            'origin_port': 1,
            'destination_port': 2,
            'cargo_ready_date': date.today() + timedelta(days=7),
            'container_count': 2,
            'incoterms': 'FOB',
        }
        data.update(overrides)
        return data

    def test_valid_data_no_errors(self):
        errors = validators.validate_booking_data(self._valid_data())
        self.assertEqual(errors, {})

    def test_same_ports_error(self):
        errors = validators.validate_booking_data(
            self._valid_data(origin_port=1, destination_port=1)
        )
        self.assertIn('__all__', errors)

    def test_past_date_error(self):
        errors = validators.validate_booking_data(
            self._valid_data(cargo_ready_date=date.today() - timedelta(days=1))
        )
        self.assertIn('cargo_ready_date', errors)

    def test_invalid_container_count_error(self):
        errors = validators.validate_booking_data(
            self._valid_data(container_count=0)
        )
        self.assertIn('container_count', errors)

    def test_invalid_incoterms_error(self):
        errors = validators.validate_booking_data(
            self._valid_data(incoterms='XYZ')
        )
        self.assertIn('incoterms', errors)

    def test_missing_incoterms_error(self):
        errors = validators.validate_booking_data(
            self._valid_data(incoterms=None)
        )
        self.assertIn('incoterms', errors)

    def test_edit_unchanged_date_no_error(self):
        past_date = date.today() - timedelta(days=5)

        class FakeBooking:
            cargo_ready_date = past_date

        errors = validators.validate_booking_data(
            self._valid_data(cargo_ready_date=past_date),
            is_edit=True,
            existing_booking=FakeBooking(),
        )
        self.assertNotIn('cargo_ready_date', errors)

    def test_multiple_errors(self):
        errors = validators.validate_booking_data({
            'origin_port': 1,
            'destination_port': 1,
            'cargo_ready_date': 'bad',
            'container_count': -1,
            'incoterms': '',
        })
        self.assertTrue(len(errors) >= 3)


class TestValidateBookingItemData(SimpleTestCase):

    def _valid_data(self, **overrides):
        data = {
            'description': 'LCD Monitors',
            'quantity': 10,
            'weight_kg': 250,
            'package_type': 'CARTON',
        }
        data.update(overrides)
        return data

    def test_valid_data_no_errors(self):
        errors = validators.validate_booking_item_data(self._valid_data())
        self.assertEqual(errors, {})

    def test_missing_description(self):
        errors = validators.validate_booking_item_data(self._valid_data(description=''))
        self.assertIn('description', errors)

    def test_long_description(self):
        errors = validators.validate_booking_item_data(
            self._valid_data(description='A' * 501)
        )
        self.assertIn('description', errors)

    def test_invalid_quantity(self):
        errors = validators.validate_booking_item_data(self._valid_data(quantity=0))
        self.assertIn('quantity', errors)

    def test_invalid_weight(self):
        errors = validators.validate_booking_item_data(self._valid_data(weight_kg=-1))
        self.assertIn('weight_kg', errors)

    def test_partial_dimensions_error(self):
        errors = validators.validate_booking_item_data(
            self._valid_data(length_cm=100, width_cm=None, height_cm=50)
        )
        self.assertIn('dimensions', errors)

    def test_valid_with_all_optional_fields(self):
        errors = validators.validate_booking_item_data(self._valid_data(
            hs_code='852872',
            volume_cbm=5.5,
            length_cm=100, width_cm=50, height_cm=30,
            is_hazardous=True, un_number='1234', imo_class='3',
            country_of_origin='CN',
        ))
        self.assertEqual(errors, {})

    def test_hazardous_missing_fields(self):
        errors = validators.validate_booking_item_data(
            self._valid_data(is_hazardous=True, un_number='', imo_class='')
        )
        self.assertIn('hazardous', errors)

    def test_invalid_country_code(self):
        errors = validators.validate_booking_item_data(
            self._valid_data(country_of_origin='USA')
        )
        self.assertIn('country_of_origin', errors)

    def test_invalid_package_type(self):
        errors = validators.validate_booking_item_data(
            self._valid_data(package_type='CONTAINER')
        )
        self.assertIn('package_type', errors)
