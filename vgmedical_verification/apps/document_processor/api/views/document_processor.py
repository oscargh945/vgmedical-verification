import json
from typing import Dict

from rest_framework import status
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import MultiPartParser, JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from vgmedical_verification.apps.document_processor.api.serializers.document_processor import CaseIngestSerializer, \
    EquivalenceCreateSerializer
from vgmedical_verification.apps.document_processor.services.services import (
    process_surgical_case_files,
    generate_case_report,
    suggest_supply_equivalences,
    EquivalenceManager,
    DocumentProcessingError,
)


@api_view(['POST'])
@parser_classes([MultiPartParser, JSONParser])
@permission_classes([IsAuthenticated])
def ingest_case_view(request):
    """
    Ingesta los 3 documentos (interno, hospital, descripción) y procesa el caso completo.
    Request (multipart/form-data):
      - internal: file
      - hospital: file
      - description: file
      - case_data: (JSON) opcional con campos básicos
    """
    serializer = CaseIngestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    v = serializer.validated_data

    files_dict: Dict = {
        'internal': v['internal'],
        'hospital': v['hospital'],
        'description': v['description'],
    }

    # `case_data` puede venir como dict (JSONField) o como string JSON
    case_data = v.get('case_data')
    if isinstance(case_data, str):
        try:
            case_data = json.loads(case_data)
        except Exception:
            case_data = None
    if isinstance(case_data, dict):
        files_dict['case_data'] = case_data

    try:
        case = process_surgical_case_files(files_dict, request.user)
    except DocumentProcessingError as e:
        return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    return Response({
        'case_id': str(case.id),
        'case_number': case.case_number,
        'status': 'processed'
    }, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def case_report_view(request, case_id: str):
    """
    Retorna el reporte completo de verificación de un caso.
    """
    report = generate_case_report(case_id)
    if report.get('error'):
        return Response(report, status=status.HTTP_404_NOT_FOUND)
    return Response(report, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_equivalence_view(request):
    """
    Crea o actualiza una equivalencia de insumos (mecanismo de aprendizaje).
    Body (JSON):
      - canonical_name: str
      - aliases: [str, ...]
    """
    serializer = EquivalenceCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    v = serializer.validated_data

    manager = EquivalenceManager()
    eq = manager.add_equivalence(
        canonical_name=v['canonical_name'],
        aliases=v['aliases'],
        user=request.user,
        is_auto=False
    )
    return Response({
        'id': str(eq.id),
        'canonical_name': eq.canonical_name,
        'aliases': eq.aliases,
        'confidence_score': eq.confidence_score
    }, status=status.HTTP_201_CREATED)


# Opcional: sugerencias automáticas de equivalencias con base al caso ya cargado
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def suggest_equivalences_view(request, case_id: str):
    """
    Retorna una lista de sugerencias de equivalencias a partir de los insumos del caso.
    """
    suggestions = suggest_supply_equivalences(case_id)
    if isinstance(suggestions, dict) and suggestions.get('error'):
        return Response(suggestions, status=status.HTTP_404_NOT_FOUND)
    return Response({'suggestions': suggestions}, status=status.HTTP_200_OK)
