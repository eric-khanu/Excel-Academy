from django import forms
from django.core.validators import FileExtensionValidator
from django.utils import timezone
from .models import Teacher, School, IDCardTemplate, Department, Level


# ============================================================================
# SHARED VALIDATORS
# ============================================================================
PHONE_ALLOWED_CHARS = set('+0123456789 -()')
HEX_DIGITS = set('0123456789ABCDEFabcdef')
MAX_PHOTO_MB = 5
MAX_LOGO_MB = 2
MAX_CSV_MB = 5


def validate_phone(value, field_label="Phone"):
    """Strip and validate a phone field's characters."""
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
    Accepts 6-digit hex with optional '#' and 3-digit shorthand (#ABC).
    """
    value = (value or '').strip()
    if not value:
        return value
    if not value.startswith('#'):
        value = '#' + value

    body = value[1:]

    if len(body) == 3 and all(c in HEX_DIGITS for c in body):
        body = ''.join(c * 2 for c in body)
    elif len(body) == 6 and all(c in HEX_DIGITS for c in body):
        pass
    else:
        raise forms.ValidationError(
            f"{field_label} must be a valid 3- or 6-digit hex code, "
            f"e.g. #8B2020."
        )

    return '#' + body.upper()


# ============================================================================
# MIXIN: shared date sanity checks
# ============================================================================
class IssuedExpiryMixin:
    """Adds issue/expiry cross-field validation. Reused in TeacherForm."""

    def clean_issue_expiry(self):
        cleaned = self.cleaned_data
        issue_date = cleaned.get('issue_date')
        expiry_date = cleaned.get('expiry_date')
        valid_thru = cleaned.get('valid_thru')

        if issue_date and expiry_date and expiry_date < issue_date:
            self.add_error(
                'expiry_date',
                "Expiry date must be after the issue date.",
            )

        if issue_date and valid_thru and valid_thru < issue_date:
            self.add_error(
                'valid_thru',
                "'Valid thru' must be after the issue date.",
            )


# ============================================================================
# TEACHER FORM
# ============================================================================
class TeacherForm(IssuedExpiryMixin, forms.ModelForm):
    """Form for creating/editing a staff member's ID card record."""

    class Meta:
        model = Teacher
        fields = [
            'full_name', 'designation', 'photo', 'role',
            'department', 'levels', 'valid_thru',
            'email', 'phone', 'emergency_contact_phone',
            'issue_date', 'expiry_date',
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
            'emergency_contact_phone': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': '+234 800 000 0000',
                'autocomplete': 'off',
                'maxlength': 30,
            }),
            'issue_date': forms.DateInput(attrs={
                'class': 'form-input',
                'type': 'date',
            }),
            'expiry_date': forms.DateInput(attrs={
                'class': 'form-input',
                'type': 'date',
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
            'emergency_contact_phone': 'Optional — shown on the back of the card.',
            'issue_date': 'Date this card was issued. Shown on the back.',
            'expiry_date': 'Date this card expires. Shown on the back.',
        }
        labels = {
            'full_name': 'Full Name',
            'valid_thru': 'Valid Thru',
            'emergency_contact_phone': 'Emergency Contact Phone',
            'issue_date': 'Issue Date',
            'expiry_date': 'Expiry Date',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['department'].queryset = (
            Department.objects.filter(is_active=True).order_by('name')
        )
        self.fields['department'].empty_label = '— Select Department —'

        self.fields['levels'].queryset = (
            Level.objects.all().order_by('order', 'name')
        )

        optional_fields = [
            'template', 'photo', 'levels', 'department',
            'emergency_contact_phone', 'issue_date', 'expiry_date',
            'valid_thru',
        ]
        for name in optional_fields:
            self.fields[name].required = False

        self.fields['template'].empty_label = '— Default Template —'

    def clean_full_name(self):
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
        photo = self.cleaned_data.get('photo')
        if photo and hasattr(photo, 'size') and photo.size > MAX_PHOTO_MB * 1024 * 1024:
            raise forms.ValidationError(f"Photo must be smaller than {MAX_PHOTO_MB} MB.")
        return photo

    def clean(self):
        cleaned = super().clean()

        role = cleaned.get('role')
        department = cleaned.get('department')
        levels = cleaned.get('levels')

        if role == 'TEACHER' and not department:
            self.add_error(
                'department',
                "Teachers should be assigned to a department."
            )

        if role and role not in ('TEACHER', 'COUNSELOR') and levels:
            self.add_error(
                'levels',
                "Levels are usually only assigned to Teachers or Counselors."
            )

        self.clean_issue_expiry()

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
            'default_authorized_use',
            'default_terms',
            'default_security',
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
            'established': forms.NumberInput(attrs={
                'class': 'form-input',
                'placeholder': 'e.g. 1995',
                'min': 1800,
                'max': 2100,
                'step': 1,
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
                'accept': 'image/png, image/jpeg, image/jpg',
            }),
            'primary_color':   forms.TextInput(attrs={'type': 'color', 'class': 'color-input'}),
            'secondary_color': forms.TextInput(attrs={'type': 'color', 'class': 'color-input'}),
            'accent_color':    forms.TextInput(attrs={'type': 'color', 'class': 'color-input'}),
            'text_color':      forms.TextInput(attrs={'type': 'color', 'class': 'color-input'}),
            'default_authorized_use': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'Authorized for official school use only.',
                'maxlength': 200,
            }),
            'default_terms': forms.Textarea(attrs={
                'class': 'form-input',
                'rows': 4,
                'placeholder': 'Terms of use printed on the back of every card.',
                'maxlength': 2000,
            }),
            'default_security': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'If found, please return to the school office.',
                'maxlength': 200,
            }),
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
            'default_authorized_use': 'Shown on the back of every ID card.',
            'default_terms': 'Shown on the back of every ID card.',
            'default_security': 'Optional security notice on every card.',
        }

    def clean_name(self):
        name = self.cleaned_data.get('name', '').strip()
        name = ' '.join(name.split())
        if len(name) < 2:
            raise forms.ValidationError("School name must be at least 2 characters.")
        return name

    def clean_short_name(self):
        value = self.cleaned_data.get('short_name', '').strip().upper()
        cleaned = ''.join(c for c in value if c.isalnum() or c == '-')
        if len(cleaned) < 2:
            raise forms.ValidationError("Short name must be at least 2 characters.")
        if len(cleaned) > 10:
            raise forms.ValidationError("Short name must be 10 characters or fewer.")
        return cleaned

    def clean_established(self):
        year = self.cleaned_data.get('established')
        if year is None:
            return year
        current_year = timezone.now().year
        if not (1800 <= year <= current_year + 1):
            raise forms.ValidationError(
                f"Established year must be between 1800 and {current_year + 1}."
            )
        return year

    def clean_logo(self):
        logo = self.cleaned_data.get('logo')
        if not logo:
            return logo

        if hasattr(logo, 'size') and logo.size > MAX_LOGO_MB * 1024 * 1024:
            raise forms.ValidationError(f"Logo must be smaller than {MAX_LOGO_MB} MB.")

        name = getattr(logo, 'name', '') or ''
        if name.lower().endswith('.svg'):
            raise forms.ValidationError(
                "SVG logos are not accepted for security reasons. "
                "Please upload a PNG or JPEG."
            )

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

    def clean_default_authorized_use(self):
        return (self.cleaned_data.get('default_authorized_use') or '').strip()

    def clean_default_terms(self):
        return (self.cleaned_data.get('default_terms') or '').strip()

    def clean_default_security(self):
        return (self.cleaned_data.get('default_security') or '').strip()


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
        code = self.cleaned_data.get('code', '').strip().upper()
        if code:
            code = ''.join(c for c in code if c.isalnum())
            if not code:
                raise forms.ValidationError(
                    "Department code must contain at least one letter or digit."
                )
            if len(code) > 10:
                raise forms.ValidationError(
                    "Department code must be 10 characters or fewer."
                )
            if self.instance and self.instance.pk and self.instance.code != code:
                raise forms.ValidationError(
                    "Department code cannot be changed after creation."
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
        name = ' '.join(name.split())
        if not name:
            raise forms.ValidationError("Level name is required.")
        return name

    def clean_order(self):
        order = self.cleaned_data.get('order')
        if order is None:
            return 0
        if order < 0:
            raise forms.ValidationError("Order cannot be negative.")
        return order


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
            "email, phone, valid_thru, emergency_contact_phone, "
            "issue_date, expiry_date."
        ),
    )

    def clean_csv_file(self):
        f = self.cleaned_data.get('csv_file')
        if not f:
            return f

        if hasattr(f, 'size') and f.size > MAX_CSV_MB * 1024 * 1024:
            raise forms.ValidationError(
                f"CSV file must be smaller than {MAX_CSV_MB} MB."
            )

        try:
            head = f.read(512)
            f.seek(0)
        except Exception:
            return f

        if isinstance(head, bytes):
            if b'\x00' in head:
                raise forms.ValidationError(
                    "This file looks binary, not a CSV. "
                    "Please export your staff list as CSV."
                )
            try:
                head = head.decode('utf-8-sig', errors='ignore')
            except Exception:
                head = ''

        first_line = next(
            (line for line in head.splitlines() if line.strip()), ''
        )
        if not first_line:
            raise forms.ValidationError("The uploaded CSV appears to be empty.")
        if ',' not in first_line and '\t' not in first_line:
            raise forms.ValidationError(
                "This file doesn't look like a CSV — no commas or tabs found "
                "in the first line. Make sure you exported it as CSV."
            )

        header = first_line.split(',') if ',' in first_line else first_line.split('\t')
        header = [h.strip().lower().lstrip('\ufeff') for h in header]
        if 'full_name' not in header:
            raise forms.ValidationError(
                "CSV must contain a 'full_name' column in the first row."
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
            'name',
            'show_hologram', 'show_gold_bar', 'show_barcode',
            'show_terms', 'show_issue_date', 'show_expiry_date',
            'show_authorized', 'show_security',
            'card_footer_text', 'card_footer_subtext',
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
            'show_hologram':    forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
            'show_gold_bar':    forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
            'show_barcode':     forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
            'show_terms':       forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
            'show_issue_date':  forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
            'show_expiry_date': forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
            'show_authorized':  forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
            'show_security':    forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
        }
        help_texts = {
            'card_footer_text': 'Primary footer line on the card.',
            'card_footer_subtext': 'Secondary line shown in smaller text.',
        }

    def clean_name(self):
        name = self.cleaned_data.get('name', '').strip()
        name = ' '.join(name.split())
        if len(name) < 2:
            raise forms.ValidationError("Template name must be at least 2 characters.")
        return name


# ============================================================================
# PRINT TRACKING FORMS
# ============================================================================
class PrintResetForm(forms.Form):
    """Confirmation form for resetting print tracking."""

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
    """Filter form for the print-all page."""

    PRINT_SCOPE_CHOICES = [
        ('all',       'All active staff'),
        ('unprinted', 'Only unprinted cards'),
        ('printed',   'Only printed cards (reprints)'),
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
        self.fields['scope'].label = 'Include'
        self.fields['track'].label = 'Update print tracking'