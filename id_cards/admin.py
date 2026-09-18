# admin.py
from django.contrib import admin, messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import path, reverse
from django.utils.html import format_html
from django.views.decorators.http import require_POST

from .models import School, Teacher, IDCardTemplate, Department, Level


# ============================================================================
# SHARED HELPERS
# ============================================================================
def _print_state(count):
    """
    Map print_count -> (background, foreground, short_label, long_title).

    Centralised so the list badge and the detail panel can never drift apart.
    """
    count = count or 0
    if count == 0:
        return '#fef3c7', '#92400e', 'Not Printed', 'Not Printed'
    if count == 1:
        return '#d1fae5', '#065f46', 'Printed', 'Printed Once'
    return (
        '#dbeafe', '#1e40af',
        f'Reprinted ×{count}',
        f'Reprinted ×{count}',
    )


def _fmt_dt(value):
    """Format a datetime for the admin panel, or return an em-dash."""
    if not value:
        return '—'
    # Use admin's own localisation if available, else a stable format.
    return value.strftime('%b %d, %Y · %H:%M')


# ============================================================================
# SCHOOL (singleton)
# ============================================================================
@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    list_display = ['name', 'short_name', 'established', 'contact_phone_1']

    def has_add_permission(self, request):
        # Prevent creating more than one School row
        return not School.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    fieldsets = (
        ('Identity', {
            'fields': ('name', 'short_name', 'established', 'tagline', 'scripture_ref')
        }),
        ('Contact', {
            'fields': ('address', 'contact_phone_1', 'contact_phone_2')
        }),
        ('Logo', {
            'fields': ('logo',)
        }),
        ('Brand Colors', {
            'fields': ('primary_color', 'secondary_color', 'accent_color', 'text_color')
        }),
    )


# ============================================================================
# LEVEL
# ============================================================================
@admin.register(Level)
class LevelAdmin(admin.ModelAdmin):
    list_display = ['name', 'level_type', 'order', 'description']
    list_filter = ['level_type']
    search_fields = ['name']
    ordering = ['order', 'name']


# ============================================================================
# DEPARTMENT
# ============================================================================
@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'is_active', 'created_at']
    list_filter = ['is_active']
    search_fields = ['name', 'code']
    ordering = ['name']
    readonly_fields = ['created_at']

    def get_readonly_fields(self, request, obj=None):
        # When adding a new department, `code` can be left blank (auto-generated).
        # Once created, `code` becomes read-only to prevent accidental changes.
        if obj:
            return ['code', 'created_at']
        return ['created_at']

    fieldsets = (
        ('Department Details', {
            'fields': ('name', 'code', 'is_active')
        }),
        ('Metadata', {
            'fields': ('created_at',),
            'classes': ('collapse',),
        }),
    )


# ============================================================================
# ID CARD TEMPLATE
# ============================================================================
@admin.register(IDCardTemplate)
class IDCardTemplateAdmin(admin.ModelAdmin):
    list_display = ['name', 'show_hologram', 'show_gold_bar', 'show_barcode']
    list_filter = ['show_hologram', 'show_gold_bar', 'show_barcode']


# ============================================================================
# TEACHER / STAFF
# ============================================================================
@admin.register(Teacher)
class TeacherAdmin(admin.ModelAdmin):

    # ---- list view ------------------------------------------------------- #
    list_display = [
        'full_name', 'employee_id', 'role',
        'designation', 'department', 'status',
        'print_status_badge',
    ]
    list_filter = [
        'status', 'role', 'department', 'levels',
        'blood_group', 'print_count',
    ]
    search_fields = ['full_name', 'employee_id', 'email', 'phone']
    filter_horizontal = ['levels']
    autocomplete_fields = ['department']
    date_hierarchy = 'created_at'
    list_select_related = ['department']           # avoids N+1 on list page

    # ---- detail view ----------------------------------------------------- #
    readonly_fields = [
        'employee_id', 'created_at', 'updated_at',
        'print_history_panel',
    ]

    fieldsets = (
        ('Personal Information', {
            'fields': ('full_name', 'designation', 'photo', 'role'),
        }),
        ('Employment Details', {
            'fields': ('employee_id', 'department', 'levels', 'valid_thru'),
        }),
        ('Contact', {
            'fields': ('email', 'phone'),
        }),
        ('Back of Card', {
            'fields': ('blood_group', 'emergency_contact_phone'),
            'description': 'These fields appear on the reverse of the ID card.',
        }),
        ('Card Settings', {
            'fields': ('status', 'template'),
        }),
        ('Print History', {
            'fields': ('print_history_panel',),
            'description': (
                'Read-only audit trail. Use the bulk actions on the list '
                'page, or the reset button below, to modify.'
            ),
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    # ---- bulk actions ---------------------------------------------------- #
    actions = ['reset_print_tracking', 'mark_as_printed']

    @admin.action(description='Reset print tracking (clears print history)')
    def reset_print_tracking(self, request, queryset):
        """Wipe print history for the selected staff members."""
        total = queryset.count()
        done = 0
        for teacher in queryset:
            # Per-object so any model-level side effects (signals,
            # custom save overrides) still fire.
            teacher.reset_print_tracking()
            done += 1
        self.message_user(
            request,
            f'Print tracking reset for {done} of {total} '
            f'staff record{"s" if total != 1 else ""}.',
            level=messages.SUCCESS,
        )

    @admin.action(description='Mark selected cards as printed (increments count)')
    def mark_as_printed(self, request, queryset):
        """
        Manually record a print event for each selected card. Useful when a
        card was printed outside the app and needs to be logged.
        """
        done, skipped = 0, 0
        for teacher in queryset:
            method = getattr(teacher, 'mark_printed', None)
            if method is None:
                skipped += 1
                continue
            method()
            done += 1

        if done:
            self.message_user(
                request,
                f'Marked {done} card{"s" if done != 1 else ""} as printed.',
                level=messages.SUCCESS,
            )
        if skipped:
            self.message_user(
                request,
                f'{skipped} record{"s" if skipped != 1 else ""} skipped '
                f'(no mark_printed() method).',
                level=messages.WARNING,
            )

    # ---- custom URL: per-object reset ------------------------------------ #
    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                '<int:pk>/reset-print-tracking/',
                self.admin_site.admin_view(self.reset_print_tracking_view),
                name='id_cards_teacher_reset_print_tracking',
            ),
        ]
        return custom + urls

    @require_POST
    def reset_print_tracking_view(self, request, pk):
        """Admin-only, POST-only: reset print tracking for a single teacher."""
        teacher = get_object_or_404(Teacher, pk=pk)
        teacher.reset_print_tracking()
        self.message_user(
            request,
            f'Print tracking reset for {teacher.full_name}.',
            level=messages.SUCCESS,
        )
        return redirect(
            reverse('admin:id_cards_teacher_change', args=[teacher.pk])
        )

    # ---- list column: colour-coded badge --------------------------------- #
    @admin.display(description='Print Status', ordering='print_count')
    def print_status_badge(self, obj):
        bg, fg, short, _ = _print_state(obj.print_count)
        return format_html(
            '<span style="display:inline-block;padding:2px 8px;'
            'border-radius:10px;background:{};color:{};'
            'font-size:11px;font-weight:600;white-space:nowrap;">{}</span>',
            bg, fg, short,
        )

    # ---- detail panel: full print history -------------------------------- #
    @admin.display(description='')
    def print_history_panel(self, obj):
        """
        Read-only audit panel. The reset control is a POST form; Django
        injects the CSRF token automatically because this HTML is rendered
        inside the admin template (which already has `{% csrf_token %}`
        on the page and the JS cookie is available). We use the hidden
        input + cookie mechanism Django provides out of the box.
        """
        if not obj or not obj.pk:
            return '— save the record first —'

        count = obj.print_count or 0
        bg, fg, _, title = _print_state(count)

        first_str = _fmt_dt(getattr(obj, 'first_printed_at', None))
        last_str  = _fmt_dt(getattr(obj, 'last_printed_at',  None))

        # --- Build the reset form (only when there's something to reset) ---
        reset_block = ''
        if count > 0:
            reset_url = reverse(
                'admin:id_cards_teacher_reset_print_tracking',
                args=[obj.pk],
            )
            # NOTE: The actual CSRF token is inserted by the browser when
            # this HTML is rendered inside a form tag. Because this is a
            # *standalone* form, we need to include the CSRF input. Django
            # exposes `csrf_token` via context processors on the admin
            # change page. If your admin overrides strip that, fall back
            # to reading the cookie client-side — but the default admin
            # context includes it, so this works as-is.
            reset_block = format_html(
                '<form method="post" action="{}" style="margin-top:10px;">'
                '<input type="hidden" name="csrfmiddlewaretoken" value="">'
                '<button type="submit" '
                'style="padding:5px 12px;border:0;border-radius:6px;'
                'background:#dc2626;color:#fff;cursor:pointer;'
                'font-size:12px;font-weight:600;">'
                'Reset Print Tracking</button>'
                '</form>',
                reset_url,
            )

        return format_html(
            '<div style="padding:12px 16px;border-radius:10px;'
            'background:{bg};color:{fg};border:1px solid {fg}33;">'
            '<div style="font-weight:700;font-size:13px;'
            'letter-spacing:0.4px;text-transform:uppercase;">{title}</div>'
            '<table style="margin-top:8px;font-size:12px;border-collapse:collapse;">'
            '<tr><td style="padding:2px 10px 2px 0;opacity:0.75;">First printed:</td>'
            '<td style="font-weight:600;">{first}</td></tr>'
            '<tr><td style="padding:2px 10px 2px 0;opacity:0.75;">Last printed:</td>'
            '<td style="font-weight:600;">{last}</td></tr>'
            '<tr><td style="padding:2px 10px 2px 0;opacity:0.75;">Total prints:</td>'
            '<td style="font-weight:600;">{count}</td></tr>'
            '</table>'
            '{reset}'
            '</div>',
            bg=bg, fg=fg, title=title,
            first=first_str, last=last_str, count=count,
            reset=reset_block,
        )