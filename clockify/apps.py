from django.apps import AppConfig


class ClockifyConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'clockify'

    def ready(self):
        import clockify.signals
