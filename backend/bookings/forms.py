import json
from django import forms
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory
from django.utils.safestring import mark_safe
from datetime import date
from .models import Booking, BookingItem, BookingDocument, BookingParty, Party, Port, Carrier, Customer
from . import validators


class BookingForm(forms.ModelForm):
    """Form for creating and editing bookings"""
    class Meta:
        model = Booking
        fields = [
            'transport_mode', 'service_type', 'move_type',
            'origin_port', 'destination_port', 'cargo_ready_date',
            'container_type', 'container_count',
            'chargeable_weight_kg', 'flight_number',
            'lcl_consolidation_number',
            'incoterms', 'incoterms_location',
            'commodity_description', 'is_hazardous',
            'external_reference', 'special_instructions',
        ]
        widgets = {
            'transport_mode': forms.Select(attrs={'class': 'form-select'}),
            'service_type': forms.Select(attrs={'class': 'form-select'}),
            'move_type': forms.Select(attrs={'class': 'form-select'}),
            'origin_port': forms.Select(attrs={'class': 'form-select'}),
            'destination_port': forms.Select(attrs={'class': 'form-select'}),
            'cargo_ready_date': forms.DateInput(
                attrs={'class': 'form-control', 'type': 'date'}
            ),
            'container_type': forms.Select(attrs={'class': 'form-select'}),
            'container_count': forms.NumberInput(
                attrs={'class': 'form-control', 'min': 1, 'max': 999}
            ),
            'chargeable_weight_kg': forms.NumberInput(
                attrs={'class': 'form-control', 'min': 0.01, 'step': '0.01',
                       'placeholder': 'Chargeable weight'}
            ),
            'flight_number': forms.TextInput(
                attrs={'class': 'form-control', 'placeholder': 'e.g. CX890'}
            ),
            'incoterms': forms.Select(attrs={'class': 'form-select'}),
            'incoterms_location': forms.TextInput(
                attrs={'class': 'form-control',
                       'placeholder': 'e.g. Shanghai Port, Warehouse A'}
            ),
            'commodity_description': forms.TextInput(
                attrs={'class': 'form-control',
                       'placeholder': 'e.g. Electronic components, textiles'}
            ),
            'is_hazardous': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'lcl_consolidation_number': forms.TextInput(
                attrs={'class': 'form-control',
                       'placeholder': 'e.g. CONSOL-2026-001'}
            ),
            'external_reference': forms.TextInput(
                attrs={'class': 'form-control',
                       'placeholder': 'Your reference number (e.g. PO-12345)'}
            ),
            'special_instructions': forms.Textarea(
                attrs={'class': 'form-control', 'rows': 2,
                       'placeholder': 'Any special handling or delivery instructions'}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        grouped, port_type_map = self._grouped_port_choices()
        self.fields['origin_port'].choices = grouped
        self.fields['destination_port'].choices = grouped
        # JSON map of port PK → port_type for JavaScript filtering
        self.port_type_map = mark_safe(json.dumps(port_type_map))
        self.fields['special_instructions'].required = False
        self.fields['incoterms_location'].required = False
        self.fields['commodity_description'].required = False
        self.fields['is_hazardous'].required = False
        self.fields['service_type'].required = False
        self.fields['move_type'].required = False
        # Mode-specific fields — all optional at form level; clean() enforces per mode
        self.fields['container_type'].required = False
        self.fields['container_count'].required = False
        self.fields['chargeable_weight_kg'].required = False
        self.fields['flight_number'].required = False
        self.fields['lcl_consolidation_number'].required = False

    def clean_cargo_ready_date(self):
        cargo_date = self.cleaned_data['cargo_ready_date']
        existing_date = self.instance.cargo_ready_date if self.instance and self.instance.pk else None
        err = validators.validate_cargo_ready_date(cargo_date, existing_date)
        if err:
            raise ValidationError(err)
        return cargo_date

    def clean_container_count(self):
        count = self.cleaned_data.get('container_count')
        if count is None:
            return None  # Allowed for non-FCL modes
        err = validators.validate_container_count(count)
        if err:
            raise ValidationError(err)
        return count

    def clean_incoterms(self):
        code = self.cleaned_data['incoterms']
        err = validators.validate_incoterms(code)
        if err:
            raise ValidationError(err)
        return code

    def clean(self):
        cleaned = super().clean()
        origin = cleaned.get('origin_port')
        dest = cleaned.get('destination_port')
        if origin and dest:
            err = validators.validate_ports_different(origin.pk, dest.pk)
            if err:
                raise ValidationError(err)

        # Mode-aware field validation and cross-mode cleanup
        mode = cleaned.get('transport_mode', '')

        # Server-side port type vs transport mode validation
        mode_port_types = {
            'SEA_FCL': ('SEA', 'BOTH'),
            'SEA_LCL': ('SEA', 'BOTH'),
            'AIR': ('AIR', 'BOTH'),
            'SEA_AIR': ('SEA', 'AIR', 'BOTH'),
            'AIR_SEA': ('SEA', 'AIR', 'BOTH'),
            'RAIL': ('SEA', 'AIR', 'BOTH', 'RAIL'),
            'TRUCK': ('SEA', 'AIR', 'BOTH', 'RAIL'),
            'MULTIMODAL': ('SEA', 'AIR', 'BOTH', 'RAIL'),
        }
        allowed_types = mode_port_types.get(mode)
        if allowed_types:
            if origin and origin.port_type not in allowed_types:
                self.add_error('origin_port', f'Port type {origin.port_type} is not compatible with {mode} transport mode.')
            if dest and dest.port_type not in allowed_types:
                self.add_error('destination_port', f'Port type {dest.port_type} is not compatible with {mode} transport mode.')

        # Service type: ocean routing (AWS/IPI/MLB/RIPI) or air level (Express/Standard/Deferred)
        OCEAN_MODES = ('SEA_FCL', 'SEA_LCL', 'SEA_AIR', 'AIR_SEA')
        if mode not in OCEAN_MODES and mode != 'AIR':
            cleaned['service_type'] = ''

        # Move type: cargo receipt & delivery terms — sea/hybrid modes only
        if mode not in OCEAN_MODES:
            cleaned['move_type'] = ''

        if mode == 'SEA_FCL':
            if not cleaned.get('container_type'):
                self.add_error('container_type', 'Container type is required for FCL shipments.')
            if not cleaned.get('container_count'):
                self.add_error('container_count', 'Container count is required for FCL shipments.')
            # Clear air and LCL fields
            cleaned['chargeable_weight_kg'] = None
            cleaned['flight_number'] = ''
            cleaned['lcl_consolidation_number'] = ''
        elif mode == 'SEA_LCL':
            # LCL: no containers (shared space), clear both container and air fields
            cleaned['container_type'] = None
            cleaned['container_count'] = None
            cleaned['chargeable_weight_kg'] = None
            cleaned['flight_number'] = ''
        elif mode == 'AIR':
            # Air: no containers, keep air-specific fields, clear LCL
            cleaned['container_type'] = None
            cleaned['container_count'] = None
            cleaned['lcl_consolidation_number'] = ''
        elif mode in ('SEA_AIR', 'AIR_SEA'):
            # Hybrid: container optional, air fields optional, LCL not applicable
            if not cleaned.get('container_type'):
                cleaned['container_type'] = None
            if not cleaned.get('container_count'):
                cleaned['container_count'] = None
            cleaned['lcl_consolidation_number'] = ''
        else:
            # RAIL, TRUCK, MULTIMODAL: container optional, clear air and LCL fields
            if not cleaned.get('container_type'):
                cleaned['container_type'] = None
            if not cleaned.get('container_count'):
                cleaned['container_count'] = None
            cleaned['chargeable_weight_kg'] = None
            cleaned['flight_number'] = ''
            cleaned['lcl_consolidation_number'] = ''

        return cleaned

    @staticmethod
    def _grouped_port_choices():
        """Build grouped choices and port_type map for JavaScript filtering.

        Returns:
            (choices, port_type_map) where:
            - choices: [(country, [(pk, label), ...]), ...]
            - port_type_map: {pk: port_type} dict for JS port filtering
        """
        ports = Port.objects.filter(is_active=True).order_by('country', 'name')
        groups = {}
        port_type_map = {}
        for port in ports:
            groups.setdefault(port.country, []).append(
                (port.pk, f"{port.code} - {port.name}")
            )
            port_type_map[str(port.pk)] = port.port_type
        choices = [('', '---------')]
        for country in sorted(groups.keys()):
            choices.append((country, groups[country]))
        return choices, port_type_map


class BookingItemForm(forms.ModelForm):
    """Form for a single cargo item with Phase 1.5 fields"""
    class Meta:
        model = BookingItem
        fields = [
            'description', 'package_type', 'quantity', 'weight_kg',
            'hs_code', 'volume_cbm', 'length_cm', 'width_cm', 'height_cm',
            'marks_and_numbers', 'is_hazardous', 'un_number', 'imo_class',
            'country_of_origin',
        ]
        widgets = {
            'description': forms.TextInput(
                attrs={'class': 'form-control', 'placeholder': 'e.g. LCD Monitors'}
            ),
            'package_type': forms.Select(attrs={'class': 'form-select'}),
            'quantity': forms.NumberInput(
                attrs={'class': 'form-control', 'min': 1, 'max': 99999}
            ),
            'weight_kg': forms.NumberInput(
                attrs={'class': 'form-control', 'min': 0.01, 'max': 99999999, 'step': '0.01'}
            ),
            'hs_code': forms.TextInput(
                attrs={'class': 'form-control', 'placeholder': '85287200',
                       'maxlength': 10}
            ),
            'volume_cbm': forms.NumberInput(
                attrs={'class': 'form-control', 'min': 0.001, 'step': '0.001',
                       'placeholder': 'CBM'}
            ),
            'length_cm': forms.NumberInput(
                attrs={'class': 'form-control', 'min': 0.01, 'step': '0.01',
                       'placeholder': 'L (cm)'}
            ),
            'width_cm': forms.NumberInput(
                attrs={'class': 'form-control', 'min': 0.01, 'step': '0.01',
                       'placeholder': 'W (cm)'}
            ),
            'height_cm': forms.NumberInput(
                attrs={'class': 'form-control', 'min': 0.01, 'step': '0.01',
                       'placeholder': 'H (cm)'}
            ),
            'marks_and_numbers': forms.TextInput(
                attrs={'class': 'form-control', 'placeholder': 'Shipping marks'}
            ),
            'is_hazardous': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'un_number': forms.TextInput(
                attrs={'class': 'form-control', 'placeholder': 'e.g. 1234',
                       'maxlength': 4}
            ),
            'imo_class': forms.TextInput(
                attrs={'class': 'form-control', 'placeholder': 'e.g. 3, 6.1',
                       'maxlength': 10}
            ),
            'country_of_origin': forms.TextInput(
                attrs={'class': 'form-control', 'placeholder': 'e.g. CN',
                       'maxlength': 2}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Mark Phase 1.5 fields as optional
        optional = [
            'hs_code', 'volume_cbm', 'length_cm', 'width_cm', 'height_cm',
            'marks_and_numbers', 'is_hazardous', 'un_number', 'imo_class',
            'country_of_origin',
        ]
        for field_name in optional:
            self.fields[field_name].required = False

    def clean_quantity(self):
        qty = self.cleaned_data['quantity']
        err = validators.validate_quantity(qty)
        if err:
            raise ValidationError(err)
        return qty

    def clean_weight_kg(self):
        weight = self.cleaned_data['weight_kg']
        err = validators.validate_weight_kg(weight)
        if err:
            raise ValidationError(err)
        return weight

    def clean_hs_code(self):
        code = self.cleaned_data.get('hs_code', '')
        if code:
            err = validators.validate_hs_code(code)
            if err:
                raise ValidationError(err)
        return code

    def clean_volume_cbm(self):
        vol = self.cleaned_data.get('volume_cbm')
        if vol is not None:
            err = validators.validate_volume_cbm(vol)
            if err:
                raise ValidationError(err)
        return vol

    def clean_country_of_origin(self):
        code = self.cleaned_data.get('country_of_origin', '')
        if code:
            code = code.upper()
            err = validators.validate_country_code(code)
            if err:
                raise ValidationError(err)
        return code

    def clean(self):
        cleaned = super().clean()

        # Validate dimensions together
        err = validators.validate_dimensions(
            cleaned.get('length_cm'), cleaned.get('width_cm'), cleaned.get('height_cm')
        )
        if err:
            raise ValidationError(err)

        # Validate hazardous fields together
        err = validators.validate_hazardous_fields(
            cleaned.get('is_hazardous', False),
            cleaned.get('un_number', ''),
            cleaned.get('imo_class', ''),
        )
        if err:
            raise ValidationError(err)

        return cleaned


BookingItemFormSet = inlineformset_factory(
    Booking, BookingItem,
    form=BookingItemForm,
    extra=1,
    min_num=1,
    max_num=50,
    validate_min=True,
    can_delete=True,
)


class BookingDocumentForm(forms.ModelForm):
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

    class Meta:
        model = BookingDocument
        fields = ['document_type', 'file', 'notes']
        widgets = {
            'document_type': forms.Select(attrs={'class': 'form-select'}),
            'file': forms.ClearableFileInput(attrs={
                'class': 'form-control',
                'accept': '.pdf,.jpg,.jpeg,.png,.xlsx,.csv'
            }),
            'notes': forms.TextInput(
                attrs={'class': 'form-control', 'placeholder': 'Optional notes'}
            ),
        }

    def clean_file(self):
        file = self.cleaned_data.get('file')
        if file:
            err = validators.validate_file_size(file.size)
            if err:
                raise ValidationError(err)
            err = validators.validate_file_extension(file.name)
            if err:
                raise ValidationError(err)
        return file


class PartyForm(forms.ModelForm):
    """Form for creating/editing address book parties."""
    class Meta:
        model = Party
        fields = [
            'role', 'company_name', 'contact_name', 'email', 'phone',
            'address_line_1', 'address_line_2', 'city', 'state',
            'postal_code', 'country_code', 'tax_id', 'is_default',
        ]
        widgets = {
            'role': forms.Select(attrs={'class': 'form-select'}),
            'company_name': forms.TextInput(attrs={'class': 'form-control'}),
            'contact_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'address_line_1': forms.TextInput(attrs={'class': 'form-control'}),
            'address_line_2': forms.TextInput(attrs={'class': 'form-control'}),
            'city': forms.TextInput(attrs={'class': 'form-control'}),
            'state': forms.TextInput(attrs={'class': 'form-control'}),
            'postal_code': forms.TextInput(attrs={'class': 'form-control'}),
            'country_code': forms.TextInput(
                attrs={'class': 'form-control', 'placeholder': 'e.g. US',
                       'maxlength': 2}
            ),
            'tax_id': forms.TextInput(attrs={'class': 'form-control'}),
            'is_default': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean_country_code(self):
        code = self.cleaned_data.get('country_code', '')
        if code:
            code = code.upper()
            err = validators.validate_country_code(code)
            if err:
                raise ValidationError(err)
        return code

    def clean_company_name(self):
        name = self.cleaned_data.get('company_name', '')
        err = validators.validate_party_company_name(name)
        if err:
            raise ValidationError(err)
        return name.strip()


class BookingPartySelectForm(forms.Form):
    """Form for selecting an existing party from the address book to add to a booking."""
    party = forms.ModelChoiceField(
        queryset=Party.objects.none(),
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Select from address book',
    )
    role = forms.ChoiceField(
        choices=BookingParty.ROLE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )

    def __init__(self, customer, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['party'].queryset = Party.objects.filter(
            customer=customer, is_active=True
        )


class CarrierDetailsForm(forms.ModelForm):
    """Form for staff to enter/edit carrier details on a booking."""
    carrier_select = forms.ModelChoiceField(
        queryset=Carrier.objects.filter(is_active=True),
        required=False,
        label='Select Carrier',
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text='Select a known carrier, or type a custom name below',
    )

    class Meta:
        model = Booking
        fields = [
            'carrier_config',
            'carrier_name', 'vessel_name', 'voyage_number',
            'cargo_cutoff_date', 'etd', 'eta',
            'carrier_booking_ref', 'contract_number',
            'hbl_number', 'mbl_number', 'hawb_number', 'mawb_number',
        ]
        widgets = {
            'carrier_config': forms.Select(
                attrs={'class': 'form-select'}
            ),
            'carrier_name': forms.TextInput(
                attrs={'class': 'form-control',
                       'placeholder': 'e.g. Maersk, MSC, CMA CGM'}
            ),
            'vessel_name': forms.TextInput(
                attrs={'class': 'form-control',
                       'placeholder': 'e.g. Maersk Elba'}
            ),
            'voyage_number': forms.TextInput(
                attrs={'class': 'form-control',
                       'placeholder': 'e.g. 428W'}
            ),
            'cargo_cutoff_date': forms.DateInput(
                attrs={'class': 'form-control', 'type': 'date'}
            ),
            'etd': forms.DateInput(
                attrs={'class': 'form-control', 'type': 'date'}
            ),
            'eta': forms.DateInput(
                attrs={'class': 'form-control', 'type': 'date'}
            ),
            'carrier_booking_ref': forms.TextInput(
                attrs={'class': 'form-control',
                       'placeholder': 'Carrier booking reference'}
            ),
            'contract_number': forms.TextInput(
                attrs={'class': 'form-control',
                       'placeholder': 'Internal contract number'}
            ),
            'hbl_number': forms.TextInput(
                attrs={'class': 'form-control',
                       'placeholder': 'House B/L number'}
            ),
            'mbl_number': forms.TextInput(
                attrs={'class': 'form-control',
                       'placeholder': 'Master B/L number'}
            ),
            'hawb_number': forms.TextInput(
                attrs={'class': 'form-control',
                       'placeholder': 'House Airway Bill number'}
            ),
            'mawb_number': forms.TextInput(
                attrs={'class': 'form-control',
                       'placeholder': 'Master Airway Bill number'}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in self.fields:
            self.fields[field_name].required = False
        # Only show active carrier configs in dropdown
        from integrations.models import CarrierConfig
        self.fields['carrier_config'].queryset = (
            CarrierConfig.objects.filter(is_active=True)
        )

    def clean(self):
        cleaned = super().clean()
        # Auto-fill carrier_name from carrier_select if not manually entered
        selected = cleaned.get('carrier_select')
        if selected and not cleaned.get('carrier_name'):
            cleaned['carrier_name'] = selected.name
        etd = cleaned.get('etd')
        eta = cleaned.get('eta')
        if etd and eta and eta < etd:
            raise ValidationError('ETA cannot be before ETD.')
        return cleaned


class MarkInTransitForm(forms.Form):
    """Form for staff to record actual departure date when marking in transit."""
    actual_departure_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control', 'type': 'date',
        }),
        label='Actual Departure Date',
        help_text='When did the vessel/flight actually depart?',
    )


class MarkArrivedForm(forms.Form):
    """Form for staff to record actual arrival date when marking arrived."""
    actual_arrival_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control', 'type': 'date',
        }),
        label='Actual Arrival Date',
        help_text='When did the cargo actually arrive at destination port?',
    )


class CompleteBookingForm(forms.Form):
    """Form for staff to record actual arrival date when completing a booking."""
    actual_arrival_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control', 'type': 'date',
        }),
        label='Actual Arrival Date',
        help_text='When did the cargo actually arrive at destination?',
    )


class RecordMilestoneForm(forms.Form):
    """Form for staff to record operational milestones."""
    milestone_type = forms.ChoiceField(
        choices=[],
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Milestone Type',
    )
    occurred_at = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={
            'class': 'form-control', 'type': 'datetime-local',
        }),
        label='Date & Time',
    )
    location = forms.CharField(
        max_length=200, required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control', 'placeholder': 'Port/location',
        }),
        label='Location',
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control', 'rows': 2,
            'placeholder': 'Additional notes (optional)',
        }),
        label='Notes',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from .models import ShipmentMilestone
        self.fields['milestone_type'].choices = ShipmentMilestone.MILESTONE_CHOICES


class CancelConfirmedForm(forms.Form):
    """Form for staff to cancel a confirmed booking with a reason."""
    reason = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Explain why this confirmed booking is being cancelled...',
        }),
        max_length=1000,
        label='Cancellation Reason',
    )


class RejectBookingForm(forms.Form):
    """Form for staff to enter a rejection reason."""
    reason = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Explain why this booking is being rejected...',
        }),
        max_length=1000,
        label='Rejection Reason',
    )


class CustomerRejectForm(forms.Form):
    """Form for customer to reject a confirmed booking with a reason."""
    reason = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Explain why you are rejecting this booking...',
        }),
        max_length=1000,
        label='Rejection Reason',
    )


class ConsolidationCreateForm(forms.Form):
    """Form to create a consolidation group and select bookings."""
    customer = forms.ModelChoiceField(
        queryset=Customer.objects.none(),
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_customer'}),
        label='Customer',
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2,
                                     'placeholder': 'Optional notes about this consolidation'}),
        label='Notes',
    )

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        qs = Customer.objects.filter(is_active=True)
        if organization:
            qs = qs.filter(organization=organization)
        self.fields['customer'].queryset = qs


class ConsolidationAddBookingForm(forms.Form):
    """Form to add a booking to an existing consolidation."""
    booking = forms.ModelChoiceField(
        queryset=Booking.objects.none(),
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Select Booking',
    )

    def __init__(self, consolidation, *args, **kwargs):
        super().__init__(*args, **kwargs)
        valid_statuses = ('SUBMITTED', 'CONFIRMED', 'PACKING', 'IN_TRANSIT', 'ARRIVED', 'COMPLETED')
        self.fields['booking'].queryset = (
            Booking.objects.filter(
                customer=consolidation.customer,
                status__in=valid_statuses,
                consolidation__isnull=True,
            )
            .select_related('origin_port', 'destination_port')
            .order_by('-created_at')
        )
        self.fields['booking'].label_from_instance = (
            lambda obj: f"{obj.booking_number} — {obj.origin_port.code}→{obj.destination_port.code} ({obj.get_status_display()})"
        )
