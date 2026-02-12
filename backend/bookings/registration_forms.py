from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password


class RegistrationForm(forms.Form):
    """Combined registration form: creates User + Customer + UserProfile."""

    # Personal info
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
        attrs={'class': 'form-control', 'placeholder': 'Choose a username'}
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

    # Company info
    company_name = forms.CharField(max_length=255, widget=forms.TextInput(
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
        if User.objects.filter(username=username, is_active=True).exists():
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
