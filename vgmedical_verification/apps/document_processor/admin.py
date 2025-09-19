from django.contrib import admin
from django.utils.html import format_html
from .models import (
    SurgicalCase, Document, Supply, SupplyEquivalence, VerificationResult
)


@admin.register(SurgicalCase)
class SurgicalCaseAdmin(admin.ModelAdmin):
    list_display = [
        'case_number', 'patient_name', 'surgery_date',
        'doctor_name', 'verification_status', 'created'
    ]
    list_filter = ['surgery_date', 'city', 'created']
    search_fields = ['case_number', 'patient_name', 'patient_id', 'doctor_name']
    readonly_fields = ['case_number', 'created', 'modified']

    def verification_status(self, obj):
        try:
            verification = obj.verification
            if verification.verification_score >= 85:
                color = 'green'
                status = '✅ APROBADO'
            elif verification.requires_review:
                color = 'orange'
                status = '⚠️ REVISIÓN'
            else:
                color = 'red'
                status = '❌ RECHAZADO'

            return format_html(
                '<span style="color: {};">{}</span>',
                color, status
            )
        except:
            return format_html('<span style="color: gray;">Sin verificar</span>')

    verification_status.short_description = 'Estado Verificación'


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = [
        'surgical_case', 'document_type', 'status',
        'supplies_count', 'processed_at'
    ]
    list_filter = ['document_type', 'status', 'processed_at']
    readonly_fields = [
        'extracted_text', 'processed_at', 'processing_error',
        'created', 'modified'
    ]

    def supplies_count(self, obj):
        return obj.supplies.count()

    supplies_count.short_description = 'Insumos'


@admin.register(Supply)
class SupplyAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'quantity', 'document_type', 'ref_code',
        'lot_code', 'udi_label_present'
    ]
    list_filter = ['document__document_type', 'udi_label_present']
    search_fields = ['name', 'ref_code', 'lot_code']

    def document_type(self, obj):
        return obj.document.get_document_type_display()

    document_type.short_description = 'Tipo Documento'


@admin.register(SupplyEquivalence)
class SupplyEquivalenceAdmin(admin.ModelAdmin):
    list_display = [
        'canonical_name', 'aliases_count', 'confidence_score',
        'times_used', 'is_auto_generated'
    ]
    list_filter = ['is_auto_generated', 'confidence_score']
    search_fields = ['canonical_name', 'aliases']
    readonly_fields = ['times_used', 'last_used', 'created', 'modified']

    def aliases_count(self, obj):
        return len(obj.aliases)

    aliases_count.short_description = 'Sinónimos'


@admin.register(VerificationResult)
class VerificationResultAdmin(admin.ModelAdmin):
    list_display = [
        'surgical_case', 'verification_score', 'overall_status',
        'basic_data_match', 'supplies_match', 'traceability_complete',
        'processing_time'
    ]
    list_filter = [
        'basic_data_match', 'supplies_match', 'traceability_complete',
        'requires_review'
    ]
    readonly_fields = [
        'basic_data_details', 'supplies_details', 'traceability_details',
        'discrepancies', 'processed_at', 'processing_time'
    ]

    def overall_status(self, obj):
        status = obj.overall_status
        color_map = {
            'APROBADO': 'green',
            'REQUIERE_REVISION': 'orange',
            'RECHAZADO': 'red'
        }

        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color_map.get(status, 'gray'), status
        )

    overall_status.short_description = 'Estado General'
