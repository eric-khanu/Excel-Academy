from django.db import models, IntegrityError, transaction
from django.core.validators import (
    FileExtensionValidator,
    RegexValidator,
    MinValueValidator,
    MaxValueValidator,
)
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.text import slugify
from django.db.models import F, IntegerField
from django.db.models.functions import Cast, Substr, Coalesce
import re


# ============================================================================
# Shared validators
# ============================================================================
HEX_COLOR_VALIDATOR = RegexValidator(
    regex=r'^#(?:[0-9a-fA-F]{3}){1,2}$',
    message="Enter a valid hex color, e.g. #8B2020.",
)


def validate_image_size(file, limit_mb=5):
    """Reject image uploads larger than `limit_mb` megabytes."""
    if file.size > limit_mb * 1024 * 1024:
        raise ValidationError(f"Image must be under {limit_mb} MB.")


# ============================================================================
# SCHOOL BRANDING (singleton — only one row ever exists)
# ============================================================================
class School(models.Model):
    """School-level branding — logo, name, colors, contact info."""

    # --- Identity ---
    name = models.CharField(max_length=200, default="Excel Junior Secondary School")
    short_name = models.CharField(
        max_length=50, default="EJSS",
        help_text="Used as the ID prefix, e.g. EJSS-2026-001",
    )
    tagline = models.CharField(
        max_length=200, blank=True,
        default="Be strong and courageous, your works shall be rewarded",
    )
    scripture_ref = models.CharField(
        max_length=100, blank=True, default="2 Chronicles 15:7"
    )
    address = models.CharField(
        max_length=200, blank=True, default="",
        help_text="School address, shown on the back of the card.",
    )
    established = models.PositiveSmallIntegerField(
        null=True, blank=True,
        validators=[MinValueValidator(1800), MaxValueValidator(2100)],
        help_text="Year the school was established, e.g. 1995.",
    )

    # --- Logo (SVG intentionally excluded — XSS vector) ---
    logo = models.ImageField(
        upload_to='logos/',
        blank=True, null=True,
        validators=[
            FileExtensionValidator(['png', 'jpg', 'jpeg']),
            validate_image_size,
        ],
    )

    # --- Contact (shown on the back of the card) ---
    contact_phone_1 = models.CharField(
        max_length=30, blank=True,
        help_text="Primary phone shown on the back of the card.",
    )
    contact_phone_2 = models.CharField(
        max_length=30, blank=True,
        help_text="Secondary phone (optional).",
    )

    # --- Brand colors ---
    primary_color = models.CharField(
        max_length=7, default="#F58220", validators=[HEX_COLOR_VALIDATOR]
    )
    secondary_color = models.CharField(
        max_length=7, default="#6B3410", validators=[HEX_COLOR_VALIDATOR]
    )
    accent_color = models.CharField(
        max_length=7, default="#FDF6EC", validators=[HEX_COLOR_VALIDATOR]
    )
    text_color = models.CharField(
        max_length=7, default="#3A1F0A", validators=[HEX_COLOR_VALIDATOR]
    )

    # --- Back-of-card shared content (same for every teacher) ---
    default_authorized_use = models.CharField(
        max_length=200, blank=True,
        default="Authorized for official school use only.",
        help_text="Shown on the back of every ID card.",
    )
    default_terms = models.TextField(
        blank=True,
        default=(
            "This card is the property of the school and is not transferable. "
            "It must be carried at all times while on school premises and "
            "produced on demand by any authorized staff member."
        ),
        help_text="Shown on the back of every ID card.",
    )
    default_security = models.CharField(
        max_length=200, blank=True,
        default="If found, please return to the school office. Reward available.",
        help_text="Optional security notice shown on the back of every card.",
    )

    class Meta:
        verbose_name = "School Branding"
        verbose_name_plural = "School Branding"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        """
        Force singleton behaviour (pk=1) without silently overwriting
        or racing on concurrent creates.
        """
        self.pk = 1
        if not School.objects.filter(pk=1).exists():
            kwargs.setdefault('force_insert', True)
        super().save(*args, **kwargs)

    @classmethod
    def get_solo(cls):
        """Fetch-or-create the single branding row."""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


# ============================================================================
# LEVELS (JSS1–SSS3)
# ============================================================================
class Level(models.Model):
    LEVEL_TYPE_CHOICES = [
        ('JSS', 'Junior Secondary School'),
        ('SSS', 'Senior Secondary School'),
        ('PRIMARY', 'Primary'),
        ('NURSERY', 'Nursery'),
        ('DAY CARE', 'Day Care'),
        ('OTHER', 'Other'),
    ]

    name = models.CharField(max_length=50, unique=True)
    level_type = models.CharField(
        max_length=20, choices=LEVEL_TYPE_CHOICES, default='JSS'
    )
    order = models.PositiveIntegerField(
        default=0,
        help_text="Controls display order — lower numbers appear first.",
    )
    description = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ['order', 'name']
        verbose_name = "Level"
        verbose_name_plural = "Levels"

    def __str__(self):
        return self.name


# ============================================================================
# DEPARTMENTS
# ============================================================================
class Department(models.Model):
    name = models.CharField(max_length=150, unique=True)
    code = models.CharField(
        max_length=10, blank=True, unique=True,
        help_text="Auto-generated from the name (e.g. 'Science' → SCI). "
                  "Leave blank to auto-generate.",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        verbose_name = "Department"
        verbose_name_plural = "Departments"

    def __str__(self):
        return f"{self.name} ({self.code})" if self.code else self.name

    def _generate_code(self):
        """
        Rules (in order):
            1. Multi-word → first letter of each word, up to 4 letters
            2. Single word ≥ 3 chars → first 3 letters
            3. Single word < 3 chars → as-is uppercase
        Collisions get a numeric suffix: SCI, SCI2, SCI3, …
        """
        clean = re.sub(r'[^A-Za-z\s]', '', self.name).strip()
        clean = re.sub(r'\s+', ' ', clean)
        words = clean.split()

        if not words:
            base = "DEP"
        elif len(words) >= 2:
            base = ''.join(w[0] for w in words[:4]).upper() or "DEP"
        else:
            word = words[0].upper()
            base = word[:3] if len(word) >= 3 else word

        return self._resolve_collision(base)

    def _resolve_collision(self, base):
        """Given a base code, find a unique variant with a numeric suffix."""
        qs = (
            Department.objects.exclude(pk=self.pk)
            if self.pk else Department.objects.all()
        )
        code = base
        suffix = 1
        while qs.filter(code=code).exists():
            suffix += 1
            code = f"{base[:8]}{suffix}"[:10]
        return code

    def save(self, *args, **kwargs):
        """Normalise + generate code, retrying on race-condition IntegrityErrors."""
        if self.code:
            self.code = self.code.upper().strip()
        else:
            self.code = self._generate_code()

        for _ in range(5):
            try:
                with transaction.atomic():
                    return super().save(*args, **kwargs)
            except IntegrityError:
                self.code = self._resolve_collision(self.code)

        raise IntegrityError(
            f"Could not allocate a unique Department code for '{self.name}'."
        )


# ============================================================================
# ID CARD TEMPLATE
# ============================================================================
class IDCardTemplate(models.Model):
    name = models.CharField(max_length=100, default="Default Faculty Card")
    show_hologram = models.BooleanField(default=True)
    show_gold_bar = models.BooleanField(default=True)
    show_barcode = models.BooleanField(default=False)

    # --- Back-of-card visibility toggles ---
    show_terms = models.BooleanField(
        default=True,
        help_text="Show the terms of use section on the back of the card.",
    )
    show_issue_date = models.BooleanField(
        default=True,
        help_text="Show the issue date on the back of the card.",
    )
    show_expiry_date = models.BooleanField(
        default=True,
        help_text="Show the expiry date on the back of the card.",
    )
    show_authorized = models.BooleanField(
        default=True,
        help_text="Show the authorization statement on the back of the card.",
    )
    show_security = models.BooleanField(
        default=True,
        help_text="Show the security notice on the back of the card.",
    )

    card_footer_text = models.CharField(
        max_length=100, default="STAFF IDENTIFICATION"
    )
    card_footer_subtext = models.CharField(
        max_length=100, default="(SEE REVERSE FOR DETAILS)"
    )

    class Meta:
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(fields=['name'], name='uniq_template_name'),
        ]

    def __str__(self):
        return self.name


# ============================================================================
# TEACHER / STAFF
# ============================================================================
class Teacher(models.Model):
    """Staff / Teacher record — every field editable."""

    ROLE_CHOICES = [
        ('TEACHER', 'Teacher'),
        ('SECRETARY', 'Secretary'),
        ('ACCOUNTANT', 'Accountant'),
        ('LIBRARIAN', 'Librarian'),
        ('COUNSELOR', 'Counselor'),
        ('LAB_TECH', 'Lab Technician'),
        ('ICT', 'ICT / Computer Staff'),
        ('SECURITY', 'Security'),
        ('CLEANER', 'Cleaning Staff'),
        ('DRIVER', 'Driver'),
        ('ADMIN', 'Administrator'),
        ('PRINCIPAL', 'Principal'),
        ('VICE_PRINCIPAL', 'Vice Principal'),
        ('BURSAR', 'Bursar'),
        ('OTHER', 'Other'),
    ]

    CARD_STATUS = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('expired', 'Expired'),
    ]

    # --- Personal info ------------------------------------------------------
    full_name = models.CharField(max_length=200)
    designation = models.CharField(
        max_length=200,
        help_text="e.g. Senior Mathematics Teacher, Front Office Secretary",
    )
    photo = models.ImageField(
        upload_to='photos/',
        blank=True, null=True,
        validators=[
            FileExtensionValidator(['png', 'jpg', 'jpeg']),
            validate_image_size,
        ],
    )

    # --- Role ---------------------------------------------------------------
    role = models.CharField(
        max_length=30, choices=ROLE_CHOICES, default='TEACHER',
        help_text="Staff role",
    )

    # --- Employment ---------------------------------------------------------
    employee_id = models.CharField(
        max_length=50, unique=True, blank=True, editable=False,
        help_text="Auto-generated from school short name and year",
    )
    department = models.ForeignKey(
        Department, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='teachers',
    )
    levels = models.ManyToManyField(
        Level, blank=True, related_name='teachers',
        help_text="Levels this staff member handles (JSS1, SSS2, etc.)",
    )
    valid_thru = models.DateField(null=True, blank=True)

    # --- Contact ------------------------------------------------------------
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)

    # --- Back-of-card contact -----------------------------------------------
    emergency_contact_phone = models.CharField(
        max_length=30, blank=True,
        help_text="Phone number for emergency contact.",
    )

    # --- Card validity dates ------------------------------------------------
    issue_date = models.DateField(
        null=True, blank=True,
        help_text="Date the card was issued. Shown on the back.",
    )
    expiry_date = models.DateField(
        null=True, blank=True,
        help_text="Date the card expires. Shown on the back.",
    )

    # --- Print tracking -----------------------------------------------------
    print_count = models.PositiveIntegerField(
        default=0,
        help_text="How many times this card has been printed.",
    )
    first_printed_at = models.DateTimeField(
        null=True, blank=True,
        help_text="When the card was first printed.",
    )
    last_printed_at = models.DateTimeField(
        null=True, blank=True,
        help_text="When the card was last printed.",
    )

    # --- Status & template --------------------------------------------------
    status = models.CharField(
        max_length=20, choices=CARD_STATUS, default='active'
    )
    template = models.ForeignKey(
        IDCardTemplate, on_delete=models.SET_NULL, null=True, blank=True
    )

    # --- Timestamps ---------------------------------------------------------
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['full_name']
        verbose_name = "Teacher / Staff"
        verbose_name_plural = "Teachers / Staff"
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['employee_id']),
            models.Index(fields=['-last_printed_at']),
        ]

    def __str__(self):
        return f"{self.full_name} ({self.employee_id})"

    # ------------------------------------------------------------------
    # Employee ID generation
    # ------------------------------------------------------------------
    def _generate_employee_id(self):
        """
        Format:  <SCHOOL_SHORT>-<YEAR>-<NNN>
        Uses a numeric cast so the counter survives past 999.
        """
        school = School.objects.first()
        short = (school.short_name if school and school.short_name else 'SCH')
        short = re.sub(r'[^A-Za-z0-9]', '', slugify(short)).upper() or 'SCH'

        year = timezone.now().year
        prefix = f"{short}-{year}-"

        last_seq = (
            Teacher.objects
            .filter(employee_id__startswith=prefix)
            .annotate(
                seq=Cast(Substr('employee_id', len(prefix) + 1), IntegerField())
            )
            .order_by('-seq')
            .values_list('seq', flat=True)
            .first()
        )

        next_num = (last_seq or 0) + 1
        return f"{prefix}{next_num:03d}"

    def save(self, *args, **kwargs):
        """
        Assign an employee ID on first save, retrying up to 5 times if a
        concurrent insert claims the same ID first.
        """
        is_new = self._state.adding and not self.employee_id
        if not is_new:
            return super().save(*args, **kwargs)

        for _ in range(5):
            self.employee_id = self._generate_employee_id()
            try:
                with transaction.atomic():
                    return super().save(*args, **kwargs)
            except IntegrityError:
                continue

        raise IntegrityError(
            "Unable to allocate a unique employee_id after 5 attempts."
        )

    # ------------------------------------------------------------------
    # Display helpers
    # ------------------------------------------------------------------
    @property
    def initials(self):
        parts = self.full_name.split()
        return ''.join(p[0].upper() for p in parts[:2])[:2]

    @property
    def department_display(self):
        return self.department.name if self.department else "General"

    @property
    def levels_display(self):
        """
        Comma-separated level names. Cached per-instance to avoid N+1
        queries when the same instance is rendered repeatedly.
        """
        if not hasattr(self, '_levels_display_cache'):
            self._levels_display_cache = list(
                self.levels.values_list('name', flat=True)
            )
        return ', '.join(self._levels_display_cache)

    @property
    def is_expired(self):
        if self.status == 'expired':
            return True
        if not self.valid_thru:
            return False
        return self.valid_thru < timezone.now().date()

    # ------------------------------------------------------------------
    # Resolved values (fall back through School → template → empty)
    # ------------------------------------------------------------------
    @property
    def resolved_terms(self):
        """Teacher override → template override → school default → empty."""
        if self.id_card_terms:
            return self.id_card_terms
        if self.template and self.template.default_terms:
            return self.template.default_terms
        school = School.get_solo()
        return school.default_terms or ""

    @property
    def resolved_authorized_use(self):
        if self.authorized_use:
            return self.authorized_use
        if self.template and self.template.default_authorized_use:
            return self.template.default_authorized_use
        school = School.get_solo()
        return school.default_authorized_use or ""

    @property
    def resolved_security(self):
        if self.security:
            return self.security
        if self.template and self.template.default_security:
            return self.template.default_security
        school = School.get_solo()
        return school.default_security or ""

    @property
    def resolved_issue_date(self):
        return self.issue_date or self.created_at.date()

    @property
    def resolved_expiry_date(self):
        return self.expiry_date or self.valid_thru

    # ------------------------------------------------------------------
    # Print tracking
    # ------------------------------------------------------------------
    @property
    def is_printed(self):
        return self.print_count > 0

    @property
    def is_reprinted(self):
        return self.print_count > 1

    @property
    def print_status(self):
        if self.print_count == 0:
            return 'unprinted'
        if self.print_count == 1:
            return 'printed'
        return 'reprinted'

    @property
    def print_status_display(self):
        if self.print_count == 0:
            return 'Not Printed'
        if self.print_count == 1:
            return 'Printed'
        return f'Reprinted ×{self.print_count}'

    def mark_printed(self, save=True):
        """Record a print event. Uses atomic DB update when save=True."""
        now = timezone.now()

        if save:
            if not self.pk:
                raise ValueError("Cannot mark an unsaved Teacher as printed.")
            Teacher.objects.filter(pk=self.pk).update(
                print_count=F('print_count') + 1,
                first_printed_at=Coalesce('first_printed_at', now),
                last_printed_at=now,
            )
            self.refresh_from_db(
                fields=['print_count', 'first_printed_at', 'last_printed_at']
            )
            return True

        self.print_count = (self.print_count or 0) + 1
        if self.first_printed_at is None:
            self.first_printed_at = now
        self.last_printed_at = now
        return True

    @classmethod
    def mark_many_printed(cls, teachers):
        """Atomic increment for many teachers in one query."""
        ids = [t.pk for t in teachers if t.pk]
        if not ids:
            return 0

        now = timezone.now()
        return cls.objects.filter(pk__in=ids).update(
            print_count=F('print_count') + 1,
            first_printed_at=Coalesce('first_printed_at', now),
            last_printed_at=now,
        )

    @classmethod
    def reset_all_print_tracking(cls, *, confirm=False):
        """Wipe print tracking for every teacher. Requires confirm=True."""
        if not confirm:
            raise ValueError(
                "Pass confirm=True to reset ALL print tracking records."
            )
        return cls.objects.update(
            print_count=0,
            first_printed_at=None,
            last_printed_at=None,
        )

    def reset_print_tracking(self, save=True):
        self.print_count = 0
        self.first_printed_at = None
        self.last_printed_at = None
        if save:
            self.save(update_fields=[
                'print_count', 'first_printed_at', 'last_printed_at',
            ])