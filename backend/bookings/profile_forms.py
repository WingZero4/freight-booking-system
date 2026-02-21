import zoneinfo

from django import forms
from django.contrib.auth.models import User

TIMEZONE_CHOICES = [('', 'UTC (default)')] + [
    (tz, tz) for tz in sorted(zoneinfo.available_timezones())
]


class ProfileEditForm(forms.Form):
    first_name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    last_name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={'class': 'form-control'}),
    )
    phone = forms.CharField(
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    timezone = forms.ChoiceField(
        choices=TIMEZONE_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-control', 'id': 'id_timezone'}),
    )
    phone_notifications = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label='Receive SMS notifications for critical booking events',
    )
    whatsapp_notifications = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label='Receive WhatsApp notifications for critical booking events',
    )

    def __init__(self, *args, user_instance=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_instance = user_instance
        if user_instance and not self.is_bound:
            self.fields['first_name'].initial = user_instance.first_name
            self.fields['last_name'].initial = user_instance.last_name
            self.fields['email'].initial = user_instance.email
            profile = getattr(user_instance, 'profile', None)
            self.fields['phone'].initial = getattr(profile, 'phone', '')
            self.fields['timezone'].initial = getattr(profile, 'timezone', '')
            self.fields['phone_notifications'].initial = getattr(profile, 'phone_notifications', False)
            self.fields['whatsapp_notifications'].initial = getattr(profile, 'whatsapp_notifications', False)

    def clean_email(self):
        email = self.cleaned_data['email']
        qs = User.objects.filter(email__iexact=email, is_active=True)
        if self.user_instance:
            qs = qs.exclude(pk=self.user_instance.pk)
        if qs.exists():
            raise forms.ValidationError('This email address is already in use.')
        return email
