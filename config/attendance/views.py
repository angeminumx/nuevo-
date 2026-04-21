import csv
import datetime
from pathlib import Path

from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import IntegrityError
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.contrib.auth.models import User
from django.conf import settings
from twilio.rest import Client

from .models import (
    AttendanceLog,
    Classroom,
    DailyReceptionSession,
    TeacherClassroomAccess,
    TeacherScanLog,
    PERIOD_CHOICES,
    StaffMessage,
    SMSOptIn,
    SMSMessageLog,
    MessageTemplate,
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


def format_local_dt(dt):
    if not dt:
        return ""
    local_dt = timezone.localtime(dt)
    hour_12 = local_dt.hour % 12 or 12
    am_pm = "AM" if local_dt.hour < 12 else "PM"
    return f"{local_dt.month}/{local_dt.day}/{local_dt.year} {hour_12}:{local_dt.minute:02d} {am_pm}"


def get_reports_dir():
    return Path(__file__).resolve().parent.parent / "daily_reports"


def is_receptionist(user):
    return user.is_authenticated and user.groups.filter(name="Receptionist").exists()


def is_teacher(user):
    return user.is_authenticated and user.groups.filter(name="Teacher").exists()


def render_sms_template(template_obj, student):
    today = datetime.date.today()
    quote = QUOTES[today.toordinal() % len(QUOTES)]

    first_name = student.first_name or ""
    last_name = student.last_name or ""
    student_name = f"{first_name} {last_name}".strip()

    return template_obj.body_template.format(
        student_name=student_name,
        first_name=first_name,
        last_name=last_name,
        quote=quote,
    )


def send_sms_message(phone_number, body):
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN or not settings.TWILIO_PHONE_NUMBER:
        return {
            "success": False,
            "provider_message_id": "",
            "error": "Twilio credentials are missing.",
        }

    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        message = client.messages.create(
            body=body,
            from_=settings.TWILIO_PHONE_NUMBER,
            to=phone_number,
        )
        return {
            "success": True,
            "provider_message_id": message.sid,
            "error": "",
        }
    except Exception as e:
        return {
            "success": False,
            "provider_message_id": "",
            "error": str(e),
        }


def send_morning_checkin_sms(student):
    sms_optin = SMSOptIn.objects.filter(
        student=student,
        opted_in=True,
        is_active=True
    ).first()

    if not sms_optin or not sms_optin.phone_number:
        return

    today = datetime.date.today()

    already_sent = SMSMessageLog.objects.filter(
        student=student,
        message_type="morning",
        created_at__date=today,
        status="sent",
    ).exists()

    if already_sent:
        return

    template_obj = MessageTemplate.objects.filter(
        message_type="morning",
        is_active=True
    ).first()

    if not template_obj:
        return

    message_body = render_sms_template(template_obj, student)

    log = SMSMessageLog.objects.create(
        student=student,
        phone_number=sms_optin.phone_number,
        message_type="morning",
        message_body=message_body,
        status="pending",
    )

    result = send_sms_message(sms_optin.phone_number, message_body)

    if result.get("success"):
        log.status = "sent"
        log.sent_at = timezone.now()
        log.provider_message_id = result.get("provider_message_id", "")
        log.error_message = ""
    else:
        log.status = "failed"
        log.error_message = result.get("error", "Unknown SMS error")

    log.save()


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

        for student in name_results:
            student.latest_scan = TeacherScanLog.objects.select_related(
                "classroom", "scanned_by"
            ).filter(
                student=student
            ).order_by("-scanned_at").first()

    open_logs = AttendanceLog.objects.select_related("student").filter(
        check_out_time__isnull=True
    ).order_by("-check_in_time")

    checked_in_student_ids = set(open_logs.values_list("student_id", flat=True))

    today = datetime.date.today()
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
        send_morning_checkin_sms(student)

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
        today = datetime.date.today()
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
    today = datetime.date.today()

    session = DailyReceptionSession.objects.filter(session_date=today).first()
    if not session:
        return redirect("dashboard")

    if session.is_active:
        session.ended_at = now
        session.is_active = False
        session.save()

    session_start = session.started_at
    session_end = session.ended_at or now

    if not session_start:
        return redirect("dashboard")

    open_logs = AttendanceLog.objects.filter(
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

    receptionist_logs = AttendanceLog.objects.filter(
        check_in_time__gte=session_start,
        check_in_time__lte=session_end,
    ).select_related("student").order_by("check_in_time")

    teacher_logs = TeacherScanLog.objects.select_related(
        "student", "classroom", "scanned_by"
    ).filter(
        scanned_at__gte=session_start,
        scanned_at__lte=session_end,
    ).order_by("scanned_at")

    reports_dir = get_reports_dir()
    reports_dir.mkdir(parents=True, exist_ok=True)

    receptionist_csv_path = reports_dir / f"reception_attendance_{today}.csv"
    teacher_csv_path = reports_dir / f"classroom_scans_{today}.csv"

    with open(receptionist_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Student ID",
            "First Name",
            "Last Name",
            "Check In Time",
            "Check Out Time",
            "Reason",
            "Notes",
        ])

        for log in receptionist_logs:
            writer.writerow([
                log.student.student_id,
                log.student.first_name,
                log.student.last_name,
                format_local_dt(log.check_in_time),
                format_local_dt(log.check_out_time),
                log.reason or "",
                log.notes or "",
            ])

    with open(teacher_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Student ID",
            "First Name",
            "Last Name",
            "Classroom",
            "Period",
            "Scanned At",
            "Scanned By",
        ])

        for log in teacher_logs:
            writer.writerow([
                log.student.student_id,
                log.student.first_name,
                log.student.last_name,
                log.classroom.name if log.classroom else "",
                log.get_period_display() if hasattr(log, "get_period_display") else log.period,
                format_local_dt(log.scanned_at),
                log.scanned_by.username if log.scanned_by else "",
            ])

    TeacherScanLog.objects.filter(scan_date=today).delete()

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="reception_attendance_{today}.csv"'

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

    for log in receptionist_logs:
        writer.writerow([
            log.student.student_id,
            log.student.first_name,
            log.student.last_name,
            format_local_dt(log.check_in_time),
            format_local_dt(log.check_out_time),
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

    today = datetime.date.today()

    scanned_logs = TeacherScanLog.objects.select_related("student").filter(
        classroom=classroom,
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
    period = request.POST.get("period", "homeroom").strip()

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

    if not receptionist_checkin:
        return redirect(f"/teacher/classroom/{classroom.pk}/?period={period}")

    today = datetime.date.today()

    try:
        TeacherScanLog.objects.create(
            student=student,
            classroom=classroom,
            scanned_by=request.user,
            period=period,
            scan_date=today,
        )
    except IntegrityError:
        pass

    return redirect(f"/teacher/classroom/{classroom.pk}/?period={period}")


@login_required
@user_passes_test(is_receptionist)
def receptionist_messages(request):
    teacher_users = User.objects.filter(groups__name="Teacher").distinct().order_by("username")

    if request.method == "POST":
        recipient_id = request.POST.get("recipient_user")
        body = request.POST.get("body", "").strip()
        is_urgent = request.POST.get("is_urgent") == "on"

        if recipient_id and body:
            recipient = get_object_or_404(User, id=recipient_id)
            StaffMessage.objects.create(
                sender=request.user,
                recipient_user=recipient,
                recipient_role="teacher",
                body=body,
                is_urgent=is_urgent,
            )
        return redirect("receptionist_messages")

    inbox_messages = StaffMessage.objects.select_related(
        "sender", "recipient_user", "classroom", "student"
    ).filter(
        Q(recipient_user=request.user) | Q(recipient_role="receptionist")
    ).order_by("-created_at")

    unread_messages = inbox_messages.filter(read_at__isnull=True)
    unread_messages.update(read_at=timezone.now())

    sent_messages = StaffMessage.objects.select_related(
        "recipient_user"
    ).filter(
        sender=request.user
    ).order_by("-created_at")[:20]

    context = {
        "teacher_users": teacher_users,
        "inbox_messages": inbox_messages,
        "sent_messages": sent_messages,
    }
    return render(request, "attendance/receptionist_messages.html", context)


@login_required
@user_passes_test(is_teacher)
def teacher_messages(request):
    receptionist_users = User.objects.filter(groups__name="Receptionist").distinct().order_by("username")

    if request.method == "POST":
        recipient_id = request.POST.get("recipient_user")
        body = request.POST.get("body", "").strip()
        is_urgent = request.POST.get("is_urgent") == "on"

        if recipient_id and body:
            recipient = get_object_or_404(User, id=recipient_id)
            StaffMessage.objects.create(
                sender=request.user,
                recipient_user=recipient,
                recipient_role="receptionist",
                body=body,
                is_urgent=is_urgent,
            )
        return redirect("teacher_messages")

    inbox_messages = StaffMessage.objects.select_related(
        "sender", "recipient_user", "classroom", "student"
    ).filter(
        recipient_user=request.user
    ).order_by("-created_at")

    unread_messages = inbox_messages.filter(read_at__isnull=True)
    unread_messages.update(read_at=timezone.now())

    sent_messages = StaffMessage.objects.select_related(
        "recipient_user"
    ).filter(
        sender=request.user
    ).order_by("-created_at")[:20]

    context = {
        "receptionist_users": receptionist_users,
        "inbox_messages": inbox_messages,
        "sent_messages": sent_messages,
    }
    return render(request, "attendance/teacher_messages.html", context)


@login_required
@user_passes_test(is_receptionist)
def receptionist_sms_optin(request):
    query = request.GET.get("q", "").strip()
    matched_student = None
    sms_record = None
    recent_sms_logs = []
    today_morning_log = None
    active_templates = []

    if query:
        matched_student = Student.objects.filter(
            active=True
        ).filter(
            Q(student_id__iexact=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(badge_number__iexact=query)
        ).order_by("last_name", "first_name").first()

        if matched_student:
            sms_record = SMSOptIn.objects.filter(student=matched_student).first()

            recent_sms_logs = SMSMessageLog.objects.filter(
                student=matched_student
            ).order_by("-created_at")[:10]

            today_morning_log = SMSMessageLog.objects.filter(
                student=matched_student,
                message_type="morning",
                created_at__date=datetime.date.today()
            ).order_by("-created_at").first()

    if request.method == "POST":
        student_id = request.POST.get("student_id")
        phone_number = request.POST.get("phone_number", "").strip()
        opted_in = request.POST.get("opted_in") == "on"
        is_active = request.POST.get("is_active") == "on"
        notes = request.POST.get("notes", "").strip()

        student = get_object_or_404(Student, id=student_id)

        sms_record, created = SMSOptIn.objects.get_or_create(
            student=student,
            defaults={
                "phone_number": phone_number,
                "opted_in": opted_in,
                "is_active": is_active,
                "notes": notes,
                "consent_timestamp": timezone.now() if opted_in else None,
            }
        )

        if not created:
            sms_record.phone_number = phone_number
            sms_record.opted_in = opted_in
            sms_record.is_active = is_active
            sms_record.notes = notes
            if opted_in and sms_record.consent_timestamp is None:
                sms_record.consent_timestamp = timezone.now()
            if not opted_in:
                sms_record.consent_timestamp = None
            sms_record.save()

        return redirect(f"/sms-optin/?q={student.student_id}")

    active_templates = MessageTemplate.objects.filter(
        is_active=True
    ).order_by("message_type")

    context = {
        "query": query,
        "matched_student": matched_student,
        "sms_record": sms_record,
        "recent_sms_logs": recent_sms_logs,
        "today_morning_log": today_morning_log,
        "active_templates": active_templates,
    }
    return render(request, "attendance/receptionist_sms_optin.html", context)


@login_required
@user_passes_test(is_receptionist)
def history(request):
    logs = AttendanceLog.objects.select_related("student").order_by("-check_in_time")

    context = {
        "logs": logs,
    }
    return render(request, "attendance/history.html", context)