from django import forms
from id_cards.forms import validate_phone
from id_cards.models import Level, Department, IDCardTemplate
from .models import Student


class StudentForm(forms.ModelForm):
    """Form for creating/editing a student ID card record."""

    class Meta:
        model = Student
        fields = [
            'full_name', 'gender', 'date_of_birth', 'photo',
            'level', 'department', 'guardian_name', 'guardian_phone',
            'valid_thru',
            'email', 'phone', 'address',
            'blood_group', 'emergency_contact_phone',
            'status', 'template',
        ]
        widgets = {
            'full_name':        forms.TextInput(attrs={'class': 'form-input', 'maxlength': 200}),
            'gender':           forms.Select(attrs={'class': 'form-input'}),
            'date_of_birth':    forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}),
            'photo':            forms.FileInput(attrs={'class': 'form-input', 'accept': 'image/*'}),
            'level':            forms.Select(attrs={'class': 'form-input'}),
            'department':       forms.Select(attrs={'class': 'form-input'}),
            'guardian_name':    forms.TextInput(attrs={'class': 'form-input', 'maxlength': 200}),
            'guardian_phone':   forms.TextInput(attrs={'class': 'form-input', 'maxlength': 30}),
            'valid_thru':       forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}),
            'email':            forms.EmailInput(attrs={'class': 'form-input'}),
            'phone':            forms.TextInput(attrs={'class': 'form-input', 'maxlength': 30}),
            'address':          forms.TextInput(attrs={'class': 'form-input', 'maxlength': 200}),
            'blood_group':      forms.Select(attrs={'class': 'form-input'}),
            'emergency_contact_phone': forms.TextInput(attrs={'class': 'form-input', 'maxlength': 30}),
            'status':           forms.Select(attrs={'class': 'form-input'}),
            'template':         forms.Select(attrs={'class': 'form-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['level'].queryset = Level.objects.all().order_by('order', 'name')
        self.fields['department'].queryset = Department.objects.filter(is_active=True).order_by('name')
        self.fields['template'].queryset = IDCardTemplate.objects.all()

        # Optional fields
        for name in (
            'template', 'photo', 'level', 'department', 'blood_group',
            'emergency_contact_phone', 'guardian_name', 'guardian_phone',
            'date_of_birth', 'valid_thru', 'email', 'phone', 'address',
        ):
            self.fields[name].required = False

        self.fields['template'].empty_label = '— Default Template —'
        self.fields['level'].empty_label = '— Select Level —'
        self.fields['department'].empty_label = '— Select Department —'

    def clean_full_name(self):
        name = self.cleaned_data.get('full_name', '').strip()
        name = ' '.join(name.split())
        if len(name) < 2:
            raise forms.ValidationError("Full name must be at least 2 characters.")
        return name

    def clean_phone(self):
        return validate_phone(self.cleaned_data.get('phone'), "Phone")

    def clean_guardian_phone(self):
        return validate_phone(self.cleaned_data.get('guardian_phone'), "Guardian phone")

    def clean_emergency_contact_phone(self):
        return validate_phone(
            self.cleaned_data.get('emergency_contact_phone'),
            "Emergency contact phone",
        )