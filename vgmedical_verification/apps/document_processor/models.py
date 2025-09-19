from django.db import models
from django.contrib.auth import get_user_model

from vgmedical_verification.utils.models import BaseModel

User = get_user_model()


class DocumentType(models.TextChoices):
    INTERNAL = 'internal', 'Reporte Interno'
    HOSPITAL = 'hospital', 'Reporte Hospital'
    DESCRIPTION = 'description', 'Descripción Quirúrgica'


class DocumentStatus(models.TextChoices):
    UPLOADED = 'uploaded', 'Subido'
    PROCESSING = 'processing', 'Procesando'
    PROCESSED = 'processed', 'Procesado'
    ERROR = 'error', 'Error'


class SurgicalCase(BaseModel):
    """Caso quirúrgico principal que agrupa los 3 documentos"""
    case_number = models.CharField(max_length=100, unique=True)
    patient_name = models.CharField(max_length=255)
    patient_id = models.CharField(max_length=100)
    surgery_date = models.DateField()
    city = models.CharField(max_length=100)
    doctor_name = models.CharField(max_length=255)
    procedure = models.TextField()

    class Meta:
        ordering = ['-created']

    def __str__(self):
        return f"Caso {self.case_number} - {self.patient_name}"


class Document(BaseModel):
    """Documento individual (interno, hospital, o descripción)"""
    surgical_case = models.ForeignKey(SurgicalCase, on_delete=models.CASCADE, related_name='documents')
    document_type = models.CharField(max_length=20, choices=DocumentType.choices)
    file = models.FileField(upload_to='documents/')
    status = models.CharField(max_length=20, choices=DocumentStatus.choices, default=DocumentStatus.UPLOADED)

    # Texto extraído
    extracted_text = models.TextField(blank=True)

    # Datos básicos extraídos
    extracted_patient_name = models.CharField(max_length=255, blank=True)
    extracted_patient_id = models.CharField(max_length=100, blank=True)
    extracted_date = models.DateField(null=True, blank=True)
    extracted_city = models.CharField(max_length=100, blank=True)
    extracted_doctor = models.CharField(max_length=255, blank=True)
    extracted_procedure = models.TextField(blank=True)

    processed_at = models.DateTimeField(null=True, blank=True)
    processing_error = models.TextField(blank=True)

    class Meta:
        unique_together = ['surgical_case', 'document_type']

    def __str__(self):
        return f"{self.get_document_type_display()} - {self.surgical_case.case_number}"


class Supply(BaseModel):
    """Insumo médico detectado en un documento"""
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='supplies')

    # Datos del insumo
    name = models.CharField(max_length=500)  # Nombre como aparece en el documento
    normalized_name = models.CharField(max_length=500, blank=True)  # Nombre normalizado
    quantity = models.IntegerField()

    # Para reporte interno - trazabilidad
    ref_code = models.CharField(max_length=100, blank=True)  # REF
    lot_code = models.CharField(max_length=100, blank=True)  # LOT
    udi_label_present = models.BooleanField(default=False)  # Si tiene etiqueta UDI pegada

    # Posición en el texto (para debugging)
    line_number = models.IntegerField(null=True, blank=True)
    confidence = models.FloatField(default=0.0)  # Confianza del OCR/extracción

    def __str__(self):
        return f"{self.name} (x{self.quantity})"


class SupplyEquivalence(BaseModel):
    """Base de conocimiento de equivalencias entre nombres de insumos"""
    canonical_name = models.CharField(max_length=500, unique=True)  # Nombre canónico
    aliases = models.JSONField(default=list)  # Lista de sinónimos/variantes

    # Metadatos de aprendizaje
    confidence_score = models.FloatField(default=1.0)
    times_used = models.IntegerField(default=0)
    last_used = models.DateTimeField(auto_now=True)

    # Creación automática vs manual
    is_auto_generated = models.BooleanField(default=False)
    validated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return self.canonical_name

    def add_alias(self, alias):
        """Añade un nuevo sinónimo si no existe"""
        if alias.lower() not in [a.lower() for a in self.aliases]:
            self.aliases.append(alias)
            self.save()


class VerificationResult(BaseModel):
    """Resultado de la verificación de un caso quirúrgico"""
    surgical_case = models.OneToOneField(SurgicalCase, on_delete=models.CASCADE, related_name='verification')

    # Resultados generales
    basic_data_match = models.BooleanField(default=False)
    supplies_match = models.BooleanField(default=False)
    traceability_complete = models.BooleanField(default=False)
    requires_review = models.BooleanField(default=True)

    # Detalles de verificación (JSON)
    basic_data_details = models.JSONField(default=dict)
    supplies_details = models.JSONField(default=dict)
    traceability_details = models.JSONField(default=dict)
    discrepancies = models.JSONField(default=list)

    # Metadatos
    verification_score = models.FloatField(default=0.0)
    processed_at = models.DateTimeField(auto_now_add=True)
    processing_time = models.FloatField(default=0.0)

    # Feedback del analista (para aprendizaje)
    analyst_feedback = models.JSONField(default=dict, blank=True)
    feedback_date = models.DateTimeField(null=True, blank=True)
    feedback_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"Verificación {self.surgical_case.case_number}"

    @property
    def overall_status(self):
        if self.basic_data_match and self.supplies_match and self.traceability_complete:
            return "APROBADO"
        elif self.requires_review:
            return "REQUIERE_REVISION"
        else:
            return "RECHAZADO"
