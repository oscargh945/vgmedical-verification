import re
import unicodedata
import logging
from typing import Dict, List, Optional
from rapidfuzz import fuzz
from django.db import transaction
from django.utils import timezone

from vgmedical_verification.apps.document_processor.models import (
    SurgicalCase, Document, Supply, DocumentType, DocumentStatus, \
    SupplyEquivalence
)
from vgmedical_verification.apps.document_processor.parsers import DocumentParserFactory
from vgmedical_verification.apps.verification.engine import VerificationEngine, SupplyMatcher

logger = logging.getLogger(__name__)


class DocumentProcessingError(Exception):
    """Excepción para errores de procesamiento de documentos"""
    pass


class DocumentProcessor:
    """Servicio principal para procesamiento de documentos"""

    def __init__(self):
        self.verification_engine = VerificationEngine()

    def process_surgical_case(self, files_data: List[Dict], user) -> SurgicalCase:
        """
        Procesa un caso quirúrgico completo con sus 3 documentos

        Args:
            files_data: Lista con datos de archivos [
                {
                    'file': file_object,
                    'document_type': 'internal'|'hospital'|'description',
                    'case_data': {...}  # Datos adicionales del caso
                }
            ]
            user: Usuario que sube los documentos

        Returns:
            SurgicalCase procesado con verificación completa
        """

        if len(files_data) != 3:
            raise DocumentProcessingError(
                f"Se requieren exactamente 3 documentos, se recibieron {len(files_data)}"
            )

        # Verificar que tenemos los 3 tipos requeridos
        doc_types = {item['document_type'] for item in files_data}
        required_types = {DocumentType.INTERNAL, DocumentType.HOSPITAL, DocumentType.DESCRIPTION}

        if doc_types != required_types:
            missing = required_types - doc_types
            raise DocumentProcessingError(
                f"Faltan tipos de documento: {', '.join(missing)}"
            )

        try:
            with transaction.atomic():
                # 1. Crear caso quirúrgico
                case = self._create_surgical_case(files_data, user)

                # 2. Procesar cada documento
                for file_data in files_data:
                    self._process_document(case, file_data)

                # 3. Ejecutar verificación completa
                verification_result = self.verification_engine.verify_case(case)

                logger.info(
                    f"Caso {case.case_number} procesado exitosamente. "
                    f"Score: {verification_result.verification_score}"
                )

                return case

        except Exception as e:
            logger.error(f"Error procesando caso quirúrgico: {str(e)}")
            raise DocumentProcessingError(f"Error procesando caso: {str(e)}")

    def _create_surgical_case(self, files_data: List[Dict], user) -> SurgicalCase:
        """Crea el caso quirúrgico principal"""

        # Usar datos del primer archivo para crear el caso
        # (luego se actualizará con datos más precisos del parsing)
        base_data = files_data[0].get('case_data', {})

        case_number = self._generate_case_number()

        case = SurgicalCase.objects.create(
            case_number=case_number,
            patient_name=base_data.get('patient_name', 'Por definir'),
            patient_id=base_data.get('patient_id', ''),
            surgery_date=base_data.get('surgery_date', timezone.now().date()),
            city=base_data.get('city', ''),
            doctor_name=base_data.get('doctor_name', ''),
            procedure=base_data.get('procedure', '')
        )

        return case

    def _generate_case_number(self) -> str:
        """Genera un número único para el caso"""
        from datetime import datetime
        import uuid

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        short_uuid = str(uuid.uuid4())[:8]
        return f"VG_{timestamp}_{short_uuid}"

    def _process_document(self, case: SurgicalCase, file_data: Dict) -> Document:
        """Procesa un documento individual
        (parsea antes de guardar para evitar issues con el stream)
        """

        file_obj = file_data['file']
        doc_type = file_data['document_type']

        # 1) Parsear PRIMERO (y asegurar puntero al inicio)
        try:
            if hasattr(file_obj, "seek"):
                file_obj.seek(0)

            parser = DocumentParserFactory.get_parser(doc_type)
            extracted_data = parser.parse_file(file_obj)

            # 2) Rewind otra vez antes de asignar al FileField
            if hasattr(file_obj, "seek"):
                file_obj.seek(0)
        except Exception as e:
            raise DocumentProcessingError(f"Error procesando documento {doc_type}: {str(e)}")

        # 3) Crear documento y persistir
        document = Document.objects.create(
            surgical_case=case,
            document_type=doc_type,
            file=file_obj,
            status=DocumentStatus.PROCESSING
        )

        try:
            # Actualizar documento con datos extraídos
            document.extracted_text = extracted_data.get('raw_text', '')
            document.extracted_patient_name = extracted_data.get('patient_name', '')
            document.extracted_patient_id = extracted_data.get('patient_id', '')
            document.extracted_date = self._parse_date(extracted_data.get('date'))
            document.extracted_city = extracted_data.get('city', '')
            document.extracted_doctor = extracted_data.get('doctor', '')
            document.extracted_procedure = extracted_data.get('procedure', '')
            document.status = DocumentStatus.PROCESSED
            document.processed_at = timezone.now()
            document.save()

            # Crear insumos
            self._create_supplies(document, extracted_data.get('supplies', []))

            # Actualizar datos del caso con información más precisa
            self._update_case_data(case, document, extracted_data)

            return document

        except Exception as e:
            document.status = DocumentStatus.ERROR
            document.processing_error = str(e)
            document.save()
            raise DocumentProcessingError(f"Error procesando documento {doc_type}: {str(e)}")

    def _parse_date(self, date_str: Optional[str]):
        """Convierte string de fecha a objeto date"""
        if not date_str:
            return None

        try:
            from datetime import datetime
            return datetime.strptime(date_str, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            return None

    def _create_supplies(self, document: Document, supplies_data: List[Dict]):
        """Crea los insumos asociados al documento"""

        for supply_data in supplies_data:
            Supply.objects.create(
                document=document,
                name=supply_data.get('name', ''),
                quantity=supply_data.get('quantity', 1),
                ref_code=supply_data.get('ref_code', ''),
                lot_code=supply_data.get('lot_code', ''),
                udi_label_present=supply_data.get('udi_label_present', False),
                confidence=supply_data.get('confidence', 0.0)
            )

    def _update_case_data(self, case: SurgicalCase, document: Document, extracted_data: Dict):
        """
        Actualiza datos del caso con información extraída más precisa
        Sobrescribe con prioridad al documento interno, hospital/description solo si vacío.
        """

        updated = False

        def _choose(old_val, new_val, is_internal):
            if not new_val:
                return old_val, False
            if is_internal:
                return new_val, (new_val != old_val)
            if not old_val:
                return new_val, True
            return old_val, False

        is_internal = (document.document_type == DocumentType.INTERNAL)

        case.patient_name, ch = _choose(case.patient_name, extracted_data.get('patient_name'), is_internal);
        updated |= ch
        case.patient_id, ch = _choose(case.patient_id, extracted_data.get('patient_id'), is_internal);
        updated |= ch

        # Fecha
        date_str = extracted_data.get('date')
        new_date = None
        if date_str:
            from datetime import datetime
            for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y'):
                try:
                    new_date = datetime.strptime(date_str, fmt).date()
                    break
                except Exception:
                    continue
        if new_date and (is_internal or not case.surgery_date):
            if case.surgery_date != new_date:
                case.surgery_date = new_date

            updated = True

        case.city,         ch = _choose(case.city,         extracted_data.get('city'),       is_internal); updated |= ch
        case.doctor_name,  ch = _choose(case.doctor_name,  extracted_data.get('doctor'),     is_internal); updated |= ch
        case.procedure,    ch = _choose(case.procedure,    extracted_data.get('procedure'),  is_internal); updated |= ch

        if updated:
            case.save()


class ReportGenerator:
    """Generador de reportes de verificación"""

    def generate_verification_report(self, case: SurgicalCase) -> Dict:
        """
        Genera reporte completo de verificación para un caso

        Returns:
            Dict con estructura JSON del reporte
        """

        try:
            verification = case.verification
        except:
            return {
                'error': 'Caso no verificado',
                'case_id': str(case.id)
            }

        report = {
            'case_id': str(case.id),
            'case_number': case.case_number,
            'patient_name': case.patient_name,
            'patient_id': case.patient_id,
            'surgery_date': case.surgery_date.isoformat() if case.surgery_date else None,
            'doctor_name': case.doctor_name,
            'procedure': case.procedure,
            'city': case.city,

            # Resultados principales
            'verification_score': verification.verification_score,
            'overall_status': verification.overall_status,
            'requires_review': verification.requires_review,

            # Detalles por componente
            'basic_data_verification': self._format_basic_data_results(verification),
            'supplies_verification': self._format_supplies_results(verification),
            'traceability_verification': self._format_traceability_results(verification),

            # Discrepancias y observaciones
            'discrepancies': verification.discrepancies,
            'recommendations': self._generate_recommendations(verification),

            # Metadatos
            'processed_at': verification.processed_at.isoformat(),
            'processing_time': verification.processing_time,

            # Documentos procesados
            'documents': self._format_documents_info(case)
        }

        return report

    def _format_basic_data_results(self, verification) -> Dict:
        """Formatea resultados de verificación de datos básicos"""
        details = verification.basic_data_details

        return {
            'overall_match': details.get('match', False),
            'match_percentage': details.get('match_percentage', 0),
            'field_results': {
                field: {
                    'match': result.get('match', False),
                    'values_by_document': result.get('values', {}),
                    'discrepancy': result.get('discrepancy', '')
                }
                for field, result in details.get('details', {}).items()
            }
        }

    def _format_supplies_results(self, verification) -> Dict:
        """Formatea resultados de verificación de insumos"""
        details = verification.supplies_details

        return {
            'overall_match': details.get('match', False),
            'match_percentage': details.get('match_percentage', 0),
            'total_supplies': details.get('total_supplies', 0),
            'matched_supplies': details.get('matched_supplies', 0),
            'supply_details': [
                {
                    'internal_name': supply.get('internal_name', ''),
                    'internal_quantity': supply.get('internal_quantity', 0),
                    'name_match': supply.get('name_match', False),
                    'quantity_match': supply.get('quantity_match', False),
                    'hospital_matches': supply.get('hospital_matches', []),
                    'description_matches': supply.get('description_matches', []),
                    'traceability': {
                        'ref_code': supply.get('ref_code', ''),
                        'lot_code': supply.get('lot_code', ''),
                        'udi_present': supply.get('udi_label_present', False)
                    },
                    'discrepancy': supply.get('discrepancy', '')
                }
                for supply in details.get('supplies_details', [])
            ]
        }

    def _format_traceability_results(self, verification) -> Dict:
        """Formatea resultados de verificación de trazabilidad"""
        details = verification.traceability_details

        return {
            'overall_complete': details.get('complete', False),
            'completion_percentage': details.get('completion_percentage', 0),
            'total_supplies': details.get('total_supplies', 0),
            'complete_supplies': details.get('complete_supplies', 0),
            'missing_items': details.get('missing_items', []),
            'supply_traceability': [
                {
                    'supply_name': item.get('supply_name', ''),
                    'ref_complete': item.get('ref_complete', False),
                    'lot_complete': item.get('lot_complete', False),
                    'udi_complete': item.get('udi_complete', False),
                    'overall_complete': item.get('complete', False),
                    'issues': item.get('issues', [])
                }
                for item in details.get('details', [])
            ]
        }

    def _generate_recommendations(self, verification) -> List[str]:
        """Genera recomendaciones basadas en los resultados"""
        recommendations = []

        # Recomendaciones para datos básicos
        if not verification.basic_data_match:
            recommendations.append(
                "Revisar y corregir inconsistencias en datos básicos del paciente"
            )

        # Recomendaciones para insumos
        if not verification.supplies_match:
            score = verification.supplies_details.get('match_percentage', 0)
            if score < 70:
                recommendations.append(
                    "Revisar exhaustivamente las cantidades y nombres de insumos"
                )
            else:
                recommendations.append(
                    "Verificar insumos con discrepancias menores"
                )

        # Recomendaciones para trazabilidad
        if not verification.traceability_complete:
            completion = verification.traceability_details.get('completion_percentage', 0)
            if completion < 80:
                recommendations.append(
                    "Completar información de trazabilidad (REF/LOT/UDI) faltante"
                )
            else:
                recommendations.append(
                    "Verificar etiquetas UDI en insumos faltantes"
                )

        # Recomendación general
        if verification.verification_score < 85:
            recommendations.append(
                "Se recomienda revisión manual completa antes de aprobar"
            )

        return recommendations

    def _format_documents_info(self, case: SurgicalCase) -> List[Dict]:
        """Formatea información de documentos procesados"""
        documents_info = []

        for doc in case.documents.all():
            doc_info = {
                'type': doc.get_document_type_display(),
                'status': doc.get_status_display(),
                'processed_at': doc.processed_at.isoformat() if doc.processed_at else None,
                'supplies_count': doc.supplies.count(),
                'has_error': bool(doc.processing_error)
            }

            if doc.processing_error:
                doc_info['error'] = doc.processing_error

            documents_info.append(doc_info)

        return documents_info


class EquivalenceManager:
    """Gestor de equivalencias de insumos - sistema de aprendizaje"""

    def __init__(self):
        self.equivalence_model = SupplyEquivalence

    def add_equivalence(self, canonical_name: str, aliases: List[str],
                        user=None, is_auto=False) -> SupplyEquivalence:
        """Añade una nueva equivalencia o actualiza existente"""

        # Normalizar nombres
        canonical_clean = self._normalize_name(canonical_name)
        aliases_clean = [self._normalize_name(alias) for alias in aliases]

        # Buscar equivalencia existente
        equivalence, created = self.equivalence_model.objects.get_or_create(
            canonical_name=canonical_clean,
            defaults={
                'aliases': aliases_clean,
                'is_auto_generated': is_auto,
                'validated_by': user,
                'confidence_score': 0.8 if is_auto else 1.0
            }
        )

        if not created:
            # Actualizar aliases existentes
            for alias in aliases_clean:
                equivalence.add_alias(alias)

            if user and not equivalence.validated_by:
                equivalence.validated_by = user
                equivalence.confidence_score = 1.0
                equivalence.save()

        return equivalence

    def suggest_equivalences(self, supply_names: List[str]) -> List[Dict]:
        """Sugiere equivalencias basadas en similitud de nombres"""
        suggestions = []

        for name in supply_names:
            similar_names = self._find_similar_names(name, supply_names)
            if len(similar_names) > 1:
                suggestions.append({
                    'canonical_candidate': name,
                    'similar_names': similar_names,
                    'confidence': self._calculate_similarity_confidence(similar_names)
                })

        return suggestions

    def _normalize_name(self, name: str) -> str:
        """Normaliza nombre para equivalencias, quitando acentos y estandarizando tokens"""

        s = unicodedata.normalize('NFKD', name)
        s = ''.join(c for c in s if not unicodedata.combining(c))
        s = s.lower().strip()
        s = s.replace('×', 'x')
        s = re.sub(r'[^\w\s\d\.,x\-]', '', s)
        s = re.sub(r'\s+', ' ', s)
        s = re.sub(r'(\d+(?:\.\d+)?)\s*x\s*(\d+(?:\.\d+)?)', r'\1x\2', s)
        replacements = {
            'standard': 'estandar',
        }
        for old, new in replacements.items():
            s = s.replace(old, new)
        return s

    def _find_similar_names(self, target_name: str, all_names: List[str]) -> List[str]:
        """Encuentra nombres similares usando fuzzy matching (rapidfuzz)"""

        similar = []
        target_normalized = self._normalize_name(target_name)

        for name in all_names:
            if name == target_name:
                continue

            name_normalized = self._normalize_name(name)
            similarity = fuzz.token_sort_ratio(target_normalized, name_normalized)

            if similarity >= 80:
                similar.append({'name': name, 'similarity': similarity})
        similar.sort(key=lambda x: x['similarity'], reverse=True)
        return [target_name] + [item['name'] for item in similar]

    def _calculate_similarity_confidence(self, similar_names: List[str]) -> float:
        """Calcula confianza de la sugerencia de equivalencia"""
        if len(similar_names) < 2:
            return 0.0


        total_similarity = 0
        comparisons = 0

        for i in range(len(similar_names)):
            for j in range(i + 1, len(similar_names)):
                name1_norm = self._normalize_name(similar_names[i])
                name2_norm = self._normalize_name(similar_names[j])
                similarity = fuzz.token_sort_ratio(name1_norm, name2_norm)
                total_similarity += similarity
                comparisons += 1

        return (total_similarity / comparisons) / 100.0 if comparisons > 0 else 0.0


# Funciones utilitarias para uso en views/APIs

def process_surgical_case_files(files_dict: Dict, user) -> SurgicalCase:
    """
    Función utilitaria para procesar archivos de caso quirúrgico

    Args:
        files_dict: {
            'internal': file_object,
            'hospital': file_object,
            'description': file_object,
            'case_data': {...}  # Datos adicionales opcionales
        }
        user: Usuario que procesa

    Returns:
        SurgicalCase procesado
    """

    processor = DocumentProcessor()

    # Convertir dict a formato esperado
    files_data = []
    for doc_type in ['internal', 'hospital', 'description']:
        if doc_type in files_dict:
            files_data.append({
                'file': files_dict[doc_type],
                'document_type': doc_type,
                'case_data': files_dict.get('case_data', {})
            })

    return processor.process_surgical_case(files_data, user)


def generate_case_report(case_id: str) -> Dict:
    """
    Función utilitaria para generar reporte de caso

    Args:
        case_id: UUID del caso

    Returns:
        Dict con reporte completo
    """
    from django.shortcuts import get_object_or_404

    case = get_object_or_404(SurgicalCase, id=case_id)
    reporter = ReportGenerator()

    return reporter.generate_verification_report(case)


def suggest_supply_equivalences(case_id: str) -> List[Dict]:
    """
    Función utilitaria para sugerir equivalencias de insumos

    Args:
        case_id: UUID del caso

    Returns:
        Lista de sugerencias de equivalencias
    """
    from django.shortcuts import get_object_or_404

    case = get_object_or_404(SurgicalCase, id=case_id)
    manager = EquivalenceManager()

    # Obtener todos los nombres de insumos del caso
    supply_names = []
    for doc in case.documents.all():
        supply_names.extend([supply.name for supply in doc.supplies.all()])

    return manager.suggest_equivalences(supply_names)
