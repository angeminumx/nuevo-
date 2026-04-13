from django.db import models
from django.contrib.auth.models import User
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