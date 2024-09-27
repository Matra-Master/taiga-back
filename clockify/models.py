from django.db import models
from taiga.users.models import User

# Create your models here.
class ClockifyProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    clockify_key = models.CharField(max_length=200, null=True, blank=True, default=None)

    def __str__(self):
        return f"{self.user.name}'s Clockify Profile"
