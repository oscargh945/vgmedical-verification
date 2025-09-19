from django.apps import AppConfig

class VerificationConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'vgmedical_verification.apps.verification'
    verbose_name = 'Verification Engine'

    def ready(self):
        # Import signals if needed
        pass
