from django.contrib.auth import get_user_model
from rest_framework import serializers

User = get_user_model()


class CaseDataSerializer(serializers.Serializer):
    patient_name = serializers.CharField(required=False, allow_blank=True)
    patient_id = serializers.CharField(required=False, allow_blank=True)
    surgery_date = serializers.DateField(required=False)
    city = serializers.CharField(required=False, allow_blank=True)
    doctor_name = serializers.CharField(required=False, allow_blank=True)
    procedure = serializers.CharField(required=False, allow_blank=True)

class CaseIngestSerializer(serializers.Serializer):
    internal = serializers.FileField()
    hospital = serializers.FileField()
    description = serializers.FileField()
    # case_data puede venir como JSON embebido en multipart
    case_data = serializers.JSONField(required=False)

    def validate(self, attrs):
        # Validación simple de tamaños/MIME opcional (placeholder)
        # Ejemplo: limitar a 10MB por archivo
        max_size = 10 * 1024 * 1024
        for key in ('internal', 'hospital', 'description'):
            f = attrs.get(key)
            if not f:
                raise serializers.ValidationError({key: "Archivo requerido"})
            if getattr(f, 'size', 0) > max_size:
                raise serializers.ValidationError({key: "Archivo supera 10MB"})
        return attrs

class EquivalenceCreateSerializer(serializers.Serializer):
    canonical_name = serializers.CharField()
    aliases = serializers.ListField(child=serializers.CharField(), allow_empty=False)
