import io
import os
import csv
from datetime import datetime

from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.contrib import messages
from django.views.decorators.http import require_http_methods, require_POST
from django.conf import settings
from django.contrib.staticfiles import finders
from django.db import transaction
from django.db.models import Q, Count, Sum, Max
from django.utils import timezone

from .models import Teacher, School, IDCardTemplate, Department, Level
from .forms import (
    TeacherForm, SchoolForm, DepartmentForm, LevelForm, BulkImportForm,
    PrintResetForm,
)

# ---------------------------------------------------------------------------
# Optional PDF backend: xhtml2pdf
# ---------------------------------------------------------------------------
try:
    from xhtml2pdf import pisa
    XHTML2PDF_AVAILABLE = True
except ImportError:
    XHTML2PDF_AVAILABLE = False


# ============================================================================
# HELPERS
# ============================================================================
def get_school():
    """Return the single School branding record (created on first access)."""
    school, _ = School.objects.get_or_create(pk=1)
    return school


def link_callback(uri, rel):
    """
    Resolve HTML URIs to absolute filesystem paths so xhtml2pdf can embed
    images and CSS. Handles /static/, /media/, absolute paths, and remote URLs.
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
        return os.path.join(settings.MEDIA_ROOT, path)

    # Absolute local path already
    if os.path.isfile(uri):
        return uri

    # Remote URLs (e.g. Google Fonts) — pass through, xhtml2pdf will fetch
    if uri.startswith(('http://', 'https://')):
        return uri

    # Fallback — treat as media-relative
    return os.path.join(settings.MEDIA_ROOT, uri)


def _render_pdf(template_name, context, filename):
    """Shared PDF renderer for single and bulk exports."""
    if not XHTML2PDF_AVAILABLE:
        return HttpResponse(
            "xhtml2pdf is not installed. Run: pip install xhtml2pdf",
            status=500,
        )

    html_string = render_to_string(template_name, context)
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="{filename}"'

    result = pisa.CreatePDF(
        io.BytesIO(html_string.encode("UTF-8")),
        dest=response,
        link_callback=link_callback,
    )

    if result.err:
        return HttpResponse(f"PDF generation error: {result.err}", status=500)
    return response


def _apply_print_filter(queryset, printed_param):
    """
    Apply the ?printed= filter to a teacher queryset.

    Accepted values:
        ''          → no filter (all)
        'no'        → unprinted only (print_count == 0)
        'yes'       → printed any number of times (print_count > 0)
        'once'      → printed exactly once (print_count == 1)
        'reprinted' → printed more than once (print_count > 1)
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


# ============================================================================
# CARD / TEACHER VIEWS
# ============================================================================
def card_list(request):
    """Dashboard — shows all staff cards with filters and print tracking."""
    teachers = (
        Teacher.objects
        .select_related('department', 'template')
        .prefetch_related('levels')
        .order_by('full_name')
    )

    # --- Filters ---
    q        = request.GET.get('q', '').strip()
    role     = request.GET.get('role', '')
    status   = request.GET.get('status', '')
    dept     = request.GET.get('dept', '')
    printed  = request.GET.get('printed', '')

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
        teachers = teachers.filter(department__id=dept)

    teachers = _apply_print_filter(teachers, printed)

    # --- Materialise the queryset ONCE, then partition in Python ---
    # This is faster than running three .filter().count() queries,
    # and gives the template three pre-split lists to iterate over.
    teachers = list(teachers)

    unprinted_teachers = [t for t in teachers if t.print_count == 0]
    printed_teachers   = [t for t in teachers if t.print_count == 1]
    reprinted_teachers = [t for t in teachers if t.print_count > 1]

    # --- Stats (across the whole DB, not the filtered set) ---
    stats = {
        'total':       Teacher.objects.count(),
        'active':      Teacher.objects.filter(status='active').count(),
        'teachers':    Teacher.objects.filter(role='TEACHER').count(),
        'departments': Department.objects.filter(is_active=True).count(),
        'unprinted':   Teacher.objects.filter(print_count=0).count(),
        'printed':     Teacher.objects.filter(print_count=1).count(),
        'reprinted':   Teacher.objects.filter(print_count__gt=1).count(),
    }

    context = {
        # Base list (still useful for the header count and empty check)
        'teachers': teachers,

        # Three partitioned lists — the template iterates over these
        'unprinted_teachers': unprinted_teachers,
        'printed_teachers':   printed_teachers,
        'reprinted_teachers': reprinted_teachers,

        # Section counts
        'unprinted_count': len(unprinted_teachers),
        'printed_count':   len(printed_teachers),
        'reprinted_count': len(reprinted_teachers),

        # Rest of the page context
        'school': get_school(),
        'departments': Department.objects.filter(is_active=True),
        'roles': Teacher.ROLE_CHOICES,
        'stats': stats,
        'current_filters': {
            'q': q,
            'role': role,
            'status': status,
            'dept': dept,
            'printed': printed,
        },
    }
    return render(request, 'id_cards/card_list.html', context)

def card_detail(request, pk):
    teacher = get_object_or_404(
        Teacher.objects.select_related('department', 'template').prefetch_related('levels'),
        pk=pk,
    )
    return render(request, 'id_cards/card_detail.html', {
        'teacher': teacher,
        'school': get_school(),
    })

@require_http_methods(["GET", "POST"])
def card_create(request):
    if request.method == 'POST':
        form = TeacherForm(request.POST, request.FILES)
        if form.is_valid():
            teacher = form.save()
            messages.success(
                request,
                f"ID card for {teacher.full_name} created — "
                f"Employee ID: {teacher.employee_id}"
            )
            return redirect('card_detail', pk=teacher.pk)
    else:
        form = TeacherForm()
    return render(request, 'id_cards/card_form.html', {
        'form': form,
        'school': get_school(),
        'title': 'Create New Staff ID',
    })


@require_http_methods(["GET", "POST"])
def card_edit(request, pk):
    teacher = get_object_or_404(Teacher, pk=pk)
    if request.method == 'POST':
        form = TeacherForm(request.POST, request.FILES, instance=teacher)
        if form.is_valid():
            form.save()
            messages.success(request, f"ID card for {teacher.full_name} updated.")
            return redirect('card_detail', pk=teacher.pk)
    else:
        form = TeacherForm(instance=teacher)
    return render(request, 'id_cards/card_form.html', {
        'form': form,
        'teacher': teacher,
        'school': get_school(),
        'title': f'Edit — {teacher.full_name}',
    })


def card_delete(request, pk):
    teacher = get_object_or_404(Teacher, pk=pk)
    if request.method == 'POST':
        name = teacher.full_name
        teacher.delete()
        messages.success(request, f"Deleted {name}'s ID card.")
        return redirect('card_list')
    return render(request, 'id_cards/card_confirm_delete.html', {
        'teacher': teacher,
        'school': get_school(),
    })


# ============================================================================
# PRINT VIEWS (browser-native) — these MARK AS PRINTED
# ============================================================================
def card_print(request, pk):
    """Print a single card — records a print event."""
    teacher = get_object_or_404(Teacher, pk=pk)
    teacher.mark_printed()
    return render(request, 'id_cards/card_print.html', {
        'teacher': teacher,
        'school': get_school(),
    })


def card_print_all(request):
    """
    Print all cards — records a print event per card (bulk).

    Query params:
        ?printed=no        → only unprinted cards
        ?printed=yes       → only already-printed cards (any count)
        ?printed=once      → only printed exactly once
        ?printed=reprinted → only reprinted cards
        (none)             → all active cards
        ?track=0           → do NOT record print events (preview mode)
    """
    teachers_qs = (
        Teacher.objects
        .filter(status='active')
        .select_related('department')
        .order_by('full_name')
    )

    printed_filter = request.GET.get('printed', '')
    teachers_qs = _apply_print_filter(teachers_qs, printed_filter)

    teachers = list(teachers_qs)

    # ---- Print tracking (skippable for preview runs) ----
    track = request.GET.get('track', '1') != '0'
    if track and teachers:
        Teacher.mark_many_printed(teachers)
        # Refresh the instances so the audit strip in the template
        # reflects the NEW count.
        for t in teachers:
            t.refresh_from_db(
                fields=['print_count', 'first_printed_at', 'last_printed_at']
            )

    return render(request, 'id_cards/card_print.html', {
        'teachers': teachers,
        'school': get_school(),
        'print_all': True,
        'tracked': track,
    })


@require_POST
def card_print_reset(request, pk):
    """
    Reset print tracking on a single card.

    POST only. Protected by the PrintResetForm — the admin must type
    "RESET" to confirm, so a misclick can't wipe the audit trail.
    """
    teacher = get_object_or_404(Teacher, pk=pk)
    form = PrintResetForm(request.POST, teacher=teacher)

    if form.is_valid():
        previous_count = teacher.print_count or 0
        teacher.reset_print_tracking()
        messages.success(
            request,
            f"Print tracking reset for {teacher.full_name} "
            f"(was {previous_count} print{'s' if previous_count != 1 else ''})."
        )
    else:
        messages.error(
            request,
            "Print tracking was NOT reset — confirmation phrase didn't match."
        )

    return redirect('card_detail', pk=pk)


@require_POST
def reset_all_print_counts(request):
    """
    Bulk-reset print tracking for every staff member.

    POST only, guarded by CSRF + an explicit confirmation in the template.
    """
    updated = Teacher.reset_all_print_tracking()
    messages.success(
        request,
        f"Print tracking reset for {updated} staff record{'s' if updated != 1 else ''}."
    )
    return redirect('school_settings')


# ============================================================================
# PDF VIEWS — these MARK AS PRINTED too
# ============================================================================
def card_pdf(request, pk):
    """
    Download a single card as PDF — records a print event.

    Query params:
        ?track=0 → do NOT record a print event (preview / re-download)
    """
    teacher = get_object_or_404(Teacher, pk=pk)

    track = request.GET.get('track', '1') != '0'
    if track:
        teacher.mark_printed()

    safe_name = teacher.full_name.replace(' ', '_').replace('/', '_')
    return _render_pdf(
        'id_cards/card_pdf.html',
        {'teacher': teacher, 'school': get_school(), 'single': True},
        f"{safe_name}_{teacher.employee_id}.pdf",
    )


def card_pdf_all(request):
    """
    Download all active cards as one PDF — records a print event per card.

    Query params:
        ?printed=no        → only unprinted
        ?printed=yes       → only already-printed
        ?printed=once      → exactly one print
        ?printed=reprinted → reprinted
        ?track=0           → do NOT record print events
    """
    teachers_qs = (
        Teacher.objects
        .filter(status='active')
        .select_related('department')
        .order_by('full_name')
    )

    printed_filter = request.GET.get('printed', '')
    teachers_qs = _apply_print_filter(teachers_qs, printed_filter)

    teachers = list(teachers_qs)

    track = request.GET.get('track', '1') != '0'
    if track and teachers:
        Teacher.mark_many_printed(teachers)
        for t in teachers:
            t.refresh_from_db(
                fields=['print_count', 'first_printed_at', 'last_printed_at']
            )

    return _render_pdf(
        'id_cards/card_pdf.html',
        {'teachers': teachers, 'school': get_school(), 'print_all': True},
        "All_Staff_ID_Cards.pdf",
    )


# ============================================================================
# SCHOOL SETTINGS
# ============================================================================
@require_http_methods(["GET", "POST"])
def school_settings(request):
    school = get_school()

    if request.method == 'POST':
        form = SchoolForm(request.POST, request.FILES, instance=school)
        if form.is_valid():
            form.save()
            messages.success(request, "School branding updated.")
            return redirect('school_settings')
    else:
        form = SchoolForm(instance=school)

    # ---- Print tracking overview for the settings page ----
    totals = Teacher.objects.aggregate(
        total=Count('id'),
        total_prints=Sum('print_count'),
        last_print=Max('last_printed_at'),
    )
    print_stats = {
        'total':        totals['total'] or 0,
        'total_prints': totals['total_prints'] or 0,
        'last_print':   totals['last_print'],
        'unprinted':    Teacher.objects.filter(print_count=0).count(),
        'printed':      Teacher.objects.filter(print_count=1).count(),
        'reprinted':    Teacher.objects.filter(print_count__gt=1).count(),
    }

    return render(request, 'id_cards/school_settings.html', {
        'form': form,
        'school': school,
        'print_stats': print_stats,
    })


# ============================================================================
# DEPARTMENT CRUD
# ============================================================================
def department_list(request):
    departments = Department.objects.all().order_by('name')
    return render(request, 'id_cards/department_list.html', {
        'departments': departments,
        'school': get_school(),
    })


@require_http_methods(["GET", "POST"])
def department_create(request):
    if request.method == 'POST':
        form = DepartmentForm(request.POST)
        if form.is_valid():
            dept = form.save()
            messages.success(request, f"Department '{dept.name}' created (code: {dept.code}).")
            return redirect('department_list')
    else:
        form = DepartmentForm()
    return render(request, 'id_cards/department_form.html', {
        'form': form,
        'school': get_school(),
        'title': 'Add Department',
    })


@require_http_methods(["GET", "POST"])
def department_edit(request, pk):
    dept = get_object_or_404(Department, pk=pk)
    if request.method == 'POST':
        form = DepartmentForm(request.POST, instance=dept)
        if form.is_valid():
            form.save()
            messages.success(request, f"Department '{dept.name}' updated.")
            return redirect('department_list')
    else:
        form = DepartmentForm(instance=dept)
    return render(request, 'id_cards/department_form.html', {
        'form': form,
        'department': dept,
        'school': get_school(),
        'title': f'Edit — {dept.name}',
    })


def department_delete(request, pk):
    dept = get_object_or_404(Department, pk=pk)
    if request.method == 'POST':
        name = dept.name
        dept.delete()
        messages.success(request, f"Department '{name}' deleted.")
        return redirect('department_list')
    return render(request, 'id_cards/department_confirm_delete.html', {
        'department': dept,
        'school': get_school(),
    })


# ============================================================================
# LEVEL CRUD
# ============================================================================
def level_list(request):
    levels = Level.objects.all().order_by('order', 'name')
    return render(request, 'id_cards/level_list.html', {
        'levels': levels,
        'school': get_school(),
    })


@require_http_methods(["GET", "POST"])
def level_create(request):
    if request.method == 'POST':
        form = LevelForm(request.POST)
        if form.is_valid():
            level = form.save()
            messages.success(request, f"Level '{level.name}' created.")
            return redirect('level_list')
    else:
        form = LevelForm()
    return render(request, 'id_cards/level_form.html', {
        'form': form,
        'school': get_school(),
        'title': 'Add Level',
    })


@require_http_methods(["GET", "POST"])
def level_edit(request, pk):
    level = get_object_or_404(Level, pk=pk)
    if request.method == 'POST':
        form = LevelForm(request.POST, instance=level)
        if form.is_valid():
            form.save()
            messages.success(request, f"Level '{level.name}' updated.")
            return redirect('level_list')
    else:
        form = LevelForm(instance=level)
    return render(request, 'id_cards/level_form.html', {
        'form': form,
        'level': level,
        'school': get_school(),
        'title': f'Edit — {level.name}',
    })


def level_delete(request, pk):
    level = get_object_or_404(Level, pk=pk)
    if request.method == 'POST':
        name = level.name
        level.delete()
        messages.success(request, f"Level '{name}' deleted.")
        return redirect('level_list')
    return render(request, 'id_cards/level_confirm_delete.html', {
        'level': level,
        'school': get_school(),
    })


# ============================================================================
# BULK CSV IMPORT
# ============================================================================
@require_http_methods(["GET", "POST"])
def bulk_import(request):
    """
    Upload a CSV with columns:
        full_name, designation, role, department, levels,
        email, phone, valid_thru, blood_group, emergency_contact_phone

    - department : department NAME (must already exist)
    - levels     : semicolon-separated level NAMES (e.g. "JSS1;JSS2")
    - role       : one of the ROLE_CHOICES keys (TEACHER, SECRETARY, …)
    - valid_thru : YYYY-MM-DD or MM/YYYY (best-effort parsing)
    - blood_group: O+, O-, A+, A-, B+, B-, AB+, AB- (optional)

    Employee IDs are auto-generated by the model.
    """
    if request.method == 'POST':
        form = BulkImportForm(request.POST, request.FILES)
        if not form.is_valid():
            for error in form.errors.values():
                messages.error(request, error.as_text())
            return redirect('bulk_import')

        csv_file = form.cleaned_data['csv_file']
        decoded = csv_file.read().decode('utf-8-sig').splitlines()
        reader = csv.DictReader(decoded)

        created, skipped, errors = 0, 0, []

        valid_roles = dict(Teacher.ROLE_CHOICES)
        valid_blood_groups = {
            choice[0] for choice in Teacher.BLOOD_GROUP_CHOICES if choice[0]
        }

        for i, row in enumerate(reader, start=2):  # row 1 = header
            full_name = (row.get('full_name') or '').strip()
            if not full_name:
                skipped += 1
                continue

            # Resolve department by name
            dept_name = (row.get('department') or '').strip()
            dept = None
            if dept_name:
                dept = Department.objects.filter(name__iexact=dept_name).first()

            # Resolve role (fallback to TEACHER)
            role_key = (row.get('role') or 'TEACHER').strip().upper()
            if role_key not in valid_roles:
                role_key = 'TEACHER'

            # Parse valid_thru (best-effort)
            valid_thru = None
            vt_raw = (row.get('valid_thru') or '').strip()
            if vt_raw:
                for fmt in ('%Y-%m-%d', '%m/%Y', '%m/%d/%Y', '%d/%m/%Y'):
                    try:
                        valid_thru = datetime.strptime(vt_raw, fmt).date()
                        break
                    except ValueError:
                        continue

            # Blood group (validate against choices)
            blood_group = (row.get('blood_group') or '').strip().upper()
            if blood_group and blood_group not in valid_blood_groups:
                blood_group = ''

            try:
                with transaction.atomic():
                    teacher = Teacher.objects.create(
                        full_name=full_name,
                        designation=(row.get('designation') or '').strip(),
                        role=role_key,
                        department=dept,
                        email=(row.get('email') or '').strip(),
                        phone=(row.get('phone') or '').strip(),
                        valid_thru=valid_thru,
                        blood_group=blood_group,
                        emergency_contact_phone=(
                            row.get('emergency_contact_phone') or ''
                        ).strip(),
                    )
                    # Attach levels
                    levels_raw = (row.get('levels') or '').strip()
                    if levels_raw:
                        names = [n.strip() for n in levels_raw.split(';') if n.strip()]
                        lvls = Level.objects.filter(name__in=names)
                        teacher.levels.set(lvls)
                created += 1
            except Exception as e:
                errors.append(f"Row {i} ({full_name}): {e}")
                skipped += 1

        if created:
            messages.success(request, f"Imported {created} staff record(s).")
        if skipped:
            messages.warning(request, f"Skipped {skipped} row(s).")
        for err in errors[:5]:
            messages.error(request, err)
        if len(errors) > 5:
            messages.error(request, f"…and {len(errors) - 5} more errors.")

        return redirect('card_list')

    return render(request, 'id_cards/bulk_import.html', {
        'form': BulkImportForm(),
        'school': get_school(),
    })


# ============================================================================
# QR CODE
# ============================================================================
import qrcode
from qrcode.image.svg import SvgPathImage


def qr_employee_svg(request, employee_id):
    """
    Returns a QR code SVG for the given employee_id.
    Encodes the employee ID as plain text — no server verification needed.
    Works offline, in print, and on any QR reader.
    """
    teacher = get_object_or_404(Teacher, employee_id=employee_id)

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=1,
    )
    qr.add_data(teacher.employee_id)
    qr.make(fit=True)

    img = qr.make_image(image_factory=SvgPathImage)
    buffer = io.BytesIO()
    img.save(buffer)
    buffer.seek(0)

    return HttpResponse(buffer.getvalue(), content_type='image/svg+xml')