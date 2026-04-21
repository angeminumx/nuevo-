from django.urls import path
from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("check-in/<int:student_id>/", views.check_in, name="check_in"),
    path("check-out/<int:student_id>/", views.check_out, name="check_out"),
    path("start-day/", views.start_day, name="start_day"),
    path("end-day/", views.end_day, name="end_day"),
    path("history/", views.history, name="history"),

    path("teacher/", views.teacher_home, name="teacher_home"),
    path("teacher/classroom/<int:classroom_id>/", views.teacher_classroom, name="teacher_classroom"),
    path("teacher/classroom/<int:classroom_id>/scan/", views.teacher_scan, name="teacher_scan"),

    path("redirect-after-login/", views.redirect_after_login, name="redirect_after_login"),

    path("messages/receptionist/", views.receptionist_messages, name="receptionist_messages"),
    path("messages/teacher/", views.teacher_messages, name="teacher_messages"),

    path("sms-optin/", views.receptionist_sms_optin, name="receptionist_sms_optin"),
]