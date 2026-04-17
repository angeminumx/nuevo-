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

    # Parent / guardian 1
    parent1_name = models.CharField(max_length=100 , blank=True, null=True)
    parent1_email = models.EmailField(blank=True, null=False)
    parent1_phone = models.CharField(max_length=20, blank=True, null=True)
    parent1_sms_opt_in = models.BooleanField(default=False)


      # Parent / guardian 2
    parent2_name = models.CharField(max_length=100 , blank=True, null=True)
    parent2_email = models.EmailField(blank=True, null=False)
    parent2_phone = models.CharField(max_length=20, blank=True, null=True)
    parent2_sms_opt_in = models.BooleanField(default=False)

    #Medical / Health notes 
    medical_notes = models.TextField(blank=True, null=True)
    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.student_id})"