from django.db import models

# Create your models here.
class Professor(models.Model):
    name = models.CharField(max_length=128)
    department = models.CharField(max_length=128)
    institution = models.CharField(max_length=128)

    def __str__(self):
        return self.name