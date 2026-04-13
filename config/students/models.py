from django.db import models


class Student(models.Model):
    student_id = models.CharField(max_length=30, unique=True)
    badge_number = models.PositiveIntegerField(unique=True, null=True, blank=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    grade = models.CharField(max_length=20, blank=True)
    homeroom = models.CharField(max_length=50, blank=True)
    active = models.BooleanField(default=True)
    photo = models.ImageField(upload_to="student_photos/", blank=True, null=True)
    directives = models.TextField(blank=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.student_id})"