import io

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.views.decorators.http import require_http_methods, require_POST
from django.db.models import Q
from django.template.loader import render_to_string
from django.http import HttpResponse

from id_cards.models import School, Level, Department
from id_cards.views import _render_pdf, _apply_print_filter, get_school
from .models import Student
from .forms import StudentForm


# ============================================================================
# LIST / DASHBOARD
# ============================================================================
def student_list(request):
    students = (
        Student.objects
        .select_related('level', 'department', 'template')
        .order_by('full_name')
    )

    q        = request.GET.get('q', '').strip()
    status   = request.GET.get('status', '')
    level_id = request.GET.get('level', '')
    printed  = request.GET.get('printed', '')

    if q:
        students = students.filter(
            Q(full_name__icontains=q) |
            Q(admission_number__icontains=q) |
            Q(email__icontains=q) |
            Q(phone__icontains=q)
        )
    if status:
        students = students.filter(status=status)
    if level_id:
        students = students.filter(level__id=level_id)

    students = _apply_print_filter(students, printed)
    students = list(students)

    unprinted = [s for s in students if s.print_count == 0]
    printed_l = [s for s in students if s.print_count == 1]
    reprinted = [s for s in students if s.print_count > 1]

    stats = {
        'total':     Student.objects.count(),
        'active':    Student.objects.filter(status='active').count(),
        'unprinted': Student.objects.filter(print_count=0).count(),
        'printed':   Student.objects.filter(print_count=1).count(),
        'reprinted': Student.objects.filter(print_count__gt=1).count(),
    }

    return render(request, 'student/student_list.html', {
        'students': students,
        'unprinted_students': unprinted,
        'printed_students':   printed_l,
        'reprinted_students': reprinted,
        'unprinted_count': len(unprinted),
        'printed_count':   len(printed_l),
        'reprinted_count': len(reprinted),
        'levels': Level.objects.all().order_by('order', 'name'),
        'school': get_school(),
        'stats': stats,
        'current_filters': {
            'q': q, 'status': status, 'level': level_id, 'printed': printed,
        },
    })


# ============================================================================
# DETAIL / CRUD
# ============================================================================
def student_detail(request, pk):
    student = get_object_or_404(
        Student.objects.select_related('level', 'department', 'template'),
        pk=pk,
    )
    return render(request, 'student/student_detail.html', {
        'student': student,
        'school': get_school(),
    })


@require_http_methods(["GET", "POST"])
def student_create(request):
    if request.method == 'POST':
        form = StudentForm(request.POST, request.FILES)
        if form.is_valid():
            student = form.save()
            messages.success(
                request,
                f"ID card for {student.full_name} created — "
                f"Admission No: {student.admission_number}"
            )
            return redirect('student:student_detail', pk=student.pk)
    else:
        form = StudentForm()
    return render(request, 'student/student_form.html', {
        'form': form,
        'school': get_school(),
        'title': 'Create New Student ID',
    })


@require_http_methods(["GET", "POST"])
def student_edit(request, pk):
    student = get_object_or_404(Student, pk=pk)
    if request.method == 'POST':
        form = StudentForm(request.POST, request.FILES, instance=student)
        if form.is_valid():
            form.save()
            messages.success(request, f"ID card for {student.full_name} updated.")
            return redirect('student:student_detail', pk=student.pk)
    else:
        form = StudentForm(instance=student)
    return render(request, 'student/student_form.html', {
        'form': form,
        'student': student,
        'school': get_school(),
        'title': f'Edit — {student.full_name}',
    })


def student_delete(request, pk):
    student = get_object_or_404(Student, pk=pk)
    if request.method == 'POST':
        name = student.full_name
        student.delete()
        messages.success(request, f"Deleted {name}'s ID card.")
        return redirect('student:student_list')
    return render(request, 'student/student_confirm_delete.html', {
        'student': student,
        'school': get_school(),
    })


# ============================================================================
# PRINT (browser)
# ============================================================================
def student_print(request, pk):
    student = get_object_or_404(Student, pk=pk)
    student.mark_printed()
    return render(request, 'student/student_print.html', {
        'student': student,
        'school': get_school(),
    })


def student_print_all(request):
    qs = (
        Student.objects
        .filter(status='active')
        .select_related('level', 'department')
        .order_by('full_name')
    )
    qs = _apply_print_filter(qs, request.GET.get('printed', ''))
    students = list(qs)

    track = request.GET.get('track', '1') != '0'
    if track and students:
        Student.mark_many_printed(students)
        for s in students:
            s.refresh_from_db(
                fields=['print_count', 'first_printed_at', 'last_printed_at']
            )

    return render(request, 'student/student_print.html', {
        'students': students,
        'school': get_school(),
        'print_all': True,
        'tracked': track,
    })


@require_POST
def student_print_reset(request, pk):
    student = get_object_or_404(Student, pk=pk)
    student.reset_print_tracking()
    messages.success(request, f"Print tracking reset for {student.full_name}.")
    return redirect('student:student_detail', pk=pk)


@require_POST
def reset_all_student_prints(request):
    updated = Student.reset_all_print_tracking()
    messages.success(
        request,
        f"Print tracking reset for {updated} student record"
        f"{'s' if updated != 1 else ''}."
    )
    return redirect('student:student_list')


# ============================================================================
# PDF
# ============================================================================
def student_pdf(request, pk):
    student = get_object_or_404(Student, pk=pk)
    track = request.GET.get('track', '1') != '0'
    if track:
        student.mark_printed()
    safe_name = student.full_name.replace(' ', '_').replace('/', '_')
    return _render_pdf(
        'student/student_pdf.html',
        {'student': student, 'school': get_school(), 'single': True},
        f"{safe_name}_{student.admission_number}.pdf",
    )


def student_pdf_all(request):
    qs = (
        Student.objects
        .filter(status='active')
        .select_related('level', 'department')
        .order_by('full_name')
    )
    qs = _apply_print_filter(qs, request.GET.get('printed', ''))
    students = list(qs)

    track = request.GET.get('track', '1') != '0'
    if track and students:
        Student.mark_many_printed(students)
        for s in students:
            s.refresh_from_db(
                fields=['print_count', 'first_printed_at', 'last_printed_at']
            )

    return _render_pdf(
        'student/student_pdf.html',
        {'students': students, 'school': get_school(), 'print_all': True},
        "All_Student_ID_Cards.pdf",
    )

# ============================================================================
# QR CODE — encodes ALL student info + school info
# ============================================================================
import qrcode
from qrcode.image.svg import SvgPathImage


def student_qr_svg(request, admission_number):
    """
    Returns a QR code SVG encoding all of the student's information
    plus the school's contact details.

    The payload is a structured multi-line record:
        NAME: Sarah Elizabeth Chen
        LEVEL: JSS2
        HOUSE: Blue
        GENDER: Female
        DOB: 05/12/1988
        BLOOD GROUP: O+
        GUARDIAN: Sarah C.
        GUARDIAN PHONE: 555-0199
        STUDENT PHONE: 555-0188
        EMERGENCY: 555-0187
        VALID THRU: 06/2027
        --
        SCHOOL: Excel Junior Secondary School
        ADDRESS: 12 School Road, Lagos
        PHONE 1: +234 800 000 0000
        PHONE 2: +234 800 000 0001

    Any QR scanner app will display this as plain text — no server call
    needed, works offline, prints cleanly.
    """
    student = get_object_or_404(Student, admission_number=admission_number)
    school = get_school()

    # Build the payload line-by-line. Only include lines that have data,
    # so the QR stays compact.
    lines = []

    def add(label, value):
        if value:
            lines.append(f"{label}: {value}")

    # ---- Student info ----
    add("NAME", student.full_name)
    add("ADMISSION", student.admission_number)
    add("LEVEL", student.level_display if student.level else "")
    add("DEPARTMENT", student.department_display if student.department else "")
    add("GENDER", student.get_gender_display())
    if student.date_of_birth:
        add("DOB", student.date_of_birth.strftime("%d/%m/%Y"))
    add("BLOOD GROUP", student.blood_group)
    add("GUARDIAN", student.guardian_name)
    add("GUARDIAN PHONE", student.guardian_phone)
    add("STUDENT PHONE", student.phone)
    add("EMERGENCY", student.emergency_contact_phone)
    if student.valid_thru:
        add("VALID THRU", student.valid_thru.strftime("%m/%Y"))

    # ---- School info ----
    # Separator between the two blocks.
    if lines:
        lines.append("--")
    add("SCHOOL", school.name)
    add("ADDRESS", school.address)
    add("PHONE 1", school.contact_phone_1)
    add("PHONE 2", school.contact_phone_2)

    qr_data = "\n".join(lines)

    # Error correction M tolerates ~15% damage. Bump to Q (~25%) if you
    # want maximum resilience — but the code gets denser.
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=1,
    )
    qr.add_data(qr_data)
    qr.make(fit=True)

    img = qr.make_image(image_factory=SvgPathImage)
    buffer = io.BytesIO()
    img.save(buffer)
    buffer.seek(0)

    return HttpResponse(buffer.getvalue(), content_type='image/svg+xml')