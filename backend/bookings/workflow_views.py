"""Staff-facing views for workflow template management."""
from django.db import IntegrityError, transaction
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages

from .models import (
    WorkflowTemplate, WorkflowTemplateVersion, WorkflowStep,
    WorkflowTransition, CustomerWorkflowConfig, Booking,
)
from .workflow_forms import (
    WorkflowTemplateForm, WorkflowStepForm, WorkflowTransitionForm,
    NewVersionForm, CustomerWorkflowAssignForm,
)
from .views import staff_required
from .tenant import get_user_organization
from .workflow_engine import WorkflowEngine


def _version_is_locked(version):
    """Return True if any booking references this version (immutable)."""
    return Booking.objects.filter(workflow_version=version).exists()


def _clear_other_defaults(org, exclude_pk=None):
    """Ensure only one default workflow template per org."""
    qs = WorkflowTemplate.objects.filter(organization=org, is_default=True)
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    qs.update(is_default=False)


@staff_required
def workflow_list(request):
    """List all workflow templates for the user's organization."""
    org = get_user_organization(request.user)
    templates = WorkflowTemplate.objects.filter(
        organization=org
    ).prefetch_related('versions').order_by('-is_default', 'name')

    # Customer assignments overview
    assignments = CustomerWorkflowConfig.objects.filter(
        customer__organization=org,
    ).select_related('customer', 'workflow_version__template')

    return render(request, 'bookings/workflow_list.html', {
        'templates': templates,
        'assignments': assignments,
    })


@staff_required
def workflow_create(request):
    """Create a new workflow template."""
    org = get_user_organization(request.user)

    if request.method == 'POST':
        form = WorkflowTemplateForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    template = form.save(commit=False)
                    template.organization = org
                    template.save()
                    # Bug 3: Ensure only one default per org
                    if template.is_default:
                        _clear_other_defaults(org, exclude_pk=template.pk)
                messages.success(request, f'Workflow "{template.name}" created.')
                return redirect('workflow_detail', template_id=template.pk)
            except IntegrityError:
                form.add_error('name', 'A workflow with this name already exists.')
    else:
        form = WorkflowTemplateForm()

    return render(request, 'bookings/workflow_edit.html', {
        'form': form,
        'is_create': True,
    })


@staff_required
def workflow_detail(request, template_id):
    """View a workflow template with its versions, steps, and transitions."""
    org = get_user_organization(request.user)
    template = get_object_or_404(
        WorkflowTemplate, pk=template_id, organization=org)

    versions = template.versions.prefetch_related(
        'steps', 'transitions',
    ).order_by('-version_number')

    # Customers using this workflow
    assigned_customers = CustomerWorkflowConfig.objects.filter(
        workflow_version__template=template,
    ).select_related('customer', 'workflow_version')

    return render(request, 'bookings/workflow_detail.html', {
        'template': template,
        'versions': versions,
        'assigned_customers': assigned_customers,
    })


@staff_required
def workflow_edit(request, template_id):
    """Edit a workflow template's metadata."""
    org = get_user_organization(request.user)
    template = get_object_or_404(
        WorkflowTemplate, pk=template_id, organization=org)

    if request.method == 'POST':
        form = WorkflowTemplateForm(request.POST, instance=template)
        if form.is_valid():
            try:
                with transaction.atomic():
                    form.save()
                    # Bug 3: Ensure only one default per org
                    if template.is_default:
                        _clear_other_defaults(org, exclude_pk=template.pk)
                messages.success(request, f'Workflow "{template.name}" updated.')
                return redirect('workflow_detail', template_id=template.pk)
            except IntegrityError:
                form.add_error('name', 'A workflow with this name already exists.')
    else:
        form = WorkflowTemplateForm(instance=template)

    return render(request, 'bookings/workflow_edit.html', {
        'form': form,
        'template': template,
        'is_create': False,
    })


@staff_required
def workflow_new_version(request, template_id):
    """Create a new version of a workflow template."""
    org = get_user_organization(request.user)
    template = get_object_or_404(
        WorkflowTemplate, pk=template_id, organization=org)

    latest_version = template.versions.order_by('-version_number').first()
    next_number = (latest_version.version_number + 1) if latest_version else 1

    if request.method == 'POST':
        form = NewVersionForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                # Bug 2: Recompute next_number inside atomic block to avoid race
                latest_in_tx = (
                    template.versions
                    .select_for_update()
                    .order_by('-version_number')
                    .first()
                )
                safe_number = (latest_in_tx.version_number + 1) if latest_in_tx else 1
                version = WorkflowTemplateVersion.objects.create(
                    template=template,
                    version_number=safe_number,
                    created_by=request.user,
                    notes=form.cleaned_data['notes'],
                )
                # Copy steps and transitions from latest version
                if form.cleaned_data.get('copy_from_latest') and latest_in_tx:
                    for step in latest_in_tx.steps.all():
                        WorkflowStep.objects.create(
                            version=version,
                            status=step.status,
                            order=step.order,
                            is_required=step.is_required,
                            label_override=step.label_override,
                        )
                    for trans in latest_in_tx.transitions.all():
                        WorkflowTransition.objects.create(
                            version=version,
                            from_status=trans.from_status,
                            to_status=trans.to_status,
                            required_role=trans.required_role,
                            requires_reason=trans.requires_reason,
                            auto_skip=trans.auto_skip,
                        )

            messages.success(request, f'Version {safe_number} created.')
            return redirect('workflow_version_detail',
                            template_id=template.pk, version_id=version.pk)
    else:
        form = NewVersionForm()

    return render(request, 'bookings/workflow_new_version.html', {
        'form': form,
        'template': template,
        'next_number': next_number,
        'latest_version': latest_version,
    })


@staff_required
def workflow_version_detail(request, template_id, version_id):
    """View and manage steps/transitions for a workflow version."""
    org = get_user_organization(request.user)
    template = get_object_or_404(
        WorkflowTemplate, pk=template_id, organization=org)
    version = get_object_or_404(
        WorkflowTemplateVersion, pk=version_id, template=template)

    locked = _version_is_locked(version)
    steps = version.steps.order_by('order')
    transitions = version.transitions.order_by('from_status', 'to_status')

    # Forms for adding new step/transition (only if not locked)
    step_form = WorkflowStepForm() if not locked else None
    transition_form = WorkflowTransitionForm() if not locked else None

    return render(request, 'bookings/workflow_version_detail.html', {
        'template': template,
        'version': version,
        'steps': steps,
        'transitions': transitions,
        'step_form': step_form,
        'transition_form': transition_form,
        'locked': locked,
    })


@staff_required
def workflow_add_step(request, template_id, version_id):
    """Add a step to a workflow version."""
    org = get_user_organization(request.user)
    template = get_object_or_404(
        WorkflowTemplate, pk=template_id, organization=org)
    version = get_object_or_404(
        WorkflowTemplateVersion, pk=version_id, template=template)

    if request.method == 'POST':
        form = WorkflowStepForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    # Re-check lock inside transaction to prevent TOCTOU
                    if _version_is_locked(version):
                        messages.error(request, 'This version is locked (in use by bookings) and cannot be modified.')
                        return redirect('workflow_version_detail',
                                        template_id=template.pk, version_id=version.pk)
                    step = form.save(commit=False)
                    step.version = version
                    step.save()
                WorkflowEngine.invalidate_cache(version.pk)
                messages.success(request, f'Step "{step.get_status_display()}" added.')
            except IntegrityError:
                messages.error(request, 'This status already exists in this version.')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{field}: {error}')

    return redirect('workflow_version_detail',
                    template_id=template.pk, version_id=version.pk)


@staff_required
def workflow_remove_step(request, template_id, version_id, step_id):
    """Remove a step from a workflow version."""
    org = get_user_organization(request.user)
    template = get_object_or_404(
        WorkflowTemplate, pk=template_id, organization=org)
    version = get_object_or_404(
        WorkflowTemplateVersion, pk=version_id, template=template)

    if request.method == 'POST':
        with transaction.atomic():
            if _version_is_locked(version):
                messages.error(request, 'This version is locked (in use by bookings) and cannot be modified.')
                return redirect('workflow_version_detail',
                                template_id=template.pk, version_id=version.pk)
            step = get_object_or_404(WorkflowStep, pk=step_id, version=version)
            step.delete()
        WorkflowEngine.invalidate_cache(version.pk)
        messages.success(request, 'Step removed.')

    return redirect('workflow_version_detail',
                    template_id=template.pk, version_id=version.pk)


@staff_required
def workflow_add_transition(request, template_id, version_id):
    """Add a transition to a workflow version."""
    org = get_user_organization(request.user)
    template = get_object_or_404(
        WorkflowTemplate, pk=template_id, organization=org)
    version = get_object_or_404(
        WorkflowTemplateVersion, pk=version_id, template=template)

    if request.method == 'POST':
        form = WorkflowTransitionForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    if _version_is_locked(version):
                        messages.error(request, 'This version is locked (in use by bookings) and cannot be modified.')
                        return redirect('workflow_version_detail',
                                        template_id=template.pk, version_id=version.pk)
                    transition = form.save(commit=False)
                    transition.version = version
                    transition.save()
                WorkflowEngine.invalidate_cache(version.pk)
                messages.success(
                    request,
                    f'Transition {transition.get_from_status_display()} '
                    f'\u2192 {transition.get_to_status_display()} added.')
            except IntegrityError:
                messages.error(request, 'This transition already exists in this version.')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{field}: {error}')

    return redirect('workflow_version_detail',
                    template_id=template.pk, version_id=version.pk)


@staff_required
def workflow_remove_transition(request, template_id, version_id, transition_id):
    """Remove a transition from a workflow version."""
    org = get_user_organization(request.user)
    template = get_object_or_404(
        WorkflowTemplate, pk=template_id, organization=org)
    version = get_object_or_404(
        WorkflowTemplateVersion, pk=version_id, template=template)

    if request.method == 'POST':
        with transaction.atomic():
            if _version_is_locked(version):
                messages.error(request, 'This version is locked (in use by bookings) and cannot be modified.')
                return redirect('workflow_version_detail',
                                template_id=template.pk, version_id=version.pk)
            transition = get_object_or_404(
                WorkflowTransition, pk=transition_id, version=version)
            transition.delete()
        WorkflowEngine.invalidate_cache(version.pk)
        messages.success(request, 'Transition removed.')

    return redirect('workflow_version_detail',
                    template_id=template.pk, version_id=version.pk)


@staff_required
def workflow_assign(request):
    """Assign or reassign a workflow version to a customer."""
    org = get_user_organization(request.user)

    if request.method == 'POST':
        form = CustomerWorkflowAssignForm(org, request.POST)
        if form.is_valid():
            customer = form.cleaned_data['customer']
            version_pk = form.cleaned_data['workflow_version']
            version = get_object_or_404(
                WorkflowTemplateVersion, pk=version_pk,
                template__organization=org)
            config, created = CustomerWorkflowConfig.objects.update_or_create(
                customer=customer,
                defaults={
                    'workflow_version': version,
                    'assigned_by': request.user,
                },
            )
            action = 'assigned' if created else 'updated'
            messages.success(
                request,
                f'Workflow {version} {action} to {customer.name}.')
            return redirect('workflow_list')
    else:
        form = CustomerWorkflowAssignForm(org)

    return render(request, 'bookings/workflow_assign.html', {
        'form': form,
    })
