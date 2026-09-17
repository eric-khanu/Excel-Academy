from django.contrib import admin
from .models import School, Teacher, IDCardTemplate, Department, Level


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
    list_display = [
        'full_name', 'employee_id', 'role',
        'designation', 'department', 'status',
    ]
    list_filter = ['status', 'role', 'department', 'levels', 'blood_group']
    search_fields = ['full_name', 'employee_id', 'email', 'phone']
    filter_horizontal = ['levels']
    autocomplete_fields = ['department']
    readonly_fields = ['employee_id', 'created_at', 'updated_at']
    date_hierarchy = 'created_at'

    fieldsets = (
        ('Personal Information', {
            'fields': ('full_name', 'designation', 'photo', 'role')
        }),
        ('Employment Details', {
            'fields': ('employee_id', 'department', 'levels', 'valid_thru')
        }),
        ('Contact', {
            'fields': ('email', 'phone')
        }),
        ('Back of Card', {
            'fields': ('blood_group', 'emergency_contact_phone'),
            'description': 'These fields appear on the reverse of the ID card.',
        }),
        ('Card Settings', {
            'fields': ('status', 'template')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )