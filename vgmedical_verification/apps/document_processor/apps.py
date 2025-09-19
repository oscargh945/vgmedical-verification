from django.apps import AppConfig

class DocumentProcessorConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'vgmedical_verification.apps.document_processor'
    verbose_name = 'Document Processor'

    def ready(self):
        # Import signals if needed
        pass
