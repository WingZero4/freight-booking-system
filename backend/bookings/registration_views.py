import re

from django.contrib import messages
from django.contrib.auth.models import User
from django.db import transaction
from django.shortcuts import redirect, render

from .models import Customer, UserProfile
from .notifications import _send_notification
from .registration_forms import RegistrationForm


def register(request):
    """Public registration page for new customers."""
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                # Clean up any previous rejected/inactive registration
                # with the same username or email
                old_user = User.objects.filter(
                    username=form.cleaned_data['username'],
                    is_active=False,
                ).first()
                if old_user:
                    # Delete old profile, customer, and user
                    try:
                        old_profile = old_user.profile
                        if old_profile.customer:
                            old_profile.customer.delete()
                        old_profile.delete()
                    except UserProfile.DoesNotExist:
                        pass
                    old_user.delete()

                code = _generate_customer_code(form.cleaned_data['company_name'])

                customer = Customer.objects.create(
                    code=code,
                    name=form.cleaned_data['company_name'],
                    email=form.cleaned_data.get('company_email', ''),
                    phone=form.cleaned_data.get('company_phone', ''),
                    address=form.cleaned_data.get('company_address', ''),
                    city=form.cleaned_data.get('company_city', ''),
                    country=form.cleaned_data.get('company_country', ''),
                    is_active=False,
                )

                user = User.objects.create_user(
                    username=form.cleaned_data['username'],
                    email=form.cleaned_data['email'],
                    password=form.cleaned_data['password'],
                    first_name=form.cleaned_data['first_name'],
                    last_name=form.cleaned_data['last_name'],
                    is_active=False,
                )

                UserProfile.objects.create(
                    user=user,
                    customer=customer,
                    role='USER',
                    phone=form.cleaned_data.get('phone', ''),
                    approval_status='PENDING',
                )

            _send_registration_received(user, customer)
            _send_staff_new_registration(user, customer)

            messages.success(
                request,
                'Your registration has been submitted. '
                'You will receive an email once your account has been approved.',
            )
            return redirect('login')
    else:
        form = RegistrationForm()

    return render(request, 'registration/register.html', {'form': form})


def _generate_customer_code(company_name):
    """Generate a unique customer code from company name."""
    words = re.sub(r'[^A-Za-z0-9 ]', '', company_name).split()
    base = words[0][:6].upper() if words else 'CUST'
    code = base
    counter = 1
    while Customer.objects.filter(code=code).exists():
        code = f"{base}{counter:02d}"
        counter += 1
    return code


def _send_registration_received(user, customer):
    _send_notification(
        subject='Registration Received - Pending Approval',
        template_name='registration/emails/registration_received.html',
        context={'user': user, 'customer': customer},
        recipient_list=[user.email],
    )


def _send_staff_new_registration(user, customer):
    staff_emails = list(
        User.objects.filter(
            is_staff=True, is_active=True,
        ).exclude(email='').values_list('email', flat=True)
    )
    ops_emails = list(
        UserProfile.objects.filter(
            customer__isnull=True,
            user__is_active=True,
        ).exclude(user__email='').values_list('user__email', flat=True)
    )
    all_emails = list(set(staff_emails + ops_emails))
    if all_emails:
        _send_notification(
            subject=f'New Registration: {customer.name} ({user.username})',
            template_name='registration/emails/new_registration_staff.html',
            context={'user': user, 'customer': customer},
            recipient_list=all_emails,
        )
