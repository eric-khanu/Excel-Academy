from django import forms
from django.core.validators import FileExtensionValidator
from .models import Teacher, School, IDCardTemplate, Department, Level


# ============================================================================
# TEACHER FORM
# ============================================================================
class TeacherForm(forms.ModelForm):
    """Form for creating/editing a staff member's ID card record."""

    class Meta:
        model = Teacher
        fields = [
            # Identity
            'full_name', 'designation', 'photo', 'role',
            # Employment
            'department', 'levels', 'valid_thru',
            # Contact
            'email', 'phone',
            # Back-of-card
            'blood_group', 'emergency_contact_phone',
            # Card settings
            'status', 'template',
        ]
        widgets = {
            'full_name': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'e.g. Sarah Elizabeth Chen',
                'autocomplete': 'off',
            }),
            'designation': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'e.g. Senior Mathematics Teacher',
                'autocomplete': 'off',
            }),
            'photo': forms.FileInput(attrs={
                'class': 'form-input',
                'accept': 'image/png, image/jpeg, image/jpg',
            }),
            'role': forms.Select(attrs={'class': 'form-input'}),
            'department': forms.Select(attrs={'class': 'form-input'}),
            'levels': forms.SelectMultiple(attrs={
                'class': 'form-input',
                'size': '6',
            }),
            'valid_thru': forms.DateInput(attrs={
                'class': 'form-input',
                'type': 'date',
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-input',
                'placeholder': 'name@school.edu',
                'autocomplete': 'off',
            }),
            'phone': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': '+234 800 000 0000',
                'autocomplete': 'off',
            }),
            # Blood group is now a dropdown (matches model choices)
            'blood_group': forms.Select(attrs={'class': 'form-input'}),
            'emergency_contact_phone': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': '+234 800 000 0000',
                'autocomplete': 'off',
            }),
            'status': forms.Select(attrs={'class': 'form-input'}),
            'template': forms.Select(attrs={'class': 'form-input'}),
        }
        help_texts = {
            'role': 'Staff role — displayed on the card.',
            'designation': 'Full job title as it should appear on the card.',
            'levels': 'Hold Ctrl (Windows) or Cmd (Mac) to select multiple levels.',
            'template': 'Leave blank to use the default card layout.',
            'photo': 'Square image works best (400×400px or larger).',
            'blood_group': 'Optional — shown on the back of the card.',
            'emergency_contact_phone': 'Optional — shown on the back of the card.',
        }
        labels = {
            'full_name': 'Full Name',
            'valid_thru': 'Valid Thru',
            'employee_id': 'Employee ID',
            'emergency_contact_phone': 'Emergency Contact Phone',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Only show active departments in the dropdown
        self.fields['department'].queryset = (
            Department.objects.filter(is_active=True).order_by('name')
        )
        self.fields['department'].empty_label = '— Select Department —'

        # Order levels by their sort order
        self.fields['levels'].queryset = (
            Level.objects.all().order_by('order', 'name')
        )

        # Optional fields
        self.fields['template'].required = False
        self.fields['template'].empty_label = '— Default Template —'
        self.fields['photo'].required = False
        self.fields['levels'].required = False
        self.fields['department'].required = False
        self.fields['blood_group'].required = False
        self.fields['emergency_contact_phone'].required = False

        # Ensure the blank option for blood_group is present and labeled
        # (the model already provides ('', '— Select Blood Group —'))
        self.fields['blood_group'].choices = Teacher.BLOOD_GROUP_CHOICES

    # ------------------------------------------------------------------ #
    #  Custom validation                                                  #
    # ------------------------------------------------------------------ #
    def clean_full_name(self):
        """Trim + collapse extra whitespace, enforce minimum length."""
        name = self.cleaned_data.get('full_name', '').strip()
        name = ' '.join(name.split())
        if len(name) < 2:
            raise forms.ValidationError("Full name must be at least 2 characters.")
        return name

    def clean_designation(self):
        desig = self.cleaned_data.get('designation', '').strip()
        desig = ' '.join(desig.split())
        if len(desig) < 2:
            raise forms.ValidationError("Designation must be at least 2 characters.")
        return desig

    def clean_phone(self):
        """Basic phone sanitisation — strip spaces/dashes but keep +."""
        phone = self.cleaned_data.get('phone', '').strip()
        if phone:
            allowed = set('+0123456789 -()')
            if not all(c in allowed for c in phone):
                raise forms.ValidationError(
                    "Phone can only contain digits, +, spaces, dashes, and parentheses."
                )
        return phone

    def clean_emergency_contact_phone(self):
        """Same rules as the primary phone."""
        phone = self.cleaned_data.get('emergency_contact_phone', '').strip()
        if phone:
            allowed = set('+0123456789 -()')
            if not all(c in allowed for c in phone):
                raise forms.ValidationError(
                    "Emergency contact phone can only contain digits, +, "
                    "spaces, dashes, and parentheses."
                )
        return phone

    def clean_email(self):
        return self.cleaned_data.get('email', '').strip().lower()

    # NOTE: clean_blood_group() has been removed — the model's `choices`
    # on Teacher.BLOOD_GROUP_CHOICES handles validation automatically.

    def clean_photo(self):
        """Enforce a maximum image size (5 MB) to avoid huge uploads."""
        photo = self.cleaned_data.get('photo')
        if photo and hasattr(photo, 'size'):
            if photo.size > 5 * 1024 * 1024:
                raise forms.ValidationError("Photo must be smaller than 5 MB.")
        return photo

    def clean(self):
        """Cross-field validation."""
        cleaned = super().clean()

        role = cleaned.get('role')
        department = cleaned.get('department')

        # TEACHER role should have a department
        if role == 'TEACHER' and not department:
            self.add_error(
                'department',
                "Teachers should be assigned to a department."
            )

        # Only TEACHER role should have assigned levels
        if role and role != 'TEACHER' and cleaned.get('levels'):
            self.add_error(
                'levels',
                "Only staff with the 'Teacher' role typically have assigned levels."
            )

        return cleaned


# ============================================================================
# SCHOOL BRANDING FORM
# ============================================================================
class SchoolForm(forms.ModelForm):
    """Form for editing the singleton School branding record."""

    class Meta:
        model = School
        fields = [
            'name', 'short_name', 'established',
            'tagline', 'scripture_ref', 'address',
            'contact_phone_1', 'contact_phone_2',
            'logo',
            'primary_color', 'secondary_color', 'accent_color', 'text_color',
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'e.g. Excel Junior Secondary School',
                'autocomplete': 'off',
            }),
            'short_name': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'e.g. EJSS',
                'autocomplete': 'off',
                'maxlength': 10,
            }),
            'established': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'e.g. 1995',
                'autocomplete': 'off',
                'maxlength': 20,
            }),
            'tagline': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'Short motto or mission statement',
                'autocomplete': 'off',
            }),
            'scripture_ref': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'e.g. 2 Chronicles 15:7',
                'autocomplete': 'off',
            }),
            'address': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'School address',
                'autocomplete': 'off',
            }),
            'contact_phone_1': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': '+234 800 000 0000',
                'autocomplete': 'off',
            }),
            'contact_phone_2': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': '+234 800 000 0000 (optional)',
                'autocomplete': 'off',
            }),
            'logo': forms.FileInput(attrs={
                'class': 'form-input',
                'accept': 'image/png, image/jpeg, image/jpg, image/svg+xml',
            }),
            'primary_color':   forms.TextInput(attrs={'type': 'color', 'class': 'color-input'}),
            'secondary_color': forms.TextInput(attrs={'type': 'color', 'class': 'color-input'}),
            'accent_color':    forms.TextInput(attrs={'type': 'color', 'class': 'color-input'}),
            'text_color':      forms.TextInput(attrs={'type': 'color', 'class': 'color-input'}),
        }
        help_texts = {
            'short_name': 'Used as the prefix for auto-generated Employee IDs '
                          '(e.g. EJSS → EJSS-2026-001).',
            'address': 'Displayed on the back of the card.',
            'contact_phone_1': 'Primary phone shown on the back of the card.',
            'contact_phone_2': 'Optional second phone number.',
            'logo': 'PNG with transparent background works best.',
            'primary_color': 'Header background & headlines.',
            'secondary_color': 'Accents, borders, and gold bars.',
            'accent_color': 'Card background & soft fills.',
            'text_color': 'Body copy on light surfaces.',
        }

    # ------------------------------------------------------------------ #
    #  Validation                                                         #
    # ------------------------------------------------------------------ #
    def clean_short_name(self):
        """Uppercase, strip spaces, and enforce a safe format."""
        value = self.cleaned_data.get('short_name', '').strip().upper()
        cleaned = ''.join(c for c in value if c.isalnum() or c == '-')
        if len(cleaned) < 2:
            raise forms.ValidationError("Short name must be at least 2 characters.")
        if len(cleaned) > 10:
            raise forms.ValidationError("Short name must be 10 characters or fewer.")
        return cleaned

    def clean_logo(self):
        """Enforce a maximum file size of 2 MB."""
        logo = self.cleaned_data.get('logo')
        if logo and hasattr(logo, 'size') and logo.size > 2 * 1024 * 1024:
            raise forms.ValidationError("Logo must be smaller than 2 MB.")
        return logo

    def clean_contact_phone_1(self):
        return self._clean_phone(self.cleaned_data.get('contact_phone_1'))

    def clean_contact_phone_2(self):
        return self._clean_phone(self.cleaned_data.get('contact_phone_2'))

    @staticmethod
    def _clean_phone(value):
        value = (value or '').strip()
        if value:
            allowed = set('+0123456789 -()')
            if not all(c in allowed for c in value):
                raise forms.ValidationError(
                    "Phone can only contain digits, +, spaces, dashes, and parentheses."
                )
        return value

    def clean_primary_color(self):
        return self._clean_hex(self.cleaned_data.get('primary_color'))

    def clean_secondary_color(self):
        return self._clean_hex(self.cleaned_data.get('secondary_color'))

    def clean_accent_color(self):
        return self._clean_hex(self.cleaned_data.get('accent_color'))

    def clean_text_color(self):
        return self._clean_hex(self.cleaned_data.get('text_color'))

    @staticmethod
    def _clean_hex(value):
        """Ensure the color is a valid 6-digit hex code."""
        value = (value or '').strip()
        if not value.startswith('#'):
            value = '#' + value
        if len(value) != 7:
            raise forms.ValidationError(
                "Color must be a valid 6-digit hex code, e.g. #8B2020."
            )
        return value.upper()


# ============================================================================
# DEPARTMENT FORM
# ============================================================================
class DepartmentForm(forms.ModelForm):
    """Form for creating/editing a department. Code is auto-generated if blank."""

    class Meta:
        model = Department
        fields = ['name', 'code', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'e.g. Basic Science',
                'autocomplete': 'off',
            }),
            'code': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'Auto-generated if left blank',
                'autocomplete': 'off',
                'maxlength': 10,
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
        }
        help_texts = {
            'name': 'Full department name, e.g. Mathematics, Science, Administration.',
            'code': 'Leave blank to auto-generate from the name (Science → SCI).',
            'is_active': 'Inactive departments are hidden from the teacher form.',
        }

    def clean_name(self):
        name = self.cleaned_data.get('name', '').strip()
        name = ' '.join(name.split())
        if len(name) < 2:
            raise forms.ValidationError("Department name must be at least 2 characters.")
        return name

    def clean_code(self):
        """Optional manual override — uppercased and sanitised."""
        code = self.cleaned_data.get('code', '').strip().upper()
        if code:
            code = ''.join(c for c in code if c.isalnum())
        return code


# ============================================================================
# LEVEL FORM
# ============================================================================
class LevelForm(forms.ModelForm):
    """Form for creating/editing a school level (JSS1, SSS2, etc.)."""

    class Meta:
        model = Level
        fields = ['name', 'level_type', 'order', 'description']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'e.g. JSS1',
                'autocomplete': 'off',
                'maxlength': 50,
            }),
            'level_type': forms.Select(attrs={'class': 'form-input'}),
            'order': forms.NumberInput(attrs={
                'class': 'form-input',
                'min': 0,
                'placeholder': 'e.g. 1',
            }),
            'description': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'Optional note about this level',
                'autocomplete': 'off',
            }),
        }
        help_texts = {
            'order': 'Controls display order — lower numbers appear first.',
        }

    def clean_name(self):
        name = self.cleaned_data.get('name', '').strip()
        if not name:
            raise forms.ValidationError("Level name is required.")
        return name


# ============================================================================
# BULK IMPORT FORM
# ============================================================================
class BulkImportForm(forms.Form):
    """Form for uploading a CSV of staff members."""

    csv_file = forms.FileField(
        widget=forms.FileInput(attrs={
            'class': 'form-input',
            'accept': '.csv,text/csv',
        }),
        validators=[FileExtensionValidator(allowed_extensions=['csv'])],
        help_text=(
            "Required column: full_name. "
            "Optional: designation, role, department, levels, "
            "email, phone, valid_thru, blood_group, emergency_contact_phone."
        ),
    )

    def clean_csv_file(self):
        f = self.cleaned_data.get('csv_file')
        if f and hasattr(f, 'size') and f.size > 5 * 1024 * 1024:
            raise forms.ValidationError("CSV file must be smaller than 5 MB.")
        return f


# ============================================================================
# ID CARD TEMPLATE FORM
# ============================================================================
class IDCardTemplateForm(forms.ModelForm):
    """Form for editing card template options."""

    class Meta:
        model = IDCardTemplate
        fields = [
            'name', 'show_hologram', 'show_gold_bar',
            'show_barcode', 'card_footer_text', 'card_footer_subtext',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-input'}),
            'card_footer_text': forms.TextInput(attrs={'class': 'form-input'}),
            'card_footer_subtext': forms.TextInput(attrs={'class': 'form-input'}),
            'show_hologram': forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
            'show_gold_bar': forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
            'show_barcode':  forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
        }
        help_texts = {
            'card_footer_text': 'Primary footer line on the card.',
            'card_footer_subtext': 'Secondary line shown in smaller text.',
        }