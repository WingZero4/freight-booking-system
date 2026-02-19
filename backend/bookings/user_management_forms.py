from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password

from .models import Customer, UserProfile


class StaffUserForm(forms.Form):
    """Form for ops admin to create a new staff/ops user."""

    first_name = forms.CharField(max_length=150, widget=forms.TextInput(
        attrs={'class': 'form-control', 'placeholder': 'First name'}
    ))
    last_name = forms.CharField(max_length=150, widget=forms.TextInput(
        attrs={'class': 'form-control', 'placeholder': 'Last name'}
    ))
    email = forms.EmailField(widget=forms.EmailInput(
        attrs={'class': 'form-control', 'placeholder': 'Email address'}
    ))
    phone = forms.CharField(max_length=50, required=False, widget=forms.TextInput(
        attrs={'class': 'form-control', 'placeholder': 'Phone number'}
    ))
    username = forms.CharField(max_length=150, widget=forms.TextInput(
        attrs={'class': 'form-control', 'placeholder': 'Username'}
    ))
    password = forms.CharField(widget=forms.PasswordInput(
        attrs={'class': 'form-control', 'placeholder': 'Password'}
    ))
    password_confirm = forms.CharField(
        label='Confirm Password',
        widget=forms.PasswordInput(
            attrs={'class': 'form-control', 'placeholder': 'Confirm password'}
        ),
    )
    role = forms.ChoiceField(
        choices=[('OPS', 'Operations'), ('ADMIN', 'Admin')],
        widget=forms.Select(attrs={'class': 'form-select'}),
    )

    def clean_username(self):
        username = self.cleaned_data['username']
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError('This username is already taken.')
        return username

    def clean_email(self):
        email = self.cleaned_data['email']
        if User.objects.filter(email=email, is_active=True).exists():
            raise forms.ValidationError('An account with this email already exists.')
        return email

    def clean(self):
        cleaned = super().clean()
        pw = cleaned.get('password')
        pw2 = cleaned.get('password_confirm')
        if pw and pw2 and pw != pw2:
            self.add_error('password_confirm', 'Passwords do not match.')
        if pw:
            user = User(
                username=cleaned.get('username', ''),
                email=cleaned.get('email', ''),
            )
            try:
                validate_password(pw, user)
            except forms.ValidationError as e:
                self.add_error('password', e)
        return cleaned


class CustomerUserForm(forms.Form):
    """Form for ops admin to create a new customer user."""

    first_name = forms.CharField(max_length=150, widget=forms.TextInput(
        attrs={'class': 'form-control', 'placeholder': 'First name'}
    ))
    last_name = forms.CharField(max_length=150, widget=forms.TextInput(
        attrs={'class': 'form-control', 'placeholder': 'Last name'}
    ))
    email = forms.EmailField(widget=forms.EmailInput(
        attrs={'class': 'form-control', 'placeholder': 'Email address'}
    ))
    phone = forms.CharField(max_length=50, required=False, widget=forms.TextInput(
        attrs={'class': 'form-control', 'placeholder': 'Phone number'}
    ))
    username = forms.CharField(max_length=150, widget=forms.TextInput(
        attrs={'class': 'form-control', 'placeholder': 'Username'}
    ))
    password = forms.CharField(widget=forms.PasswordInput(
        attrs={'class': 'form-control', 'placeholder': 'Password'}
    ))
    password_confirm = forms.CharField(
        label='Confirm Password',
        widget=forms.PasswordInput(
            attrs={'class': 'form-control', 'placeholder': 'Confirm password'}
        ),
    )
    role = forms.ChoiceField(
        choices=[('USER', 'User'), ('SHIPPER', 'Shipper'), ('ADMIN', 'Admin')],
        widget=forms.Select(attrs={'class': 'form-select'}),
    )

    # Customer assignment
    customer_mode = forms.ChoiceField(
        choices=[('existing', 'Assign to Existing Customer'), ('new', 'Create New Customer')],
        widget=forms.RadioSelect(),
        initial='existing',
    )
    existing_customer = forms.ModelChoiceField(
        queryset=Customer.objects.none(),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Select Customer',
    )

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        qs = Customer.objects.filter(is_active=True)
        if organization:
            qs = qs.filter(organization=organization)
        self.fields['existing_customer'].queryset = qs

    # New customer fields
    company_name = forms.CharField(max_length=255, required=False, widget=forms.TextInput(
        attrs={'class': 'form-control', 'placeholder': 'Company name'}
    ))
    company_email = forms.EmailField(required=False, widget=forms.EmailInput(
        attrs={'class': 'form-control', 'placeholder': 'Company email'}
    ))
    company_phone = forms.CharField(max_length=50, required=False, widget=forms.TextInput(
        attrs={'class': 'form-control', 'placeholder': 'Company phone'}
    ))
    company_address = forms.CharField(required=False, widget=forms.Textarea(
        attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Company address'}
    ))
    company_city = forms.CharField(max_length=100, required=False, widget=forms.TextInput(
        attrs={'class': 'form-control', 'placeholder': 'City'}
    ))
    company_country = forms.CharField(max_length=100, required=False, widget=forms.TextInput(
        attrs={'class': 'form-control', 'placeholder': 'Country'}
    ))

    def clean_username(self):
        username = self.cleaned_data['username']
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError('This username is already taken.')
        return username

    def clean_email(self):
        email = self.cleaned_data['email']
        if User.objects.filter(email=email, is_active=True).exists():
            raise forms.ValidationError('An account with this email already exists.')
        return email

    def clean(self):
        cleaned = super().clean()
        pw = cleaned.get('password')
        pw2 = cleaned.get('password_confirm')
        if pw and pw2 and pw != pw2:
            self.add_error('password_confirm', 'Passwords do not match.')
        if pw:
            user = User(
                username=cleaned.get('username', ''),
                email=cleaned.get('email', ''),
            )
            try:
                validate_password(pw, user)
            except forms.ValidationError as e:
                self.add_error('password', e)

        mode = cleaned.get('customer_mode')
        if mode == 'existing':
            if not cleaned.get('existing_customer'):
                self.add_error('existing_customer', 'Please select a customer.')
        elif mode == 'new':
            if not cleaned.get('company_name'):
                self.add_error('company_name', 'Company name is required for a new customer.')

        return cleaned


class UserEditForm(forms.Form):
    """Form for editing an existing user (staff or customer)."""

    first_name = forms.CharField(max_length=150, widget=forms.TextInput(
        attrs={'class': 'form-control'}
    ))
    last_name = forms.CharField(max_length=150, widget=forms.TextInput(
        attrs={'class': 'form-control'}
    ))
    email = forms.EmailField(widget=forms.EmailInput(
        attrs={'class': 'form-control'}
    ))
    phone = forms.CharField(max_length=50, required=False, widget=forms.TextInput(
        attrs={'class': 'form-control'}
    ))
    role = forms.ChoiceField(
        choices=[('OPS', 'Operations'), ('ADMIN', 'Admin')],
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    is_active = forms.BooleanField(required=False, widget=forms.CheckboxInput(
        attrs={'class': 'form-check-input'}
    ))

    def __init__(self, *args, user_instance=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_instance = user_instance
        if user_instance:
            self.fields['first_name'].initial = user_instance.first_name
            self.fields['last_name'].initial = user_instance.last_name
            self.fields['email'].initial = user_instance.email
            self.fields['is_active'].initial = user_instance.is_active
            try:
                profile = user_instance.profile
                self.fields['phone'].initial = profile.phone
                self.fields['role'].initial = profile.role
                if profile.customer:
                    self.fields['role'].choices = [('USER', 'User'), ('SHIPPER', 'Shipper'), ('ADMIN', 'Admin')]
                else:
                    self.fields['role'].choices = [('OPS', 'Operations'), ('ADMIN', 'Admin')]
            except UserProfile.DoesNotExist:
                self.fields['role'].choices = [('OPS', 'Operations'), ('ADMIN', 'Admin')]

    def clean_email(self):
        email = self.cleaned_data['email']
        qs = User.objects.filter(email=email, is_active=True)
        if self.user_instance:
            qs = qs.exclude(pk=self.user_instance.pk)
        if qs.exists():
            raise forms.ValidationError('An account with this email already exists.')
        return email
