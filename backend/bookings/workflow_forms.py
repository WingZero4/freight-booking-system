"""Forms for staff workflow management UI."""
from django import forms
from .models import (
    WorkflowTemplate, WorkflowStep, WorkflowTransition,
    CustomerWorkflowConfig, Booking, UserProfile, Customer,
)


class WorkflowTemplateForm(forms.ModelForm):
    """Create or edit a workflow template."""
    class Meta:
        model = WorkflowTemplate
        fields = ['name', 'description', 'is_default', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'is_default': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class WorkflowStepForm(forms.ModelForm):
    """Add or edit a workflow step."""
    class Meta:
        model = WorkflowStep
        fields = ['status', 'order', 'is_required', 'label_override']
        widgets = {
            'status': forms.Select(attrs={'class': 'form-select'}),
            'order': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'is_required': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'label_override': forms.TextInput(
                attrs={'class': 'form-control', 'placeholder': 'Leave blank for default'}),
        }


class WorkflowTransitionForm(forms.ModelForm):
    """Add or edit a workflow transition."""
    class Meta:
        model = WorkflowTransition
        fields = ['from_status', 'to_status', 'required_role', 'requires_reason', 'auto_skip']
        widgets = {
            'from_status': forms.Select(attrs={'class': 'form-select'}),
            'to_status': forms.Select(attrs={'class': 'form-select'}),
            'required_role': forms.Select(attrs={'class': 'form-select'}),
            'requires_reason': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'auto_skip': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class NewVersionForm(forms.Form):
    """Create a new version of a workflow template."""
    notes = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2,
                                     'placeholder': 'What changed in this version?'}),
        required=False,
    )
    copy_from_latest = forms.BooleanField(
        required=False, initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label='Copy steps and transitions from latest version',
    )


class CustomerWorkflowAssignForm(forms.Form):
    """Assign a workflow version to a customer."""
    customer = forms.ModelChoiceField(
        queryset=Customer.objects.none(),
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    workflow_version = forms.ChoiceField(
        widget=forms.Select(attrs={'class': 'form-select'}),
    )

    def __init__(self, organization, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['customer'].queryset = Customer.objects.filter(
            organization=organization, is_active=True,
        ).order_by('name')
        # Build version choices from active templates in this org
        from .models import WorkflowTemplateVersion
        versions = WorkflowTemplateVersion.objects.filter(
            template__organization=organization,
            template__is_active=True,
        ).select_related('template').order_by('template__name', '-version_number')
        choices = [('', '-- Select Workflow Version --')]
        for v in versions:
            choices.append((v.pk, f'{v.template.name} v{v.version_number}'))
        self.fields['workflow_version'].choices = choices
