"""
Workflow engine for configurable booking status lifecycles.

Validates transitions against the workflow template assigned to a booking's
customer. Falls back to unrestricted transitions when no workflow is configured,
maintaining backward compatibility with existing bookings.
"""
import logging

from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist

logger = logging.getLogger(__name__)

# Cache timeout for workflow data (5 minutes)
_CACHE_TTL = 300


class WorkflowEngine:
    """Validates and manages booking status transitions per workflow config."""

    @staticmethod
    def get_workflow_for_customer(customer):
        """Return the WorkflowTemplateVersion assigned to a customer, or None."""
        try:
            return customer.workflow_config.workflow_version
        except (ObjectDoesNotExist, AttributeError):
            return None

    @staticmethod
    def get_workflow_for_booking(booking):
        """Return the workflow version for a booking.

        Priority:
        1. Booking's own workflow_version FK (grandfathered)
        2. Customer's current workflow config
        3. None (no workflow — unrestricted)
        """
        if booking.workflow_version_id:
            return booking.workflow_version
        return WorkflowEngine.get_workflow_for_customer(booking.customer)

    @staticmethod
    def get_active_statuses(workflow_version):
        """Return ordered list of status codes active in this workflow version."""
        if workflow_version is None:
            return []
        cache_key = f'wf_statuses:{workflow_version.pk}'
        result = cache.get(cache_key)
        if result is None:
            result = list(
                workflow_version.steps
                .order_by('order')
                .values_list('status', flat=True)
            )
            cache.set(cache_key, result, _CACHE_TTL)
        return result

    @staticmethod
    def get_steps_map(workflow_version):
        """Return dict of {status: WorkflowStep} for all steps in this version."""
        if workflow_version is None:
            return {}
        cache_key = f'wf_steps_map:{workflow_version.pk}'
        result = cache.get(cache_key)
        if result is None:
            result = {
                step.status: step
                for step in workflow_version.steps.all()
            }
            cache.set(cache_key, result, _CACHE_TTL)
        return result

    @staticmethod
    def get_transitions_map(workflow_version):
        """Return dict of {from_status: [transition, ...]} for this version."""
        if workflow_version is None:
            return {}
        cache_key = f'wf_transitions:{workflow_version.pk}'
        result = cache.get(cache_key)
        if result is None:
            result = {}
            for t in workflow_version.transitions.all():
                result.setdefault(t.from_status, []).append(t)
            cache.set(cache_key, result, _CACHE_TTL)
        return result

    @staticmethod
    def get_allowed_transitions(workflow_version, current_status):
        """Return list of to_status codes allowed from current_status."""
        transitions_map = WorkflowEngine.get_transitions_map(workflow_version)
        transitions = transitions_map.get(current_status, [])
        return [t.to_status for t in transitions]

    @staticmethod
    def is_transition_allowed(workflow_version, from_status, to_status):
        """Check if a specific transition is allowed in this workflow."""
        if workflow_version is None:
            return True  # No workflow = unrestricted
        transitions_map = WorkflowEngine.get_transitions_map(workflow_version)
        transitions = transitions_map.get(from_status, [])
        return any(t.to_status == to_status for t in transitions)

    @staticmethod
    def get_transition(workflow_version, from_status, to_status):
        """Get the specific WorkflowTransition object, or None."""
        if workflow_version is None:
            return None
        transitions_map = WorkflowEngine.get_transitions_map(workflow_version)
        transitions = transitions_map.get(from_status, [])
        for t in transitions:
            if t.to_status == to_status:
                return t
        return None

    @staticmethod
    def get_next_status(workflow_version, current_status):
        """Return the next required status in the workflow, or None."""
        if workflow_version is None:
            return None
        statuses = WorkflowEngine.get_active_statuses(workflow_version)
        try:
            idx = statuses.index(current_status)
        except ValueError:
            return None
        # Find next required status
        steps_map = WorkflowEngine.get_steps_map(workflow_version)
        for next_status in statuses[idx + 1:]:
            step = steps_map.get(next_status)
            if step and step.is_required:
                return next_status
        return None

    @staticmethod
    def is_status_in_workflow(workflow_version, status):
        """Check if a status is part of this workflow."""
        if workflow_version is None:
            return True  # No workflow = all statuses valid
        return status in WorkflowEngine.get_active_statuses(workflow_version)

    @staticmethod
    def get_status_label(workflow_version, status):
        """Get the display label for a status (custom or default)."""
        from bookings.models import Booking
        if workflow_version is None:
            return dict(Booking.STATUS_CHOICES).get(status, status)
        steps_map = WorkflowEngine.get_steps_map(workflow_version)
        step = steps_map.get(status)
        if step and step.label_override:
            return step.label_override
        return dict(Booking.STATUS_CHOICES).get(status, status)

    @staticmethod
    def validate_transition(booking, to_status, user=None):
        """Validate whether a transition is allowed.

        Returns:
            (True, None) if allowed
            (False, error_message) if blocked
        """
        workflow = WorkflowEngine.get_workflow_for_booking(booking)

        # No workflow configured — use existing hardcoded logic (backward compat)
        if workflow is None:
            return True, None

        from_status = booking.status

        # Check transition exists in workflow
        if not WorkflowEngine.is_transition_allowed(workflow, from_status, to_status):
            allowed = WorkflowEngine.get_allowed_transitions(workflow, from_status)
            return False, (
                f'Transition from {from_status} to {to_status} is not allowed '
                f'in this workflow. Allowed: {", ".join(allowed) or "none"}'
            )

        # Check role requirement
        transition = WorkflowEngine.get_transition(workflow, from_status, to_status)
        if transition and transition.required_role:
            if not user:
                return False, (
                    f'This transition requires role {transition.required_role}. '
                    f'No user provided.'
                )
            profile = getattr(user, 'profile', None)
            if not profile:
                return False, (
                    f'This transition requires role {transition.required_role}. '
                    f'User has no profile.'
                )
            if profile.role != transition.required_role:
                return False, (
                    f'This transition requires role {transition.required_role}. '
                    f'Your role is {profile.role}.'
                )

        # Check company type requirement
        if transition and transition.allowed_company_types:
            profile = getattr(user, 'profile', None)
            if profile and profile.customer:
                user_company_types = profile.get_all_company_types()
                allowed_types = set(transition.allowed_company_types)
                if not user_company_types.intersection(allowed_types):
                    return False, (
                        f'This transition requires company type '
                        f'{", ".join(transition.allowed_company_types)}. '
                        f'Your company type(s): '
                        f'{", ".join(user_company_types) or "unset"}.'
                    )
            # Staff users (no customer) bypass company type checks

        return True, None

    @staticmethod
    def assign_workflow_to_booking(booking, customer=None):
        """Assign workflow version to a new booking based on customer config.

        Called during booking creation. Sets booking.workflow_version.
        Does NOT save the booking — caller must save.
        """
        customer = customer or booking.customer
        workflow = WorkflowEngine.get_workflow_for_customer(customer)
        if workflow:
            booking.workflow_version = workflow

    @staticmethod
    def invalidate_cache(workflow_version_id):
        """Invalidate cached data for a workflow version."""
        cache.delete(f'wf_statuses:{workflow_version_id}')
        cache.delete(f'wf_steps_map:{workflow_version_id}')
        cache.delete(f'wf_transitions:{workflow_version_id}')
