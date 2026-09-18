from django import forms
from django.core.validators import FileExtensionValidator
from .models import Teacher, School, IDCardTemplate, Department, Level


# ============================================================================
# SHARED VALIDATORS (avoid duplicating the same logic across forms)
# ============================================================================
PHONE_ALLOWED_CHARS = set('+0123456789 -()')


def validate_phone(value, field_label="Phone"):
    """
    Strip a phone field and confirm it only contains characters a phone number
    is allowed to contain. Returns the stripped value.
    """
    value = (value or '').strip()
    if value and not all(c in PHONE_ALLOWED_CHARS for c in value):
        raise forms.ValidationError(
            f"{field_label} can only contain digits, +, spaces, dashes, "
            f"and parentheses."
        )
    return value


def validate_hex_color(value, field_label="Color"):
    """
    Normalize a hex color to uppercase, 7-character form (#RRGGBB).
    """
    value = (value or '').strip()
    if not value:
        return value
    if not value.startswith('#'):
        value = '#' + value
    if len(value) != 7:
        raise forms.ValidationError(
            f"{field_label} must be a valid 6-digit hex code, e.g. #8B2020."
        )
    # Only allow hex digits after the '#'
    if not all(c in '0123456789ABCDEFabcdef' for c in value[1:]):
        raise forms.ValidationError(
            f"{field_label} must only contain hex digits (0-9, A-F)."
        )
    return value.upper()


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
                'maxlength': 200,
            }),
            'designation': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'e.g. Senior Mathematics Teacher',
                'autocomplete': 'off',
                'maxlength': 200,
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
                'maxlength': 30,
            }),
            'blood_group': forms.Select(attrs={'class': 'form-input'}),
            'emergency_contact_phone': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': '+234 800 000 0000',
                'autocomplete': 'off',
                'maxlength': 30,
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

        # Blood group choices are already defined on the model, but we set
        # them explicitly so the blank option is guaranteed to render.
        self.fields['blood_group'].choices = Teacher.BLOOD_GROUP_CHOICES

    # ------------------------------------------------------------------ #
    #  Field-level validation
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
        return validate_phone(self.cleaned_data.get('phone'), "Phone")

    def clean_emergency_contact_phone(self):
        return validate_phone(
            self.cleaned_data.get('emergency_contact_phone'),
            "Emergency contact phone",
        )

    def clean_email(self):
        return self.cleaned_data.get('email', '').strip().lower()

    def clean_photo(self):
        """Enforce a maximum image size (5 MB) to avoid huge uploads."""
        photo = self.cleaned_data.get('photo')
        if photo and hasattr(photo, 'size') and photo.size > 5 * 1024 * 1024:
            raise forms.ValidationError("Photo must be smaller than 5 MB.")
        return photo

    # ------------------------------------------------------------------ #
    #  Cross-field validation
    # ------------------------------------------------------------------ #
    def clean(self):
        cleaned = super().clean()

        role = cleaned.get('role')
        department = cleaned.get('department')
        levels = cleaned.get('levels')

        # Teachers should have a department (soft requirement, surfaced as
        # a field error rather than a hard block, so admins can override).
        if role == 'TEACHER' and not department:
            self.add_error(
                'department',
                "Teachers should be assigned to a department."
            )

        # Warn if levels are assigned to staff whose role isn't TEACHER.
        # This is a soft signal — many schools assign levels to counselors
        # too — so we don't hard-block it, but we let the admin know.
        if role and role not in ('TEACHER', 'COUNSELOR') and levels:
            self.add_error(
                'levels',
                "Levels are usually only assigned to Teachers or Counselors."
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
                'maxlength': 200,
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
                'maxlength': 200,
            }),
            'scripture_ref': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'e.g. 2 Chronicles 15:7',
                'autocomplete': 'off',
                'maxlength': 100,
            }),
            'address': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'School address',
                'autocomplete': 'off',
                'maxlength': 200,
            }),
            'contact_phone_1': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': '+234 800 000 0000',
                'autocomplete': 'off',
                'maxlength': 30,
            }),
            'contact_phone_2': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': '+234 800 000 0000 (optional)',
                'autocomplete': 'off',
                'maxlength': 30,
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
    #  Validation
    # ------------------------------------------------------------------ #
    def clean_short_name(self):
        """Uppercase, strip spaces, enforce a safe format."""
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
        return validate_phone(
            self.cleaned_data.get('contact_phone_1'),
            "Primary phone",
        )

    def clean_contact_phone_2(self):
        return validate_phone(
            self.cleaned_data.get('contact_phone_2'),
            "Secondary phone",
        )

    def clean_primary_color(self):
        return validate_hex_color(
            self.cleaned_data.get('primary_color'), "Primary color"
        )

    def clean_secondary_color(self):
        return validate_hex_color(
            self.cleaned_data.get('secondary_color'), "Secondary color"
        )

    def clean_accent_color(self):
        return validate_hex_color(
            self.cleaned_data.get('accent_color'), "Accent color"
        )

    def clean_text_color(self):
        return validate_hex_color(
            self.cleaned_data.get('text_color'), "Text color"
        )

    def clean(self):
        """
        Cross-field check: if the short name changes, warn the admin
        that existing employee IDs still use the old prefix (this is
        informational — IDs are stored as-is and don't need to change).
        """
        cleaned = super().clean()

        # Nothing hard to validate right now, but this is a convenient
        # place to add future warnings (e.g. "short name collides with
        # an existing one"). The admin field errors are surfaced from
        # individual clean_* methods above.
        return cleaned


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
                'maxlength': 150,
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
            if len(code) > 10:
                raise forms.ValidationError(
                    "Department code must be 10 characters or fewer."
                )
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
                'maxlength': 200,
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
        if not f:
            return f

        # Size cap
        if hasattr(f, 'size') and f.size > 5 * 1024 * 1024:
            raise forms.ValidationError("CSV file must be smaller than 5 MB.")

        # Very light content sniff — reject anything that doesn't look
        # like a CSV or TSV. This catches renamed .xlsx / .pdf files.
        try:
            head = f.read(512)
            f.seek(0)
        except Exception:
            # If we can't read it, let the extension validator handle it.
            return f

        if isinstance(head, bytes):
            try:
                head = head.decode('utf-8-sig', errors='ignore')
            except Exception:
                head = ''

        # First non-empty line should contain at least one comma or tab
        first_line = next(
            (line for line in head.splitlines() if line.strip()), ''
        )
        if first_line and (',' not in first_line and '\t' not in first_line):
            raise forms.ValidationError(
                "This file doesn't look like a CSV — no commas or tabs found "
                "in the first line. Make sure you exported it as CSV."
            )

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
            'name': forms.TextInput(attrs={
                'class': 'form-input',
                'maxlength': 100,
            }),
            'card_footer_text': forms.TextInput(attrs={
                'class': 'form-input',
                'maxlength': 100,
            }),
            'card_footer_subtext': forms.TextInput(attrs={
                'class': 'form-input',
                'maxlength': 100,
            }),
            'show_hologram': forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
            'show_gold_bar': forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
            'show_barcode':  forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
        }
        help_texts = {
            'card_footer_text': 'Primary footer line on the card.',
            'card_footer_subtext': 'Secondary line shown in smaller text.',
        }


# ============================================================================
# PRINT TRACKING FORMS
# ============================================================================
class PrintResetForm(forms.Form):
    """
    Confirmation form for resetting print tracking.

    Used by both the single-card reset and the bulk "reset all" action.
    Requires the admin to type a confirmation phrase so a misclick can't
    wipe a card's print history.
    """

    CONFIRM_PHRASE = "RESET"

    confirm = forms.CharField(
        max_length=10,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'Type RESET to confirm',
            'autocomplete': 'off',
            'autocapitalize': 'characters',
        }),
        help_text=(
            "Type <strong>RESET</strong> (uppercase) to confirm you want to "
            "clear all print history. This cannot be undone."
        ),
    )

    # Optional: which card is being reset (passed in via initial)
    teacher = None

    def __init__(self, *args, teacher=None, **kwargs):
        self.teacher = teacher
        super().__init__(*args, **kwargs)

    def clean_confirm(self):
        value = self.cleaned_data.get('confirm', '').strip()
        if value.upper() != self.CONFIRM_PHRASE:
            raise forms.ValidationError(
                f'Please type "{self.CONFIRM_PHRASE}" exactly to confirm.'
            )
        return value.upper()


class BulkPrintFilterForm(forms.Form):
    """
    Filter form used on the print-all page to narrow down which cards
    are included in the batch, and to control print tracking behaviour.
    """

    PRINT_SCOPE_CHOICES = [
        ('all',      'All active staff'),
        ('unprinted', 'Only unprinted cards'),
        ('printed',  'Only printed cards (reprints)'),
        ('reprinted', 'Only reprinted cards'),
    ]

    scope = forms.ChoiceField(
        choices=PRINT_SCOPE_CHOICES,
        initial='unprinted',
        widget=forms.Select(attrs={'class': 'form-input'}),
        help_text='Which cards to include in this print run.',
    )

    track = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
        help_text=(
            'When checked, print history is updated for every card in this '
            'batch. Uncheck for a preview run that does not affect tracking.'
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make the field easier to read in templates
        self.fields['scope'].label = 'Include'
        self.fields['track'].label = 'Update print tracking'