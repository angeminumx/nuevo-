import csv

from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .models import (
    AttendanceLog,
    Classroom,
    DailyReceptionSession,
    TeacherClassroomAccess,
    TeacherScanLog,
    PERIOD_CHOICES,
)
from students.models import Student


QUOTES = [
    "Small steps every day build strong outcomes.",
    "Consistency creates calm.",
    "Every child deserves a strong start to the day.",
    "Careful systems create better care.",
    "A steady routine supports meaningful learning.",
    "The work you do today shapes tomorrow.",
    "Order in the environment supports confidence in the child.",
]


def is_receptionist(user):
    return user.is_authenticated and user.groups.filter(name="Receptionist").exists()


def is_teacher(user):
    return user.is_authenticated and user.groups.filter(name="Teacher").exists()


@login_required
def redirect_after_login(request):
    user = request.user

    if user.groups.filter(name="Receptionist").exists():
        return redirect("dashboard")

    if user.groups.filter(name="Teacher").exists():
        return redirect("teacher_home")

    if user.is_staff or user.is_superuser:
        return redirect("/admin/")

    return redirect("dashboard")


@login_required
@user_passes_test(is_receptionist)
def dashboard(request):
    id_query = request.GET.get("q", "").strip()
    name_query = request.GET.get("name_q", "").strip()

    matched_student = None
    student_is_checked_in = False
    open_log_for_student = None
    name_results = Student.objects.none()
    latest_scan = None

    if id_query:
        matched_student = Student.objects.filter(
            active=True,
            student_id__iexact=id_query
        ).first()

        if not matched_student and id_query.isdigit():
            matched_student = Student.objects.filter(
                active=True,
                badge_number=int(id_query)
            ).first()

        if matched_student:
            open_log_for_student = AttendanceLog.objects.filter(
                student=matched_student,
                check_out_time__isnull=True
            ).order_by("-check_in_time").first()

            latest_scan = TeacherScanLog.objects.select_related(
                "classroom", "scanned_by"
            ).filter(
                student=matched_student
            ).order_by("-scanned_at").first()

            student_is_checked_in = open_log_for_student is not None

    if name_query:
        name_results = Student.objects.filter(
            active=True
        ).filter(
            Q(first_name__icontains=name_query) |
            Q(last_name__icontains=name_query) |
            Q(student_id__icontains=name_query) |
            Q(homeroom__icontains=name_query)
        ).order_by("last_name", "first_name")

    open_logs = AttendanceLog.objects.select_related("student").filter(
        check_out_time__isnull=True
    ).order_by("-check_in_time")

    checked_in_student_ids = set(open_logs.values_list("student_id", flat=True))

    today = timezone.localdate()
    daily_session = DailyReceptionSession.objects.filter(session_date=today).first()
    quote_of_the_day = QUOTES[today.toordinal() % len(QUOTES)]

    context = {
        "id_query": id_query,
        "name_query": name_query,
        "matched_student": matched_student,
        "student_is_checked_in": student_is_checked_in,
        "open_log_for_student": open_log_for_student,
        "open_logs": open_logs,
        "name_results": name_results,
        "checked_in_student_ids": checked_in_student_ids,
        "latest_scan": latest_scan,
        "daily_session": daily_session,
        "quote_of_the_day": quote_of_the_day,
    }
    return render(request, "attendance/dashboard.html", context)


@login_required
@user_passes_test(is_receptionist)
def check_in(request, student_id):
    if request.method != "POST":
        return redirect("dashboard")

    student = get_object_or_404(Student, id=student_id)
    reason = request.POST.get("reason", "").strip()
    notes = request.POST.get("notes", "").strip()

    already_checked_in = AttendanceLog.objects.filter(
        student=student,
        check_out_time__isnull=True
    ).exists()

    if not already_checked_in:
        AttendanceLog.objects.create(
            student=student,
            reason=reason,
            notes=notes
        )

    return redirect("dashboard")


@login_required
@user_passes_test(is_receptionist)
def check_out(request, student_id):
    if request.method != "POST":
        return redirect("dashboard")

    student = get_object_or_404(Student, id=student_id)

    open_log = AttendanceLog.objects.filter(
        student=student,
        check_out_time__isnull=True
    ).order_by("-check_in_time").first()

    if open_log:
        open_log.check_out_time = timezone.now()
        checkout_note = request.POST.get("notes", "").strip()

        if checkout_note:
            if open_log.notes:
                open_log.notes += f"\nCheck-out note: {checkout_note}"
            else:
                open_log.notes = f"Check-out note: {checkout_note}"

        open_log.save()

    return redirect("dashboard")


@login_required
@user_passes_test(is_receptionist)
def start_day(request):
    if request.method == "POST":
        today = timezone.localdate()
        session, _ = DailyReceptionSession.objects.get_or_create(session_date=today)

        if not session.is_active:
            session.started_at = timezone.now()
            session.ended_at = None
            session.is_active = True
            session.started_by = request.user
            session.save()

    return redirect("dashboard")


@login_required
@user_passes_test(is_receptionist)
def end_day(request):
    if request.method != "POST":
        return redirect("dashboard")

    now = timezone.now()
    today = timezone.localdate()

    session = DailyReceptionSession.objects.filter(session_date=today).first()
    if session and session.is_active:
        session.ended_at = now
        session.is_active = False
        session.save()

    open_logs = AttendanceLog.objects.filter(
        check_in_time__date=today,
        check_out_time__isnull=True
    ).select_related("student")

    for log in open_logs:
        log.check_out_time = now

        existing_notes = log.notes.strip() if log.notes else ""
        auto_note = "Auto-checked out at end of day"

        if existing_notes:
            log.notes = f"{existing_notes} | {auto_note}"
        else:
            log.notes = auto_note

        log.save()

    logs = AttendanceLog.objects.filter(
        check_in_time__date=today
    ).select_related("student").order_by("check_in_time")

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="attendance_{today}.csv"'

    writer = csv.writer(response)
    writer.writerow([
        "Student ID",
        "First Name",
        "Last Name",
        "Check In Time",
        "Check Out Time",
        "Reason",
        "Notes",
    ])

    for log in logs:
        writer.writerow([
            log.student.student_id,
            log.student.first_name,
            log.student.last_name,
            log.check_in_time.strftime("%Y-%m-%d %I:%M %p") if log.check_in_time else "",
            log.check_out_time.strftime("%Y-%m-%d %I:%M %p") if log.check_out_time else "",
            log.reason or "",
            log.notes or "",
        ])

    return response


@login_required
@user_passes_test(is_teacher)
def teacher_home(request):
    assigned_access = TeacherClassroomAccess.objects.filter(
        teacher=request.user
    ).select_related("classroom").order_by("classroom__name")

    classrooms = [item.classroom for item in assigned_access]

    context = {
        "classrooms": classrooms,
    }
    return render(request, "attendance/teacher_home.html", context)


@login_required
@user_passes_test(is_teacher)
def teacher_classroom(request, classroom_id):
    classroom = get_object_or_404(Classroom, id=classroom_id)

    allowed = TeacherClassroomAccess.objects.filter(
        teacher=request.user,
        classroom=classroom
    ).exists()

    if not allowed:
        return redirect("teacher_home")

    selected_period = request.GET.get("period", "homeroom")
    valid_period_values = {value for value, _ in PERIOD_CHOICES}
    if selected_period not in valid_period_values:
        selected_period = "homeroom"

    today = timezone.localdate()

    scanned_logs = TeacherScanLog.objects.select_related("student").filter(
        classroom=classroom,
        scanned_by=request.user,
        period=selected_period,
        scan_date=today
    ).order_by("student__last_name", "student__first_name")

    scanned_students = [log.student for log in scanned_logs]

    context = {
        "classroom": classroom,
        "selected_period": selected_period,
        "periods": PERIOD_CHOICES,
        "students": scanned_students,
        "today": today,
    }
    return render(request, "attendance/teacher_classroom.html", context)


@login_required
@user_passes_test(is_teacher)
def teacher_scan(request, classroom_id):
    if request.method != "POST":
        return redirect("teacher_home")

    classroom = get_object_or_404(Classroom, id=classroom_id)

    allowed = TeacherClassroomAccess.objects.filter(
        teacher=request.user,
        classroom=classroom
    ).exists()

    if not allowed:
        return redirect("teacher_home")

    query = request.POST.get("query", "").strip()
    period = request.POST.get("period", "homeroom")

    valid_period_values = {value for value, _ in PERIOD_CHOICES}
    if period not in valid_period_values:
        period = "homeroom"

    if not query:
        return redirect(f"/teacher/classroom/{classroom.pk}/?period={period}")

    student = Student.objects.filter(
        active=True
    ).filter(
        Q(badge_number__iexact=query) |
        Q(student_id__iexact=query) |
        Q(first_name__icontains=query) |
        Q(last_name__icontains=query)
    ).order_by("last_name", "first_name").first()

    if not student:
        return redirect(f"/teacher/classroom/{classroom.pk}/?period={period}")

    receptionist_checkin = AttendanceLog.objects.filter(
        student=student,
        check_out_time__isnull=True
    ).exists()

    if receptionist_checkin:
        TeacherScanLog.objects.get_or_create(
            student=student,
            classroom=classroom,
            scanned_by=request.user,
            period=period,
            scan_date=timezone.localdate(),
        )

    return redirect(f"/teacher/classroom/{classroom.pk}/?period={period}")


@login_required
@user_passes_test(is_receptionist)
def history(request):
    logs = AttendanceLog.objects.select_related("student").order_by("-check_in_time")

    context = {
        "logs": logs,
    }
    return render(request, "attendance/history.html", context)