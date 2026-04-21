from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from students.models import Student


PERIOD_CHOICES = [
    ("homeroom", "Homeroom"),
    ("period_1", "Period 1"),
    ("period_2", "Period 2"),
    ("period_3", "Period 3"),
    ("period_4_lunch_nap", "Period 4 / Lunch / Nap"),
    ("period_5", "Period 5"),
    ("period_6", "Period 6"),
    ("period_7", "Period 7"),
    ("end_of_day", "End of Day"),
]


class Classroom(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name


class TeacherClassroomAccess(models.Model):
    teacher = models.ForeignKey(User, on_delete=models.CASCADE)
    classroom = models.ForeignKey(Classroom, on_delete=models.CASCADE)

    class Meta:
        unique_together = ("teacher", "classroom")

    def __str__(self):
        return f"{self.teacher.username} -> {self.classroom.name}"


class AttendanceLog(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    check_in_time = models.DateTimeField(auto_now_add=True)
    check_out_time = models.DateTimeField(null=True, blank=True)
    reason = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)

    @property
    def is_checked_in(self):
        return self.check_out_time is None

    def __str__(self):
        status = "IN" if self.is_checked_in else "OUT"
        return f"{self.student} - {status}"


class TeacherScanLog(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    classroom = models.ForeignKey(Classroom, on_delete=models.CASCADE)
    scanned_by = models.ForeignKey(User, on_delete=models.CASCADE)

    period = models.CharField(max_length=30, choices=PERIOD_CHOICES)
    scan_date = models.DateField(auto_now_add=True)
    scanned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("student", "classroom", "period", "scan_date")
        ordering = ["-scan_date", "-scanned_at"]

    def __str__(self):
        period_label = dict(PERIOD_CHOICES).get(self.period, self.period)
        return f"{self.student} - {self.classroom.name} - {period_label} - {self.scan_date}"


class DailyReceptionSession(models.Model):
    session_date = models.DateField(unique=True)
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=False)
    started_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="started_reception_sessions",
    )

    def __str__(self):
        status = "Active" if self.is_active else "Closed"
        return f"{self.session_date} - {status}"


class StaffMessage(models.Model):
    ROLE_CHOICES = [
        ("receptionist", "Receptionist"),
        ("teacher", "Teacher"),
    ]

    sender = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="sent_staff_messages"
    )
    recipient_user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="received_staff_messages",
        null=True,
        blank=True
    )
    recipient_role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        null=True,
        blank=True
    )
    classroom = models.ForeignKey(
        Classroom,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    student = models.ForeignKey(
        Student,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    body = models.TextField()
    is_urgent = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        target = self.recipient_user.username if self.recipient_user else self.recipient_role
        return f"From {self.sender.username} to {target}"

    @property
    def is_read(self):
        return self.read_at is not None


class SMSOptIn(models.Model):
    student = models.OneToOneField(
        Student,
        on_delete=models.CASCADE,
        related_name="sms_opt_in"
    )
    phone_number = models.CharField(max_length=20)
    opted_in = models.BooleanField(default=False)
    consent_timestamp = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        status = "Opted In" if self.opted_in else "Not Opted In"
        return f"{self.student} - {self.phone_number} ({status})"


class SMSMessageLog(models.Model):
    MESSAGE_TYPE_CHOICES = [
        ("manual", "Manual"),
        ("morning", "Morning Greeting"),
        ("midday", "Lunch/Nap"),
        ("pickup", "Pickup Reminder"),
    ]

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("sent", "Sent"),
        ("failed", "Failed"),
    ]

    student = models.ForeignKey(
        Student,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    phone_number = models.CharField(max_length=20)
    message_type = models.CharField(max_length=20, choices=MESSAGE_TYPE_CHOICES)
    message_body = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    sent_at = models.DateTimeField(null=True, blank=True)
    provider_message_id = models.CharField(max_length=100, blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.phone_number} - {self.message_type} - {self.status}"


class MessageTemplate(models.Model):
    MESSAGE_TYPE_CHOICES = [
        ("morning", "Morning Greeting"),
        ("midday", "Lunch/Nap"),
        ("pickup", "Pickup Reminder"),
    ]

    name = models.CharField(max_length=100)
    message_type = models.CharField(max_length=20, choices=MESSAGE_TYPE_CHOICES, unique=True)
    body_template = models.TextField(
        help_text='Use placeholders like {student_name}, {first_name}, {last_name}, {quote}.'
    )
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.message_type})"