from django.contrib import admin
from .models import (
    Classroom,
    TeacherClassroomAccess,
    AttendanceLog,
    TeacherScanLog,
    DailyReceptionSession,
)

admin.site.register(Classroom)
admin.site.register(TeacherClassroomAccess)
admin.site.register(AttendanceLog)
admin.site.register(TeacherScanLog)
admin.site.register(DailyReceptionSession)