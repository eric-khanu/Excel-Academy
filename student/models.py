from django.db import models, IntegrityError, transaction
from django.core.validators import FileExtensionValidator
from django.utils import timezone
from django.utils.text import slugify

# Reuse the branding + template models from id_cards
from id_cards.models import School, Level, Department, IDCardTemplate


class Student(models.Model):
    """Student record — every field editable."""

    GENDER_CHOICES = [
        ('M', 'Male'),
        ('F', 'Female'),
        ('O', 'Other'),
    ]

    CARD_STATUS = [
        ('active',    'Active'),
        ('inactive',  'Inactive'),
        ('graduated', 'Graduated'),
        ('expired',   'Expired'),
    ]

    # Reuse the teacher blood-group choices (identical list)
    BLOOD_GROUP_CHOICES = [
        ('',    '— Select Blood Group —'),
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
    admission_number = models.CharField(
        max_length=50, unique=True, blank=True, editable=False,
        help_text="Auto-generated from school short name and year",
    )
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES, default='M')
    date_of_birth = models.DateField(null=True, blank=True)
    photo = models.ImageField(
        upload_to='student_photos/',
        blank=True, null=True,
        validators=[FileExtensionValidator(['png', 'jpg', 'jpeg'])],
    )

    # --- Academic -----------------------------------------------------------
    level = models.ForeignKey(
        Level, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='students',
        help_text="Class/level the student is in (JSS1, SSS2, etc.)",
    )
    department = models.ForeignKey(
        Department, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='students',
        help_text="Optional: house, stream, or faculty.",
    )
    guardian_name = models.CharField(max_length=200, blank=True)
    guardian_phone = models.CharField(max_length=30, blank=True)
    valid_thru = models.DateField(null=True, blank=True)

    # --- Contact ------------------------------------------------------------
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    address = models.CharField(max_length=200, blank=True)

    # --- Back of card -------------------------------------------------------
    blood_group = models.CharField(
        max_length=3, choices=BLOOD_GROUP_CHOICES,
        blank=True, default='',
        help_text="Shown on the back of the card.",
    )
    emergency_contact_phone = models.CharField(
        max_length=30, blank=True,
        help_text="Phone number for emergency contact.",
    )

    # --- Print tracking -----------------------------------------------------
    print_count = models.PositiveIntegerField(default=0)
    first_printed_at = models.DateTimeField(null=True, blank=True)
    last_printed_at = models.DateTimeField(null=True, blank=True)

    # --- Status & template --------------------------------------------------
    status = models.CharField(max_length=20, choices=CARD_STATUS, default='active')
    template = models.ForeignKey(
        IDCardTemplate, on_delete=models.SET_NULL, null=True, blank=True
    )

    # --- Timestamps ---------------------------------------------------------
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['full_name']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['print_count']),
            models.Index(fields=['admission_number']),
            models.Index(fields=['level']),
        ]

    def __str__(self):
        return f"{self.full_name} ({self.admission_number})"

    # ------------------------------------------------------------------
    # Admission number generation
    # ------------------------------------------------------------------
    def _generate_admission_number(self):
        """
        Format:  <SCHOOL_SHORT>-STU-<YEAR>-<NNN>
        Example: EJSS-STU-2026-001
        """
        school = School.objects.first()
        short = (school.short_name if school and school.short_name else 'SCH').upper()
        short = slugify(short).upper().replace('-', '') or 'SCH'

        year = timezone.now().year
        pattern = f"{short}-STU-{year}-"

        last = (
            Student.objects
            .filter(admission_number__startswith=pattern)
            .order_by('-admission_number')
            .values_list('admission_number', flat=True)
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
        if not self.admission_number:
            self.admission_number = self._generate_admission_number()
            try:
                with transaction.atomic():
                    super().save(*args, **kwargs)
                return
            except IntegrityError:
                self.admission_number = self._generate_admission_number()
        super().save(*args, **kwargs)

    # ------------------------------------------------------------------
    # Display helpers
    # ------------------------------------------------------------------
    @property
    def initials(self):
        parts = self.full_name.split()
        return ''.join(p[0].upper() for p in parts[:2])[:2]

    @property
    def level_display(self):
        return self.level.name if self.level else "—"

    @property
    def department_display(self):
        return self.department.name if self.department else "—"

    @property
    def age(self):
        if not self.date_of_birth:
            return None
        today = timezone.now().date()
        return today.year - self.date_of_birth.year - (
            (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day)
        )

    @property
    def is_expired(self):
        if not self.valid_thru:
            return False
        return self.valid_thru < timezone.now().date()

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
        now = timezone.now()
        if self.first_printed_at is None:
            self.first_printed_at = now
        self.last_printed_at = now
        self.print_count = (self.print_count or 0) + 1
        if save:
            self.save(update_fields=[
                'print_count', 'first_printed_at', 'last_printed_at',
            ])
        return True

    @classmethod
    def mark_many_printed(cls, students):
        students = list(students)
        if not students:
            return 0
        now = timezone.now()
        ids = [s.pk for s in students if s.pk]
        if not ids:
            return 0
        cls.objects.filter(pk__in=ids, first_printed_at__isnull=True).update(
            first_printed_at=now
        )
        return cls.objects.filter(pk__in=ids).update(
            last_printed_at=now,
            print_count=models.F('print_count') + 1,
        )

    @classmethod
    def reset_all_print_tracking(cls):
        return cls.objects.update(
            print_count=0, first_printed_at=None, last_printed_at=None,
        )

    def reset_print_tracking(self, save=True):
        self.print_count = 0
        self.first_printed_at = None
        self.last_printed_at = None
        if save:
            self.save(update_fields=[
                'print_count', 'first_printed_at', 'last_printed_at',
            ])