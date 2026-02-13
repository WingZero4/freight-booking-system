from django.contrib import messages
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .models import Customer, UserProfile
from .notifications import _send_notification
from .registration_views import _generate_customer_code
from .user_management_forms import CustomerUserForm, StaffUserForm, UserEditForm
from .views import staff_required


@staff_required
def ops_user_list(request):
    """List all users with search and type/status filtering."""
    users = User.objects.select_related('profile', 'profile__customer').order_by('-date_joined')

    type_filter = request.GET.get('type', '')
    if type_filter == 'staff':
        users = users.filter(Q(profile__isnull=True) | Q(profile__customer__isnull=True))
    elif type_filter == 'customer':
        users = users.filter(profile__customer__isnull=False)

    status_filter = request.GET.get('status', '')
    if status_filter == 'active':
        users = users.filter(is_active=True)
    elif status_filter == 'inactive':
        users = users.filter(is_active=False)

    search_query = request.GET.get('q', '')
    if search_query:
        users = users.filter(
            Q(username__icontains=search_query) |
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(profile__customer__name__icontains=search_query) |
            Q(profile__customer__code__icontains=search_query)
        )

    paginator = Paginator(users, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    # Ensure all users on this page have a profile (handles createsuperuser accounts)
    for u in page_obj:
        if not hasattr(u, '_profile_cache') or u._profile_cache is None:
            try:
                u.profile
            except UserProfile.DoesNotExist:
                UserProfile.objects.create(
                    user=u, role='ADMIN', approval_status='APPROVED',
                )

    return render(request, 'bookings/ops/user_list.html', {
        'page_obj': page_obj,
        'type_filter': type_filter,
        'status_filter': status_filter,
        'search_query': search_query,
    })


@staff_required
def ops_user_add_staff(request):
    """Create a new staff/ops user."""
    if request.method == 'POST':
        form = StaffUserForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                user = User.objects.create_user(
                    username=form.cleaned_data['username'],
                    email=form.cleaned_data['email'],
                    password=form.cleaned_data['password'],
                    first_name=form.cleaned_data['first_name'],
                    last_name=form.cleaned_data['last_name'],
                    is_active=True,
                    is_staff=True,
                )
                UserProfile.objects.create(
                    user=user,
                    customer=None,
                    role=form.cleaned_data['role'],
                    phone=form.cleaned_data.get('phone', ''),
                    approval_status='APPROVED',
                    approved_by=request.user,
                    approved_at=timezone.now(),
                )
            if user.email:
                _send_notification(
                    subject='Your Freight Booking Staff Account',
                    template_name='bookings/emails/user_created.html',
                    context={'user': user, 'customer': None, 'created_by': request.user},
                    recipient_list=[user.email],
                )
            messages.success(request, f'Staff user "{user.username}" created successfully.')
            return redirect('ops_user_list')
    else:
        form = StaffUserForm()

    return render(request, 'bookings/ops/user_form.html', {
        'form': form,
        'user_type': 'staff',
    })


@staff_required
def ops_user_add_customer(request):
    """Create a new customer user."""
    if request.method == 'POST':
        form = CustomerUserForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                if form.cleaned_data['customer_mode'] == 'new':
                    code = _generate_customer_code(form.cleaned_data['company_name'])
                    customer = Customer.objects.create(
                        code=code,
                        name=form.cleaned_data['company_name'],
                        email=form.cleaned_data.get('company_email', ''),
                        phone=form.cleaned_data.get('company_phone', ''),
                        address=form.cleaned_data.get('company_address', ''),
                        city=form.cleaned_data.get('company_city', ''),
                        country=form.cleaned_data.get('company_country', ''),
                        is_active=True,
                    )
                else:
                    customer = form.cleaned_data['existing_customer']

                user = User.objects.create_user(
                    username=form.cleaned_data['username'],
                    email=form.cleaned_data['email'],
                    password=form.cleaned_data['password'],
                    first_name=form.cleaned_data['first_name'],
                    last_name=form.cleaned_data['last_name'],
                    is_active=True,
                    is_staff=False,
                )
                UserProfile.objects.create(
                    user=user,
                    customer=customer,
                    role=form.cleaned_data['role'],
                    phone=form.cleaned_data.get('phone', ''),
                    approval_status='APPROVED',
                    approved_by=request.user,
                    approved_at=timezone.now(),
                )
            if user.email:
                _send_notification(
                    subject='Your Freight Booking Account',
                    template_name='bookings/emails/user_created.html',
                    context={'user': user, 'customer': customer, 'created_by': request.user},
                    recipient_list=[user.email],
                )
            messages.success(request, f'Customer user "{user.username}" created for {customer.name}.')
            return redirect('ops_user_list')
    else:
        form = CustomerUserForm()

    return render(request, 'bookings/ops/user_form.html', {
        'form': form,
        'user_type': 'customer',
    })


@staff_required
def ops_user_edit(request, user_id):
    """Edit an existing user's details."""
    target_user = get_object_or_404(
        User.objects.select_related('profile', 'profile__customer'), pk=user_id,
    )

    if target_user == request.user:
        messages.warning(request, 'You cannot edit your own account from here.')
        return redirect('ops_user_list')

    if target_user.is_superuser and not request.user.is_superuser:
        messages.error(request, 'Superuser accounts can only be modified by other superusers.')
        return redirect('ops_user_list')

    # Ensure profile exists for template rendering and form init
    UserProfile.objects.get_or_create(
        user=target_user,
        defaults={'role': 'ADMIN', 'approval_status': 'APPROVED'},
    )

    if request.method == 'POST':
        form = UserEditForm(request.POST, user_instance=target_user)
        if form.is_valid():
            with transaction.atomic():
                target_user.first_name = form.cleaned_data['first_name']
                target_user.last_name = form.cleaned_data['last_name']
                target_user.email = form.cleaned_data['email']
                target_user.is_active = form.cleaned_data['is_active']
                target_user.save(update_fields=['first_name', 'last_name', 'email', 'is_active'])

                profile = target_user.profile  # guaranteed to exist from get_or_create above
                profile.role = form.cleaned_data['role']
                profile.phone = form.cleaned_data.get('phone', '')
                profile.save(update_fields=['role', 'phone'])

            messages.success(request, f'User "{target_user.username}" updated successfully.')
            return redirect('ops_user_list')
    else:
        form = UserEditForm(user_instance=target_user)

    return render(request, 'bookings/ops/user_edit.html', {
        'form': form,
        'target_user': target_user,
    })


@staff_required
def ops_user_toggle_active(request, user_id):
    """Toggle a user's active status (POST only)."""
    if request.method != 'POST':
        return redirect('ops_user_list')

    target_user = get_object_or_404(User, pk=user_id)

    if target_user == request.user:
        messages.error(request, 'You cannot deactivate your own account.')
        return redirect('ops_user_list')

    if target_user.is_superuser and not request.user.is_superuser:
        messages.error(request, 'Superuser accounts can only be modified by other superusers.')
        return redirect('ops_user_list')

    target_user.is_active = not target_user.is_active
    target_user.save(update_fields=['is_active'])

    status = 'activated' if target_user.is_active else 'deactivated'
    messages.success(request, f'User "{target_user.username}" has been {status}.')
    return redirect('ops_user_list')
