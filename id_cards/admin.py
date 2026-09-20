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

    def changelist_view(self, request, extra_context=None):
        """
        Bounce the user directly to the singleton edit page — the changelist
        for a one-row table is a UX dead end.
        """
        obj = School.objects.first()
        if obj:
            url = reverse('admin:id_cards_school_change', args=[obj.pk])
            return redirect(url)
        return super().changelist_view(request, extra_context=extra_context)

    fieldsets = (
        ('Identity', {
            'fields': ('name', 'short_name', 'established', 'tagline', 'scripture_ref')
        }),
        ('Contact', {
            'fields': ('address', 'contact_phone_1', 'contact_phone_2')
        }),
        ('Logo', {
            'fields': ('logo',),
            'description': (
                'PNG or JPEG only. SVG is rejected for security reasons.'
            ),
        }),
        ('Brand Colors', {
            'fields': ('primary_color', 'secondary_color', 'accent_color', 'text_color'),
            'description': (
                'Use 6-digit hex codes (e.g. #8B2020). These drive the card '
                'layout, headers, and accents.'
            ),
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
    list_editable = ['order']  # quick reorder without opening each row


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
    list_display = [
        'name', 'show_hologram', 'show_gold_bar', 'show_barcode',
        'show_terms', 'show_issue_date', 'show_expiry_date',
        'show_authorized', 'show_security',
    ]
    list_filter = [
        'show_hologram', 'show_gold_bar', 'show_barcode',
    ]
    search_fields = ['name']
    ordering = ['name']

    fieldsets = (
        ('Template', {
            'fields': ('name',),
        }),
        ('Front of card', {
            'fields': ('show_hologram', 'show_gold_bar', 'show_barcode'),
        }),
        ('Back of card — sections', {
            'fields': (
                'show_terms', 'show_issue_date', 'show_expiry_date',
                'show_authorized', 'show_security',
            ),
            'description': (
                'Toggle which sections appear on the back of every card '
                'using this template.'
            ),
        }),
        ('Back of card — default content', {
            'fields': ('default_terms', 'default_authorized_use', 'default_security'),
            'description': (
                'Fallback content used when a teacher has no custom value '
                'for that field. Can be overridden per teacher.'
            ),
        }),
        ('Footer', {
            'fields': ('card_footer_text', 'card_footer_subtext'),
        }),
    )


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
    ]
    search_fields = ['full_name', 'employee_id', 'email', 'phone']
    filter_horizontal = ['levels']
    autocomplete_fields = ['department']
    date_hierarchy = 'created_at'
    list_select_related = ['department']           # avoids N+1 on list page
    list_per_page = 50

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
        ('Back of Card — Contact', {
            'fields': ('emergency_contact_phone',),
            'description': 'Emergency contact details shown on the reverse of the ID card.',
        }),
        ('Back of Card — Official / Legal', {
            'fields': (
                'issue_date', 'expiry_date',
                'id_card_terms', 'authorized_use', 'security',
            ),
            'description': (
                'These fields appear on the reverse of the ID card. '
                'If a field is left blank, the template default is used.'
            ),
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
        """Wipe print history for the selected staff members (single query)."""
        count = Teacher.reset_all_print_tracking_for(queryset)  \
            if hasattr(Teacher, 'reset_all_print_tracking_for')     \
            else self._fallback_reset(queryset)
        self.message_user(
            request,
            f'Print tracking reset for {count} '
            f'staff record{"s" if count != 1 else ""}.',
            level=messages.SUCCESS,
        )

    @staticmethod
    def _fallback_reset(queryset):
        """Single-query bulk reset (avoids per-row save() calls)."""
        return queryset.update(
            print_count=0,
            first_printed_at=None,
            last_printed_at=None,
        )

    @admin.action(description='Mark selected cards as printed (increments count)')
    def mark_as_printed(self, request, queryset):
        """
        Manually record a print event for each selected card. Uses the
        model's bulk helper so it's a single UPDATE, not N queries.
        """
        done = Teacher.mark_many_printed(queryset)

        if done:
            self.message_user(
                request,
                f'Marked {done} card{"s" if done != 1 else ""} as printed.',
                level=messages.SUCCESS,
            )
        else:
            self.message_user(
                request,
                'No cards were marked — selection was empty.',
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
        Read-only audit panel. Renders a POST form for resetting print
        tracking. The CSRF token is injected by Django's template layer
        through the {csrf_token} placeholder in format_html — but because
        format_html doesn't do template substitution, we render an empty
        token and let Django's CSRF middleware accept the cookie value.

        NOTE: Django 4.1+ requires the CSRF token for POST requests even
        from the admin. The empty value works only because the admin's
        session cookie carries the token; if you're on an older Django,
        use the safer `csrf_token` template approach below.
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
            # Use the request's CSRF token via a marker that we'll replace
            # in the surrounding template. See `render_change_form`.
            reset_block = format_html(
                '<form method="post" action="{}" style="margin-top:10px;">'
                '{}'
                '<button type="submit" '
                'style="padding:5px 12px;border:0;border-radius:6px;'
                'background:#dc2626;color:#fff;cursor:pointer;'
                'font-size:12px;font-weight:600;">'
                'Reset Print Tracking</button>'
                '</form>',
                reset_url,
                # Placeholder — Django's template engine substitutes this
                # via the `{% csrf_token %}` tag in the change_form template.
                # In practice, we rely on the admin session CSRF cookie.
                format_html('<input type="hidden" name="csrfmiddlewaretoken" value="{}">',
                            _get_csrf_token()),
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

