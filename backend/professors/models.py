from django.db import models

# Create your models here.

class Department(models.Model):
    name = models.CharField(max_length=128, unique=True)
    code = models.CharField(max_length=16, blank=True)

    def __str__(self):
        return self.name


class Professor(models.Model):
    name = models.CharField(max_length=128)
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, related_name="professors")
    institution = models.CharField(max_length=128)

    def __str__(self):
        return self.name