from django.db import models
from django.core.validators import FileExtensionValidator
from django.utils import timezone
from django.utils.text import slugify
import re


# ============================================================================
# SCHOOL BRANDING (singleton — only one row ever exists)
# ============================================================================
class School(models.Model):
    """School-level branding — logo, name, colors, contact info."""

    # --- Identity ---
    name = models.CharField(
        max_length=200,
        default="Excel Junior Secondary School",
    )
    short_name = models.CharField(
        max_length=50,
        default="EJSS",
        help_text="Used as the ID prefix, e.g. EJSS-2026-001",
    )
    tagline = models.CharField(
        max_length=200,
        blank=True,
        default="Be strong and courageous, your works shall be rewarded",
    )
    scripture_ref = models.CharField(
        max_length=100, blank=True, default="2 Chronicles 15:7"
    )
    address = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text="School address, shown on the back of the card.",
    )
    established = models.CharField(max_length=20, blank=True, default="1995")

    # --- Logo ---
    logo = models.ImageField(
        upload_to='logos/',
        blank=True, null=True,
        validators=[FileExtensionValidator(['png', 'jpg', 'jpeg', 'svg'])],
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
    primary_color = models.CharField(max_length=7, default="#8B2020")
    secondary_color = models.CharField(max_length=7, default="#C87A2C")
    accent_color = models.CharField(max_length=7, default="#FBF6EC")
    text_color = models.CharField(max_length=7, default="#2A1810")

    class Meta:
        verbose_name = "School Branding"
        verbose_name_plural = "School Branding"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)


# ============================================================================
# LEVELS (JSS1–SSS3)
# ============================================================================
class Level(models.Model):
    LEVEL_TYPE_CHOICES = [
        ('JSS', 'Junior Secondary School'),
        ('SSS', 'Senior Secondary School'),
        ('PRIMARY', 'Primary'),
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
        max_length=10,
        blank=True,
        unique=True,
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
               ("Basic Science" → BS, "Computer Science Dept" → CSD)
            2. Single word ≥ 3 chars → first 3 letters
               ("Science" → SCI, "Mathematics" → MAT)
            3. Single word < 3 chars → as-is uppercase
               ("Art" → ART, "PE" → PE)
        Collisions get a numeric suffix: SCI, SCI2, SCI3, …
        """
        clean = re.sub(r'[^A-Za-z\s]', '', self.name).strip()
        clean = re.sub(r'\s+', ' ', clean)
        words = clean.split()

        if not words:
            base = "DEP"
        elif len(words) >= 2:
            base = ''.join(w[0] for w in words[:4]).upper()
        else:
            word = words[0].upper()
            base = word[:3] if len(word) >= 3 else word

        qs = Department.objects.exclude(pk=self.pk) if self.pk else Department.objects.all()

        code = base
        suffix = 1
        while qs.filter(code=code).exists():
            suffix += 1
            code = f"{base[:8]}{suffix}"[:10]
        return code

    def save(self, *args, **kwargs):
        if self.code:
            self.code = self.code.upper().strip()
            qs = Department.objects.exclude(pk=self.pk) if self.pk else Department.objects.all()
            if qs.filter(code=self.code).exists():
                base = self.code
                suffix = 1
                while qs.filter(code=self.code).exists():
                    suffix += 1
                    self.code = f"{base[:8]}{suffix}"[:10]
        else:
            self.code = self._generate_code()
        super().save(*args, **kwargs)


# ============================================================================
# ID CARD TEMPLATE
# ============================================================================
class IDCardTemplate(models.Model):
    name = models.CharField(max_length=100, default="Default Faculty Card")
    show_hologram = models.BooleanField(default=True)
    show_gold_bar = models.BooleanField(default=True)
    show_barcode = models.BooleanField(default=False)
    card_footer_text = models.CharField(
        max_length=100, default="STAFF IDENTIFICATION"
    )
    card_footer_subtext = models.CharField(
        max_length=100, default="(SEE REVERSE FOR DETAILS)"
    )

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

    BLOOD_GROUP_CHOICES = [
        ('', '— Select Blood Group —'),   # blank default so it stays optional
        ('O+',  'O+'),
        ('O-',  'O−'),
        ('A+',  'A+'),
        ('A-',  'A−'),
        ('B+',  'B+'),
        ('B-',  'B−'),
        ('AB+', 'AB+'),
        ('AB-', 'AB−'),
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
        validators=[FileExtensionValidator(['png', 'jpg', 'jpeg'])],
    )

    # --- Role ---------------------------------------------------------------
    role = models.CharField(
        max_length=30,
        choices=ROLE_CHOICES,
        default='TEACHER',
        help_text="Staff role",
    )

    # --- Employment ---------------------------------------------------------
    employee_id = models.CharField(
        max_length=50,
        unique=True,
        blank=True,
        editable=False,
        help_text="Auto-generated from school short name and year",
    )
    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True, blank=True,
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

    # --- Back-of-card info --------------------------------------------------
    blood_group = models.CharField(
        max_length=3,
        choices=BLOOD_GROUP_CHOICES,
        blank=True,
        default='',
        help_text="Shown on the back of the card.",
    )
    emergency_contact_phone = models.CharField(
        max_length=30, blank=True,
        help_text="Phone number for emergency contact.",
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

    def __str__(self):
        return f"{self.full_name} ({self.employee_id})"

    def _generate_employee_id(self):
        """
        Format:  <SCHOOL_SHORT>-<YEAR>-<NNN>
        Example: EJSS-2026-001, EJSS-2026-002

        A single sequential counter per (school, year). The sequence
        resets automatically on January 1st of each new year.
        """
        school = School.objects.first()
        short = (school.short_name if school and school.short_name else 'SCH').upper()
        short = slugify(short).upper().replace('-', '') or 'SCH'

        year = timezone.now().year
        pattern = f"{short}-{year}-"

        last = (
            Teacher.objects
            .filter(employee_id__startswith=pattern)
            .order_by('-employee_id')
            .values_list('employee_id', flat=True)
            .first()
        )

        next_num = 1
        if last:
            try:
                next_num = int(last.rsplit('-', 1)[-1]) + 1
            except (ValueError, IndexError):
                next_num = 1

        return f"{pattern}{next_num:03d}"

    def save(self, *args, **kwargs):
        if not self.employee_id:
            self.employee_id = self._generate_employee_id()
        super().save(*args, **kwargs)

    @property
    def initials(self):
        parts = self.full_name.split()
        return ''.join(p[0].upper() for p in parts[:2])[:2]

    @property
    def department_display(self):
        return self.department.name if self.department else "General"

    @property
    def levels_display(self):
        names = list(self.levels.values_list('name', flat=True))
        return ', '.join(names) if names else ''