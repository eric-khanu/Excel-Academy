import csv
import io
import os
import re
from datetime import datetime
from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.staticfiles import finders
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q, Count, Sum, Max
from django.http import HttpResponse, StreamingHttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.http import urlencode
from django.views.decorators.http import require_http_methods, require_POST

from .models import Teacher, School, IDCardTemplate, Department, Level
from .forms import (
    TeacherForm, SchoolForm, DepartmentForm, LevelForm, BulkImportForm,
    PrintResetForm, IDCardTemplateForm,
)

# ---------------------------------------------------------------------------
# Optional PDF backend: xhtml2pdf
# ---------------------------------------------------------------------------
try:
    from xhtml2pdf import pisa
    XHTML2PDF_AVAILABLE = True
except ImportError:
    XHTML2PDF_AVAILABLE = False

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MAX_BULK_IMPORT_ROWS = 5000
MAX_BULK_PRINT_CARDS = 500          # safety cap for synchronous PDF generation
ALLOWED_PDF_REMOTE_HOSTS = frozenset({
    'fonts.googleapis.com',
    'fonts.gstatic.com',
})
PDF_FILENAME_SAFE = re.compile(r'[^A-Za-z0-9._-]+')
PRINT_FILTERS = frozenset({'', 'no', 'yes', 'once', 'reprinted'})


# ============================================================================
# HELPERS
# ============================================================================
def get_school():
    """Return the singleton School branding record."""
    return School.get_solo()


def link_callback(uri, rel):
    """
    Resolve HTML URIs to filesystem paths for xhtml2pdf.

    Remote URLs are only allowed for an explicit allowlist of hosts —
    this prevents SSRF via a card template that references arbitrary URLs.
    """
    # Static files
    if uri.startswith(settings.STATIC_URL):
        path = uri.replace(settings.STATIC_URL, '')
        result = finders.find(path)
        if result:
            return result

    # Media files
    if uri.startswith(settings.MEDIA_URL):
        path = uri.replace(settings.MEDIA_URL, '')
        candidate = os.path.join(settings.MEDIA_ROOT, path)
        # Ensure the resolved path is still inside MEDIA_ROOT
        real = os.path.realpath(candidate)
        if not real.startswith(os.path.realpath(settings.MEDIA_ROOT)):
            raise ValueError(f"Refusing to load out-of-tree media: {uri}")
        return candidate

    # Absolute local path
    if os.path.isfile(uri):
        return uri

    # Remote URLs — allowlist only
    if uri.startswith(('http://', 'https://')):
        from urllib.parse import urlparse
        host = urlparse(uri).hostname or ''
        if host in ALLOWED_PDF_REMOTE_HOSTS:
            return uri
        raise ValueError(f"Refusing to fetch remote resource: {uri}")

    return os.path.join(settings.MEDIA_ROOT, uri)


def _safe_filename(name, fallback="document.pdf"):
    """
    Sanitize a filename for Content-Disposition. Strips path separators,
    CR/LF, and non-alphanumeric characters (except dots, dashes, underscores).
    """
    name = (name or '').strip()
    if not name:
        return fallback
    # Strip any directory components
    name = os.path.basename(name)
    # Replace disallowed chars
    name = PDF_FILENAME_SAFE.sub('_', name)
    if not name.lower().endswith('.pdf'):
        name = name + '.pdf'
    return name[:200] or fallback


def _render_pdf(template_name, context, filename):
    """Shared PDF renderer. Sanitizes filename; raises on failure."""
    if not XHTML2PDF_AVAILABLE:
        return HttpResponse(
            "xhtml2pdf is not installed. Run: pip install xhtml2pdf",
            status=500,
        )

    html_string = render_to_string(template_name, context)
    response = HttpResponse(content_type='application/pdf')

    safe = _safe_filename(filename)
    response['Content-Disposition'] = f'inline; filename="{safe}"'

    result = pisa.CreatePDF(
        io.BytesIO(html_string.encode("UTF-8")),
        dest=response,
        link_callback=link_callback,
    )

    if result.err:
        return HttpResponse(
            "PDF generation failed. Please contact an administrator.",
            status=500,
        )
    return response


def _apply_print_filter(queryset, printed_param):
    """
    Apply the ?printed= filter. Unknown values are treated as no filter,
    but we validate at the view level too.
    """
    if printed_param == 'no':
        return queryset.filter(print_count=0)
    if printed_param == 'yes':
        return queryset.filter(print_count__gt=0)
    if printed_param == 'once':
        return queryset.filter(print_count=1)
    if printed_param == 'reprinted':
        return queryset.filter(print_count__gt=1)
    return queryset


def _require_staff(view_func):
    """
    Decorator: require authentication. Use this on every card view.
    Replace with your own role check if you have role-based permissions.
    """
    @wraps(view_func)
    @login_required
    def _wrapped(request, *args, **kwargs):
        return view_func(request, *args, **kwargs)
    return _wrapped


def _require_admin(view_func):
    """
    Decorator: require authentication AND staff status.
    Replace `user.is_staff` with your own permission check if needed.
    """
    @wraps(view_func)
    @login_required
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_staff:
            raise PermissionDenied("Administrator access required.")
        return view_func(request, *args, **kwargs)
    return _wrapped


# ============================================================================
# CARD / TEACHER VIEWS
# ============================================================================
@require_http_methods(["GET"])
@_require_staff
def card_list(request):
    """Dashboard — staff cards with filters and print tracking."""
    teachers = (
        Teacher.objects
        .select_related('department', 'template')
        .prefetch_related('levels')
        .order_by('full_name')
    )

    # --- Filters (validated) ---
    q        = request.GET.get('q', '').strip()[:200]
    role     = request.GET.get('role', '').strip()
    status   = request.GET.get('status', '').strip()
    dept     = request.GET.get('dept', '').strip()
    printed  = request.GET.get('printed', '').strip()

    if role and role not in dict(Teacher.ROLE_CHOICES):
        role = ''
    if status and status not in dict(Teacher.CARD_STATUS):
        status = ''
    if printed not in PRINT_FILTERS:
        printed = ''

    if q:
        teachers = teachers.filter(
            Q(full_name__icontains=q) |
            Q(employee_id__icontains=q) |
            Q(email__icontains=q) |
            Q(phone__icontains=q)
        )
    if role:
        teachers = teachers.filter(role=role)
    if status:
        teachers = teachers.filter(status=status)
    if dept:
        try:
            teachers = teachers.filter(department__id=int(dept))
        except (TypeError, ValueError):
            pass

    teachers = _apply_print_filter(teachers, printed)

    # Materialise once, partition in Python
    teachers = list(teachers)
    unprinted_teachers = [t for t in teachers if t.print_count == 0]
    printed_teachers   = [t for t in teachers if t.print_count == 1]
    reprinted_teachers = [t for t in teachers if t.print_count > 1]

    # Single aggregate query instead of 7 COUNT() queries
    agg = Teacher.objects.aggregate(
        total=Count('id'),
        active=Count('id', filter=Q(status='active')),
        teachers=Count('id', filter=Q(role='TEACHER')),
        unprinted=Count('id', filter=Q(print_count=0)),
        printed=Count('id', filter=Q(print_count=1)),
        reprinted=Count('id', filter=Q(print_count__gt=1)),
    )
    stats = {
        'total':       agg['total'] or 0,
        'active':      agg['active'] or 0,
        'teachers':    agg['teachers'] or 0,
        'departments': Department.objects.filter(is_active=True).count(),
        'unprinted':   agg['unprinted'] or 0,
        'printed':     agg['printed'] or 0,
        'reprinted':   agg['reprinted'] or 0,
    }

    context = {
        'teachers': teachers,
        'unprinted_teachers': unprinted_teachers,
        'printed_teachers':   printed_teachers,
        'reprinted_teachers': reprinted_teachers,
        'unprinted_count': len(unprinted_teachers),
        'printed_count':   len(printed_teachers),
        'reprinted_count': len(reprinted_teachers),
        'school': get_school(),
        'departments': Department.objects.filter(is_active=True),
        'roles': Teacher.ROLE_CHOICES,
        'stats': stats,
        'current_filters': {
            'q': q, 'role': role, 'status': status,
            'dept': dept, 'printed': printed,
        },
    }
    return render(request, 'id_cards/card_list.html', context)


@require_http_methods(["GET"])
@_require_staff
def card_detail(request, pk):
    teacher = get_object_or_404(
        Teacher.objects
        .select_related('department', 'template')
        .prefetch_related('levels'),
        pk=pk,
    )
    return render(request, 'id_cards/card_detail.html', {
        'teacher': teacher,
        'school': get_school(),
    })


@require_http_methods(["GET", "POST"])
@_require_admin
def card_create(request):
    if request.method == 'POST':
        form = TeacherForm(request.POST, request.FILES)
        if form.is_valid():
            teacher = form.save()
            messages.success(
                request,
                f"ID card for {teacher.full_name} created — "
                f"Employee ID: {teacher.employee_id}",
            )
            return redirect('id_cards:card_detail', pk=teacher.pk)
    else:
        form = TeacherForm()
    return render(request, 'id_cards/card_form.html', {
        'form': form,
        'school': get_school(),
        'title': 'Create New Staff ID',
    })


@require_http_methods(["GET", "POST"])
@_require_admin
def card_edit(request, pk):
    teacher = get_object_or_404(Teacher, pk=pk)
    if request.method == 'POST':
        form = TeacherForm(request.POST, request.FILES, instance=teacher)
        if form.is_valid():
            form.save()
            messages.success(request, f"ID card for {teacher.full_name} updated.")
            return redirect('id_cards:card_detail', pk=teacher.pk)
    else:
        form = TeacherForm(instance=teacher)
    return render(request, 'id_cards/card_form.html', {
        'form': form,
        'teacher': teacher,
        'school': get_school(),
        'title': f'Edit — {teacher.full_name}',
    })


@require_http_methods(["GET", "POST"])
@_require_admin
def card_delete(request, pk):
    teacher = get_object_or_404(Teacher, pk=pk)
    if request.method == 'POST':
        name = teacher.full_name
        teacher.delete()
        messages.success(request, f"Deleted {name}'s ID card.")
        return redirect('id_cards:card_list')
    return render(request, 'id_cards/card_confirm_delete.html', {
        'teacher': teacher,
        'school': get_school(),
    })


# ============================================================================
# PRINT VIEWS (browser-native)
# ============================================================================
@require_http_methods(["GET", "POST"])
@_require_staff
def card_print(request, pk):
    """
    Render a single card for browser printing.

    Print tracking is only incremented when the request is a POST, so
    crawlers, prefetchers, and email link scanners can't mutate history.
    """
    teacher = get_object_or_404(Teacher, pk=pk)

    tracked = False
    if request.method == 'POST' and request.POST.get('track') == '1':
        teacher.mark_printed()
        tracked = True

    return render(request, 'id_cards/card_print.html', {
        'teacher': teacher,
        'school': get_school(),
        'tracked': tracked,
        'is_bulk': False,
    })


@require_http_methods(["GET", "POST"])
@_require_staff
def card_print_all(request):
    """
    Print all cards — bulk view.

    Print tracking only fires on POST with track=1.
    Query params on GET: ?printed=no|yes|once|reprinted
    """
    teachers_qs = (
        Teacher.objects
        .filter(status='active')
        .select_related('department', 'template')
        .order_by('full_name')
    )

    printed_filter = request.GET.get('printed', '')
    if printed_filter not in PRINT_FILTERS:
        printed_filter = ''
    teachers_qs = _apply_print_filter(teachers_qs, printed_filter)

    teachers = list(teachers_qs)

    tracked = False
    if request.method == 'POST' and request.POST.get('track') == '1':
        if teachers:
            Teacher.mark_many_printed(teachers)
            # Re-fetch only the print-tracking fields in one query
            refreshed = {
                t.pk: t for t in Teacher.objects.filter(
                    pk__in=[t.pk for t in teachers]
                ).only('pk', 'print_count', 'first_printed_at', 'last_printed_at')
            }
            for t in teachers:
                r = refreshed.get(t.pk)
                if r:
                    t.print_count = r.print_count
                    t.first_printed_at = r.first_printed_at
                    t.last_printed_at = r.last_printed_at
            tracked = True

    return render(request, 'id_cards/card_print.html', {
        'teachers': teachers,
        'school': get_school(),
        'print_all': True,
        'tracked': tracked,
        'is_bulk': True,
    })


@require_POST
@_require_admin
def card_print_reset(request, pk):
    """
    Reset print tracking on a single card. POST only, confirmed via
    PrintResetForm (typed phrase).
    """
    teacher = get_object_or_404(Teacher, pk=pk)
    form = PrintResetForm(request.POST, teacher=teacher)

    if form.is_valid():
        previous_count = teacher.print_count or 0
        teacher.reset_print_tracking()
        messages.success(
            request,
            f"Print tracking reset for {teacher.full_name} "
            f"(was {previous_count} print{'s' if previous_count != 1 else ''}).",
        )
    else:
        messages.error(
            request,
            "Print tracking was NOT reset — confirmation phrase didn't match.",
        )

    return redirect('id_cards:card_detail', pk=pk)


@require_POST
@_require_admin
def reset_all_print_counts(request):
    """
    Bulk-reset print tracking for every staff member.
    POST only + explicit confirmation phrase.
    """
    confirm = (request.POST.get('confirm') or '').strip().upper()
    if confirm != 'RESET':
        messages.error(
            request,
            "Print tracking was NOT reset — type RESET to confirm.",
        )
        return redirect('id_cards:school_settings')

    updated = Teacher.reset_all_print_tracking(confirm=True)
    messages.success(
        request,
        f"Print tracking reset for {updated} staff record{'s' if updated != 1 else ''}.",
    )
    return redirect('id_cards:school_settings')


# ============================================================================
# PDF VIEWS
# ============================================================================
@require_http_methods(["GET", "POST"])
@_require_staff
def card_pdf(request, pk):
    """
    Download a single card as PDF.

    Print tracking only fires on POST with track=1.
    """
    teacher = get_object_or_404(Teacher, pk=pk)

    tracked = False
    if request.method == 'POST' and request.POST.get('track') == '1':
        teacher.mark_printed()
        tracked = True

    safe_name = _safe_filename(
        f"{teacher.full_name}_{teacher.employee_id}.pdf",
        fallback=f"card_{teacher.employee_id}.pdf",
    )
    return _render_pdf(
        'id_cards/card_pdf.html',
        {
            'teacher': teacher,
            'school': get_school(),
            'single': True,
            'tracked': tracked,
        },
        safe_name,
    )


@require_http_methods(["GET", "POST"])
@_require_staff
def card_pdf_all(request):
    """
    Download all active cards as one PDF.

    Print tracking only fires on POST with track=1.
    Enforces a safety cap (MAX_BULK_PRINT_CARDS) to avoid request timeouts.
    """
    teachers_qs = (
        Teacher.objects
        .filter(status='active')
        .select_related('department', 'template')
        .order_by('full_name')
    )

    printed_filter = request.GET.get('printed', '')
    if printed_filter not in PRINT_FILTERS:
        printed_filter = ''
    teachers_qs = _apply_print_filter(teachers_qs, printed_filter)

    total = teachers_qs.count()
    if total > MAX_BULK_PRINT_CARDS:
        messages.error(
            request,
            f"Too many cards ({total}) — the limit is {MAX_BULK_PRINT_CARDS}. "
            f"Please narrow the filter.",
        )
        return redirect('id_cards:card_list')

    teachers = list(teachers_qs)

    tracked = False
    if request.method == 'POST' and request.POST.get('track') == '1' and teachers:
        Teacher.mark_many_printed(teachers)
        tracked = True

    return _render_pdf(
        'id_cards/card_pdf.html',
        {
            'teachers': teachers,
            'school': get_school(),
            'print_all': True,
            'tracked': tracked,
        },
        "All_Staff_ID_Cards.pdf",
    )


# ============================================================================
# SCHOOL SETTINGS
# ============================================================================
@require_http_methods(["GET", "POST"])
@_require_admin
def school_settings(request):
    school = get_school()

    if request.method == 'POST':
        form = SchoolForm(request.POST, request.FILES, instance=school)
        if form.is_valid():
            form.save()
            messages.success(request, "School branding updated.")
            return redirect('id_cards:school_settings')
    else:
        form = SchoolForm(instance=school)

    totals = Teacher.objects.aggregate(
        total=Count('id'),
        total_prints=Sum('print_count'),
        last_print=Max('last_printed_at'),
        unprinted=Count('id', filter=Q(print_count=0)),
        printed=Count('id', filter=Q(print_count=1)),
        reprinted=Count('id', filter=Q(print_count__gt=1)),
    )
    print_stats = {
        'total':        totals['total'] or 0,
        'total_prints': totals['total_prints'] or 0,
        'last_print':   totals['last_print'],
        'unprinted':    totals['unprinted'] or 0,
        'printed':      totals['printed'] or 0,
        'reprinted':    totals['reprinted'] or 0,
    }

    return render(request, 'id_cards/school_settings.html', {
        'form': form,
        'school': school,
        'print_stats': print_stats,
    })


# ============================================================================
# ID CARD TEMPLATE CRUD
# ============================================================================
@require_http_methods(["GET"])
@_require_staff
def template_list(request):
    templates = IDCardTemplate.objects.all().order_by('name')
    return render(request, 'id_cards/template_list.html', {
        'templates': templates,
        'school': get_school(),
    })


@require_http_methods(["GET", "POST"])
@_require_admin
def template_create(request):
    if request.method == 'POST':
        form = IDCardTemplateForm(request.POST)
        if form.is_valid():
            tpl = form.save()
            messages.success(request, f"Template '{tpl.name}' created.")
            return redirect('id_cards:template_list')
    else:
        form = IDCardTemplateForm()
    return render(request, 'id_cards/template_form.html', {
        'form': form,
        'school': get_school(),
        'title': 'Add Card Template',
    })


@require_http_methods(["GET", "POST"])
@_require_admin
def template_edit(request, pk):
    tpl = get_object_or_404(IDCardTemplate, pk=pk)
    if request.method == 'POST':
        form = IDCardTemplateForm(request.POST, instance=tpl)
        if form.is_valid():
            form.save()
            messages.success(request, f"Template '{tpl.name}' updated.")
            return redirect('id_cards:template_list')
    else:
        form = IDCardTemplateForm(instance=tpl)
    return render(request, 'id_cards/template_form.html', {
        'form': form,
        'template': tpl,
        'school': get_school(),
        'title': f'Edit — {tpl.name}',
    })


@require_http_methods(["GET", "POST"])
@_require_admin
def template_delete(request, pk):
    tpl = get_object_or_404(IDCardTemplate, pk=pk)
    if request.method == 'POST':
        name = tpl.name
        tpl.delete()
        messages.success(request, f"Template '{name}' deleted.")
        return redirect('id_cards:template_list')
    return render(request, 'id_cards/template_confirm_delete.html', {
        'template': tpl,
        'school': get_school(),
    })


# ============================================================================
# DEPARTMENT CRUD
# ============================================================================
@require_http_methods(["GET"])
@_require_staff
def department_list(request):
    departments = (
        Department.objects
        .annotate(teacher_count=Count('teachers'))
        .order_by('name')
    )
    return render(request, 'id_cards/department_list.html', {
        'departments': departments,
        'school': get_school(),
    })


@require_http_methods(["GET", "POST"])
@_require_admin
def department_create(request):
    if request.method == 'POST':
        form = DepartmentForm(request.POST)
        if form.is_valid():
            dept = form.save()
            messages.success(
                request,
                f"Department '{dept.name}' created (code: {dept.code}).",
            )
            return redirect('id_cards:department_list')
    else:
        form = DepartmentForm()
    return render(request, 'id_cards/department_form.html', {
        'form': form,
        'school': get_school(),
        'title': 'Add Department',
    })


@require_http_methods(["GET", "POST"])
@_require_admin
def department_edit(request, pk):
    dept = get_object_or_404(Department, pk=pk)
    if request.method == 'POST':
        form = DepartmentForm(request.POST, instance=dept)
        if form.is_valid():
            form.save()
            messages.success(request, f"Department '{dept.name}' updated.")
            return redirect('id_cards:department_list')
    else:
        form = DepartmentForm(instance=dept)
    return render(request, 'id_cards/department_form.html', {
        'form': form,
        'department': dept,
        'school': get_school(),
        'title': f'Edit — {dept.name}',
    })


@require_http_methods(["GET", "POST"])
@_require_admin
def department_delete(request, pk):
    dept = get_object_or_404(Department, pk=pk)
    if request.method == 'POST':
        name = dept.name
        dept.delete()
        messages.success(request, f"Department '{name}' deleted.")
        return redirect('id_cards:department_list')
    return render(request, 'id_cards/department_confirm_delete.html', {
        'department': dept,
        'school': get_school(),
    })


# ============================================================================
# LEVEL CRUD
# ============================================================================
@require_http_methods(["GET"])
@_require_staff
def level_list(request):
    levels = Level.objects.all().order_by('order', 'name')
    return render(request, 'id_cards/level_list.html', {
        'levels': levels,
        'school': get_school(),
    })


@require_http_methods(["GET", "POST"])
@_require_admin
def level_create(request):
    if request.method == 'POST':
        form = LevelForm(request.POST)
        if form.is_valid():
            level = form.save()
            messages.success(request, f"Level '{level.name}' created.")
            return redirect('id_cards:level_list')
    else:
        form = LevelForm()
    return render(request, 'id_cards/level_form.html', {
        'form': form,
        'school': get_school(),
        'title': 'Add Level',
    })


@require_http_methods(["GET", "POST"])
@_require_admin
def level_edit(request, pk):
    level = get_object_or_404(Level, pk=pk)
    if request.method == 'POST':
        form = LevelForm(request.POST, instance=level)
        if form.is_valid():
            form.save()
            messages.success(request, f"Level '{level.name}' updated.")
            return redirect('id_cards:level_list')
    else:
        form = LevelForm(instance=level)
    return render(request, 'id_cards/level_form.html', {
        'form': form,
        'level': level,
        'school': get_school(),
        'title': f'Edit — {level.name}',
    })


@require_http_methods(["GET", "POST"])
@_require_admin
def level_delete(request, pk):
    level = get_object_or_404(Level, pk=pk)
    if request.method == 'POST':
        name = level.name
        level.delete()
        messages.success(request, f"Level '{name}' deleted.")
        return redirect('id_cards:level_list')
    return render(request, 'id_cards/level_confirm_delete.html', {
        'level': level,
        'school': get_school(),
    })


# ============================================================================
# BULK CSV IMPORT
# ============================================================================
def _parse_import_date(raw):
    """Best-effort date parser. Returns a date or None."""
    raw = (raw or '').strip()
    if not raw:
        return None
    for fmt in ('%Y-%m-%d', '%m/%Y', '%m/%d/%Y', '%d/%m/%Y'):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


@require_http_methods(["GET", "POST"])
@_require_admin
def bulk_import(request):
    """
    Upload a CSV with columns:
        full_name, designation, role, department, levels,
        email, phone, valid_thru, emergency_contact_phone,
        issue_date, expiry_date, id_card_terms,
        authorized_use, security

    Employee IDs are auto-generated by the model.
    Capped at MAX_BULK_IMPORT_ROWS to prevent DoS.
    """
    if request.method == 'POST':
        form = BulkImportForm(request.POST, request.FILES)
        if not form.is_valid():
            for error in form.errors.values():
                messages.error(request, error.as_text())
            return redirect('id_cards:bulk_import')

        csv_file = form.cleaned_data['csv_file']

        try:
            decoded = csv_file.read().decode('utf-8-sig').splitlines()
        except UnicodeDecodeError:
            messages.error(
                request,
                "File is not valid UTF-8. Please re-export as UTF-8 CSV.",
            )
            return redirect('id_cards:bulk_import')

        reader = csv.DictReader(decoded)
        rows = list(reader)

        if len(rows) > MAX_BULK_IMPORT_ROWS:
            messages.error(
                request,
                f"Too many rows ({len(rows)}). "
                f"The limit is {MAX_BULK_IMPORT_ROWS} per upload.",
            )
            return redirect('id_cards:bulk_import')

        created, skipped, errors = 0, 0, []
        valid_roles = dict(Teacher.ROLE_CHOICES)

        # Pre-resolve departments and levels once — avoids N queries per row.
        dept_lookup = {
            d.name.lower(): d for d in Department.objects.all()
        }
        level_lookup = {
            l.name.lower(): l for l in Level.objects.all()
        }

        for i, row in enumerate(reader, start=2):
            full_name = (row.get('full_name') or '').strip()
            if not full_name:
                skipped += 1
                continue

            dept_name = (row.get('department') or '').strip().lower()
            dept = dept_lookup.get(dept_name) if dept_name else None

            role_key = (row.get('role') or 'TEACHER').strip().upper()
            if role_key not in valid_roles:
                role_key = 'TEACHER'

            try:
                with transaction.atomic():
                    teacher = Teacher.objects.create(
                        full_name=full_name,
                        designation=(row.get('designation') or '').strip(),
                        role=role_key,
                        department=dept,
                        email=(row.get('email') or '').strip(),
                        phone=(row.get('phone') or '').strip(),
                        valid_thru=_parse_import_date(row.get('valid_thru')),
                        issue_date=_parse_import_date(row.get('issue_date')),
                        expiry_date=_parse_import_date(row.get('expiry_date')),
                        emergency_contact_phone=(
                            row.get('emergency_contact_phone') or ''
                        ).strip(),
                        id_card_terms=(row.get('id_card_terms') or '').strip(),
                        authorized_use=(row.get('authorized_use') or '').strip(),
                        security=(row.get('security') or '').strip(),
                    )

                    levels_raw = (row.get('levels') or '').strip()
                    if levels_raw:
                        names = [
                            n.strip().lower()
                            for n in levels_raw.split(';') if n.strip()
                        ]
                        lvls = [
                            level_lookup[n] for n in names
                            if n in level_lookup
                        ]
                        if lvls:
                            teacher.levels.set(lvls)
                created += 1

            except (IntegrityError, ValidationError, ValueError) as exc:
                errors.append(f"Row {i} ({full_name}): {exc}")
                skipped += 1

        if created:
            messages.success(request, f"Imported {created} staff record(s).")
        if skipped:
            messages.warning(request, f"Skipped {skipped} row(s).")
        for err in errors[:5]:
            messages.error(request, err)
        if len(errors) > 5:
            messages.error(request, f"…and {len(errors) - 5} more errors.")

        return redirect('id_cards:card_list')

    return render(request, 'id_cards/bulk_import.html', {
        'form': BulkImportForm(),
        'school': get_school(),
    })


# ============================================================================
# QR CODE
# ============================================================================
import qrcode
from qrcode.image.svg import SvgPathImage


@require_http_methods(["GET"])
@_require_staff
def qr_employee_svg(request, employee_id):
    """
    Returns a QR code SVG encoding the teacher's information plus the
    school's contact details.

    Requires login. Staff can only fetch their own card unless they are
    admins — this prevents enumeration of the full staff roster.
    """
    teacher = get_object_or_404(Teacher, employee_id=employee_id)

    # Object-level permission: only admins or the teacher themselves.
    if not request.user.is_staff:
        own = getattr(request.user, 'teacher', None)
        if own is None or own.pk != teacher.pk:
            raise PermissionDenied("You can only view your own QR code.")

    school = get_school()

    lines = []

    def add(label, value):
        if value:
            lines.append(f"{label}: {value}")

    add("NAME", teacher.full_name)
    add("EMPLOYEE ID", teacher.employee_id)
    add("DESIGNATION", teacher.designation)
    add("ROLE", teacher.get_role_display())
    add("DEPARTMENT", teacher.department_display if teacher.department else "")
    add("LEVELS", teacher.levels_display)
    add("EMAIL", teacher.email)
    add("PHONE", teacher.phone)
    add("EMERGENCY", teacher.emergency_contact_phone)
    if teacher.valid_thru:
        add("VALID THRU", teacher.valid_thru.strftime("%m/%Y"))
    if teacher.issue_date:
        add("ISSUED", teacher.issue_date.strftime("%m/%Y"))

    if lines:
        lines.append("--")
    add("SCHOOL", school.name)
    add("ADDRESS", school.address)
    add("PHONE 1", school.contact_phone_1)
    add("PHONE 2", school.contact_phone_2)

    qr_data = "\n".join(lines)

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,   # spec-required quiet zone
    )
    qr.add_data(qr_data)
    qr.make(fit=True)

    img = qr.make_image(image_factory=SvgPathImage)
    buffer = io.BytesIO()
    img.save(buffer)
    buffer.seek(0)

    response = HttpResponse(buffer.getvalue(), content_type='image/svg+xml')
    # Prevent this response from being cached by intermediaries.
    response['Cache-Control'] = 'private, no-store'
    return response


def _prepare_teacher_for_pdf(teacher):
    """Attach PDF-friendly attributes to a teacher instance."""
    # Force relative photo URL so xhtml2pdf loads from MEDIA_ROOT.
    if teacher.photo:
        teacher.photo_relative_url = teacher.photo.url  # already /media/...
    return teacher

def _prepare_qr_for_pdf(teacher):
    """
    Generate a QR code as a base64 data URI, so xhtml2pdf doesn't have
    to fetch it over HTTP (which would hit the login-required QR view).
    """
    import base64
    import qrcode
    import io as _io

    school = get_school()
    lines = []

    def add(label, value):
        if value:
            lines.append(f"{label}: {value}")

    add("NAME", teacher.full_name)
    add("EMPLOYEE ID", teacher.employee_id)
    add("DESIGNATION", teacher.designation)
    add("ROLE", teacher.get_role_display())
    add("DEPARTMENT", teacher.department_display if teacher.department else "")
    add("LEVELS", teacher.levels_display)
    add("EMAIL", teacher.email)
    add("PHONE", teacher.phone)
    add("EMERGENCY", teacher.emergency_contact_phone)

    if teacher.resolved_issue_date:
        add("ISSUED", teacher.resolved_issue_date.strftime("%m/%Y"))

    if teacher.resolved_expiry_date:
        add("EXPIRES", teacher.resolved_expiry_date.strftime("%m/%Y"))

    if lines:
        lines.append("--")

    add("SCHOOL", school.name)
    add("ADDRESS", school.address)
    add("PHONE 1", school.contact_phone_1)
    add("PHONE 2", school.contact_phone_2)

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data("\n".join(lines))
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    buf = _io.BytesIO()
    img.save(buf, format='PNG')
    b64 = base64.b64encode(buf.getvalue()).decode('ascii')
    teacher.qr_data_uri = f"data:image/png;base64,{b64}"
    return teacher