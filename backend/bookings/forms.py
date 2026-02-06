from django import forms
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory
from datetime import date
from .models import Booking, BookingItem, BookingDocument, Port


class BookingForm(forms.ModelForm):
    """Form for creating and editing bookings"""
    class Meta:
        model = Booking
        fields = [
            'origin_port', 'destination_port', 'cargo_ready_date',
            'container_type', 'container_count', 'special_instructions'
        ]
        widgets = {
            'origin_port': forms.Select(attrs={'class': 'form-select'}),
            'destination_port': forms.Select(attrs={'class': 'form-select'}),
            'cargo_ready_date': forms.DateInput(
                attrs={'class': 'form-control', 'type': 'date'}
            ),
            'container_type': forms.Select(attrs={'class': 'form-select'}),
            'container_count': forms.NumberInput(
                attrs={'class': 'form-control', 'min': 1, 'max': 100}
            ),
            'special_instructions': forms.Textarea(
                attrs={'class': 'form-control', 'rows': 2,
                       'placeholder': 'Any special handling or delivery instructions'}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['origin_port'].queryset = Port.objects.filter(is_active=True)
        self.fields['destination_port'].queryset = Port.objects.filter(is_active=True)
        self.fields['special_instructions'].required = False

    def clean_cargo_ready_date(self):
        cargo_date = self.cleaned_data['cargo_ready_date']
        if cargo_date < date.today():
            raise ValidationError('Cargo ready date cannot be in the past.')
        return cargo_date

    def clean(self):
        cleaned = super().clean()
        origin = cleaned.get('origin_port')
        dest = cleaned.get('destination_port')
        if origin and dest and origin == dest:
            raise ValidationError('Origin and destination ports must be different.')
        return cleaned


class BookingItemForm(forms.ModelForm):
    """Form for a single cargo item"""
    class Meta:
        model = BookingItem
        fields = ['description', 'package_type', 'quantity', 'weight_kg']
        widgets = {
            'description': forms.TextInput(
                attrs={'class': 'form-control', 'placeholder': 'e.g. LCD Monitors'}
            ),
            'package_type': forms.Select(attrs={'class': 'form-select'}),
            'quantity': forms.NumberInput(
                attrs={'class': 'form-control', 'min': 1}
            ),
            'weight_kg': forms.NumberInput(
                attrs={'class': 'form-control', 'min': 0.01, 'step': '0.01'}
            ),
        }


BookingItemFormSet = inlineformset_factory(
    Booking, BookingItem,
    form=BookingItemForm,
    extra=1,
    min_num=1,
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
            if file.size > self.MAX_FILE_SIZE:
                raise ValidationError(
                    f'File size ({file.size / (1024*1024):.1f} MB) exceeds '
                    f'maximum allowed size (10 MB).'
                )
        return file
