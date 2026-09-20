from django.contrib import admin
from django.utils.html import format_html
from .models import Student


def _print_state(count):
    count = count or 0
    if count == 0:
        return '#fef3c7', '#92400e', 'Not Printed'
    if count == 1:
        return '#d1fae5', '#065f46', 'Printed'
    return '#dbeafe', '#1e40af', f'Reprinted ×{count}'


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = [
        'full_name', 'admission_number', 'level', 'gender',
        'status', 'print_status_badge',
    ]
    list_filter  = ['status', 'level', 'department', 'gender', 'print_count']
    search_fields = ['full_name', 'admission_number', 'email', 'phone']
    readonly_fields = ['admission_number', 'created_at', 'updated_at']

    @admin.display(description='Print Status', ordering='print_count')
    def print_status_badge(self, obj):
        bg, fg, short = _print_state(obj.print_count)
        return format_html(
            '<span style="display:inline-block;padding:2px 8px;'
            'border-radius:10px;background:{};color:{};'
            'font-size:11px;font-weight:600;white-space:nowrap;">{}</span>',
            bg, fg, short,
        )