from django.contrib import admin
from .models import ClockifyProfile

# Register your models here.

@admin.register(ClockifyProfile)
class ClockifyProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'clockify_key']
