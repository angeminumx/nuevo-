from django.contrib import admin
from .models import (
    AttendanceLog,
    Classroom,
    DailyReceptionSession,
    TeacherClassroomAccess,
    TeacherScanLog,
    StaffMessage,
    SMSOptIn,
    SMSMessageLog,
    MessageTemplate,
)


@admin.register(Classroom)
class ClassroomAdmin(admin.ModelAdmin):
    list_display = ("name",)


@admin.register(AttendanceLog)
class AttendanceLogAdmin(admin.ModelAdmin):
    list_display = ("student", "check_in_time", "check_out_time", "reason")
    search_fields = ("student__first_name", "student__last_name", "student__student_id")


@admin.register(DailyReceptionSession)
class DailyReceptionSessionAdmin(admin.ModelAdmin):
    list_display = ("session_date", "started_at", "ended_at", "is_active", "started_by")


@admin.register(TeacherClassroomAccess)
class TeacherClassroomAccessAdmin(admin.ModelAdmin):
    list_display = ("teacher", "classroom")


@admin.register(TeacherScanLog)
class TeacherScanLogAdmin(admin.ModelAdmin):
    list_display = ("student", "classroom", "period", "scan_date", "scanned_at", "scanned_by")
    search_fields = ("student__first_name", "student__last_name", "student__student_id")


@admin.register(StaffMessage)
class StaffMessageAdmin(admin.ModelAdmin):
    list_display = ("sender", "recipient_user", "recipient_role", "is_urgent", "created_at", "read_at")
    search_fields = ("sender__username", "recipient_user__username", "body")
    list_filter = ("recipient_role", "is_urgent", "created_at")


@admin.register(SMSOptIn)
class SMSOptInAdmin(admin.ModelAdmin):
    list_display = ("student", "phone_number", "opted_in", "is_active", "consent_timestamp")
    search_fields = ("student__first_name", "student__last_name", "student__student_id", "phone_number")
    list_filter = ("opted_in", "is_active")


@admin.register(SMSMessageLog)
class SMSMessageLogAdmin(admin.ModelAdmin):
    list_display = ("student", "phone_number", "message_type", "status", "sent_at", "created_at")
    search_fields = ("student__first_name", "student__last_name", "student__student_id", "phone_number", "message_body")
    list_filter = ("message_type", "status", "created_at")


@admin.register(MessageTemplate)
class MessageTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "message_type", "is_active", "updated_at")
    search_fields = ("name", "body_template")
    list_filter = ("message_type", "is_active")