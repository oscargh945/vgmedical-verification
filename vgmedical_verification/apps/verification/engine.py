from typing import Dict, List, Tuple, Optional
from rapidfuzz import fuzz, process
import re
import logging
import unicodedata
from django.utils import timezone

from ..document_processor.models import (
    SurgicalCase, Document, Supply, SupplyEquivalence,
    VerificationResult, DocumentType
)

logger = logging.getLogger(__name__)


class VerificationError(Exception):
    """Excepción para errores de verificación"""
    pass


class SupplyMatcher:
    """Matcher para encontrar equivalencias entre nombres de insumos"""

    def __init__(self):
        self.equivalences = self._load_equivalences()
        self.fuzzy_threshold = 85  # Umbral de similitud para fuzzy matching

    def _load_equivalences(self) -> Dict[str, List[str]]:
        """Carga equivalencias desde la base de datos"""
        equivalences = {}
        for equiv in SupplyEquivalence.objects.all():
            equivalences[equiv.canonical_name.lower()] = [
                alias.lower() for alias in equiv.aliases
            ]
        return equivalences

    def find_match(self, supply_name: str, candidate_names: List[str]) -> Optional[Tuple[str, int]]:
        """
        Encuentra la mejor coincidencia para un insumo

        Returns:
            Tuple[str, int]: (nombre_coincidente, score_confianza) o None
        """
        supply_name_clean = self._normalize_name(supply_name)

        # 1. Búsqueda exacta
        for candidate in candidate_names:
            if supply_name_clean == self._normalize_name(candidate):
                return (candidate, 100)

        # 2. Búsqueda por equivalencias conocidas
        for canonical, aliases in self.equivalences.items():
            if supply_name_clean in aliases:
                for candidate in candidate_names:
                    candidate_clean = self._normalize_name(candidate)
                    if candidate_clean == canonical or candidate_clean in aliases:
                        return (candidate, 95)

        # 3. Fuzzy matching
        best_match = process.extractOne(
            supply_name_clean,
            [self._normalize_name(name) for name in candidate_names],
            scorer=fuzz.token_sort_ratio
        )

        if best_match and best_match[1] >= self.fuzzy_threshold:
            # Encontrar el nombre original
            for candidate in candidate_names:
                if self._normalize_name(candidate) == best_match[0]:
                    return (candidate, best_match[1])

        return None

    def _normalize_name(self, name: str) -> str:
        """Normaliza nombre de insumo para comparación, quitando acentos y caracteres especiales"""
        if not name:
            return ''

        # Convertir a minúsculas y quitar acentos
        normalized = unicodedata.normalize('NFKD', name)
        normalized = ''.join([c for c in normalized if not unicodedata.combining(c)])
        normalized = normalized.lower().strip()

        # Remover caracteres especiales y espacios extras
        normalized = re.sub(r'[^\w\s\d.,x×-]', '', normalized)
        normalized = re.sub(r'\s+', ' ', normalized)

        # Normalizar medidas comunes
        normalized = re.sub(r'(\d+)\s*x\s*(\d+)', r'\1x\2', normalized)
        normalized = re.sub(r'(\d+)\s*×\s*(\d+)', r'\1x\2', normalized)
        normalized = re.sub(r'mm', 'mm', normalized)
        normalized = re.sub(r'cm', 'cm', normalized)

        # Normalizar palabras comunes
        replacements = {
            'tornillo': 'tornillo',
            'placa': 'placa',
            'clavo': 'clavo',
            'encefalico': 'encefalico',
            'estandar': 'estandar',
            'standard': 'estandar'
        }

        for old, new in replacements.items():
            normalized = normalized.replace(old, new)

        return normalized.strip()


class BasicDataVerifier:
    """Verificador de datos básicos entre documentos"""

    def verify_case(self, case: SurgicalCase) -> Dict:
        """
        Verifica consistencia de datos básicos entre los 3 documentos

        Returns:
            Dict con resultados de verificación
        """
        documents = case.documents.all()

        if len(documents) != 3:
            return {
                'match': False,
                'error': f'Faltan documentos. Se requieren 3, se encontraron {len(documents)}',
                'details': {}
            }

        # Organizar documentos por tipo
        doc_data = {}
        for doc in documents:
            doc_data[doc.document_type] = {
                'patient_name': doc.extracted_patient_name,
                'patient_id': doc.extracted_patient_id,
                'date': doc.extracted_date,
                'city': doc.extracted_city,
                'doctor': doc.extracted_doctor,
                'procedure': doc.extracted_procedure
            }

        # Verificar cada campo
        results = {
            'patient_name': self._verify_field('patient_name', doc_data),
            'patient_id': self._verify_field('patient_id', doc_data),
            'date': self._verify_field('date', doc_data),
            'city': self._verify_field('city', doc_data),
            'doctor': self._verify_field('doctor', doc_data),
            'procedure': self._verify_field('procedure', doc_data)
        }

        # Calcular match general
        matches = sum(1 for result in results.values() if result['match'])
        total_fields = len(results)
        match_percentage = (matches / total_fields) * 100

        return {
            'match': match_percentage >= 80,  # 80% de coincidencia mínima
            'match_percentage': match_percentage,
            'details': results,
            'discrepancies': [
                f"{field}: {result['discrepancy']}"
                for field, result in results.items()
                if not result['match'] and result.get('discrepancy')
            ]
        }

    def _verify_field(self, field_name: str, doc_data: Dict) -> Dict:
        """Verifica un campo específico entre los 3 documentos"""
        values = {}

        for doc_type in [DocumentType.INTERNAL, DocumentType.HOSPITAL, DocumentType.DESCRIPTION]:
            if doc_type in doc_data:
                values[doc_type] = doc_data[doc_type].get(field_name, '')

        if len(values) < 3:
            return {
                'match': False,
                'discrepancy': f'Campo {field_name} faltante en algunos documentos',
                'values': values
            }

        # Verificación específica por tipo de campo
        if field_name in ['patient_name', 'doctor']:
            return self._verify_name_field(field_name, values)
        elif field_name == 'patient_id':
            return self._verify_id_field(values)
        elif field_name == 'date':
            return self._verify_date_field(values)
        elif field_name in ['city', 'procedure']:
            return self._verify_text_field(field_name, values)

        return {'match': False, 'discrepancy': f'Tipo de campo desconocido: {field_name}'}

    def _verify_name_field(self, field_name: str, values: Dict) -> Dict:
        """Verifica campos de nombres (paciente, doctor)"""
        normalized_values = {}

        for doc_type, value in values.items():
            if value:
                # Normalizar nombres para comparación
                normalized = self._normalize_name(value)
                normalized_values[doc_type] = normalized
            else:
                normalized_values[doc_type] = ''

        # Verificar si todos son similares
        unique_values = set(normalized_values.values())
        unique_values.discard('')  # Remover valores vacíos

        if len(unique_values) <= 1:
            return {'match': True, 'values': values}

        # Usar fuzzy matching para nombres similares
        similarity_threshold = 85
        base_name = list(unique_values)[0]

        for name in unique_values:
            if fuzz.ratio(base_name, name) < similarity_threshold:
                return {
                    'match': False,
                    'discrepancy': f'Nombres diferentes en {field_name}: {list(unique_values)}',
                    'values': values
                }

        return {'match': True, 'values': values, 'note': 'Coincidencia por similitud'}

    def _normalize_name(self, name: str) -> str:
        """Normaliza nombres para comparación, quitando acentos"""
        if not name:
            return ''

        normalized = unicodedata.normalize('NFKD', name)
        normalized = ''.join([c for c in normalized if not unicodedata.combining(c)])
        normalized = normalized.upper().strip()
        normalized = re.sub(r'\s+', ' ', normalized)

        # Remover títulos comunes
        titles = ['DR.', 'DRA.', 'DR', 'DRA', 'MD', 'M.D.']
        for title in titles:
            normalized = normalized.replace(title, '').strip()

        return normalized

    def _verify_id_field(self, values: Dict) -> Dict:
        """Verifica campo de identificación"""
        # Limpiar y normalizar IDs
        normalized_ids = {}

        for doc_type, value in values.items():
            if value:
                # Remover puntos, guiones, espacios
                clean_id = re.sub(r'[^\d]', '', str(value))
                normalized_ids[doc_type] = clean_id
            else:
                normalized_ids[doc_type] = ''

        unique_ids = set(normalized_ids.values())
        unique_ids.discard('')

        if len(unique_ids) <= 1:
            return {'match': True, 'values': values}
        else:
            return {
                'match': False,
                'discrepancy': f'IDs diferentes: {list(unique_ids)}',
                'values': values
            }

    def _verify_date_field(self, values: Dict) -> Dict:
        """Verifica campo de fecha"""
        dates = {}

        for doc_type, value in values.items():
            if value:
                dates[doc_type] = str(value)
            else:
                dates[doc_type] = ''

        unique_dates = set(dates.values())
        unique_dates.discard('')

        if len(unique_dates) <= 1:
            return {'match': True, 'values': values}
        else:
            return {
                'match': False,
                'discrepancy': f'Fechas diferentes: {list(unique_dates)}',
                'values': values
            }

    def _verify_text_field(self, field_name: str, values: Dict) -> Dict:
        """Verifica campos de texto general"""
        if not any(values.values()):
            return {
                'match': False,
                'discrepancy': f'Campo {field_name} vacío en todos los documentos',
                'values': values
            }

        # Para procedimientos, usar fuzzy matching más permisivo
        if field_name == 'procedure':
            return self._verify_procedure_field(values)

        # Para ciudad, comparación más estricta
        normalized_values = set()
        for value in values.values():
            if value:
                normalized_values.add(value.upper().strip())

        if len(normalized_values) <= 1:
            return {'match': True, 'values': values}
        else:
            return {
                'match': False,
                'discrepancy': f'{field_name} diferentes: {list(normalized_values)}',
                'values': values
            }

    def _verify_procedure_field(self, values: Dict) -> Dict:
        """Verifica específicamente el campo de procedimiento"""
        non_empty_values = [v for v in values.values() if v]

        if len(non_empty_values) < 2:
            return {'match': True, 'values': values}

        # Usar fuzzy matching para procedimientos (pueden tener variaciones)
        base_proc = non_empty_values[0]
        similarity_threshold = 70  # Más permisivo para procedimientos

        for proc in non_empty_values[1:]:
            if fuzz.partial_ratio(base_proc.lower(), proc.lower()) < similarity_threshold:
                return {
                    'match': False,
                    'discrepancy': f'Procedimientos muy diferentes',
                    'values': values
                }

        return {'match': True, 'values': values}


class SupplyVerifier:
    """Verificador de insumos entre documentos"""

    def __init__(self):
        self.matcher = SupplyMatcher()

    def verify_supplies(self, case: SurgicalCase) -> Dict:
        """
        Verifica consistencia de insumos entre los 3 documentos

        Returns:
            Dict con resultados de verificación de insumos
        """
        documents = case.documents.all()

        # Obtener insumos por documento
        supplies_by_doc = {}
        for doc in documents:
            supplies_by_doc[doc.document_type] = list(doc.supplies.all())

        # Verificar que todos los documentos tengan insumos
        if not all(supplies_by_doc.values()):
            return {
                'match': False,
                'error': 'Algunos documentos no tienen insumos registrados',
                'supplies_details': []
            }

        # Analizar cada insumo del reporte interno (es la referencia)
        internal_supplies = supplies_by_doc.get(DocumentType.INTERNAL, [])
        hospital_supplies = supplies_by_doc.get(DocumentType.HOSPITAL, [])
        description_supplies = supplies_by_doc.get(DocumentType.DESCRIPTION, [])

        supply_results = []
        total_matches = 0

        for internal_supply in internal_supplies:
            result = self._verify_single_supply(
                internal_supply,
                hospital_supplies,
                description_supplies
            )
            supply_results.append(result)
            if result['quantity_match'] and result['name_match']:
                total_matches += 1

        # Calcular estadísticas generales
        total_supplies = len(internal_supplies)
        match_percentage = (total_matches / total_supplies * 100) if total_supplies > 0 else 0

        return {
            'match': match_percentage >= 90,  # 90% de coincidencia para insumos
            'match_percentage': match_percentage,
            'total_supplies': total_supplies,
            'matched_supplies': total_matches,
            'supplies_details': supply_results,
            'discrepancies': [
                f"{result['internal_name']}: {result['discrepancy']}"
                for result in supply_results
                if result.get('discrepancy')
            ]
        }

    def _verify_single_supply(self, internal_supply: Supply,
                              hospital_supplies: List[Supply],
                              description_supplies: List[Supply]) -> Dict:
        """Verifica un insumo específico contra los otros documentos"""

        result = {
            'internal_name': internal_supply.name,
            'internal_quantity': internal_supply.quantity,
            'ref_code': internal_supply.ref_code,
            'lot_code': internal_supply.lot_code,
            'udi_label_present': internal_supply.udi_label_present,
            'hospital_matches': [],
            'description_matches': [],
            'name_match': False,
            'quantity_match': False,
            'discrepancy': None
        }

        # Buscar coincidencias en reporte de hospital
        hospital_match = self._find_supply_match(
            internal_supply, hospital_supplies
        )

        # Buscar coincidencias en descripción quirúrgica
        description_match = self._find_supply_match(
            internal_supply, description_supplies
        )

        if hospital_match:
            result['hospital_matches'].append({
                'name': hospital_match['supply'].name,
                'quantity': hospital_match['supply'].quantity,
                'confidence': hospital_match['confidence']
            })

        if description_match:
            result['description_matches'].append({
                'name': description_match['supply'].name,
                'quantity': description_match['supply'].quantity,
                'confidence': description_match['confidence']
            })

        # Evaluar coincidencias
        name_matches = []
        quantity_matches = []

        if hospital_match:
            name_matches.append(hospital_match['confidence'] >= 85)
            quantity_matches.append(
                hospital_match['supply'].quantity == internal_supply.quantity
            )

        if description_match:
            name_matches.append(description_match['confidence'] >= 85)
            quantity_matches.append(
                description_match['supply'].quantity == internal_supply.quantity
            )

        result['name_match'] = any(name_matches) if name_matches else False
        result['quantity_match'] = any(quantity_matches) if quantity_matches else False

        # Generar discrepancias
        if not result['name_match']:
            result['discrepancy'] = 'No se encontró coincidencia de nombre'
        elif not result['quantity_match']:
            result['discrepancy'] = 'Cantidades no coinciden'

        return result

    def _find_supply_match(self, target_supply: Supply,
                           candidate_supplies: List[Supply]) -> Optional[Dict]:
        """Encuentra la mejor coincidencia para un insumo"""

        if not candidate_supplies:
            return None

        candidate_names = [supply.name for supply in candidate_supplies]
        match = self.matcher.find_match(target_supply.name, candidate_names)

        if match:
            matched_name, confidence = match
            # Encontrar el supply object correspondiente
            for supply in candidate_supplies:
                if supply.name == matched_name:
                    return {
                        'supply': supply,
                        'confidence': confidence
                    }

        return None


class TraceabilityVerifier:
    """Verificador de trazabilidad (etiquetas UDI, REF/LOT)"""

    def verify_traceability(self, case: SurgicalCase) -> Dict:
        """
        Verifica trazabilidad en el reporte interno

        Returns:
            Dict con resultados de verificación de trazabilidad
        """
        try:
            internal_doc = case.documents.get(document_type=DocumentType.INTERNAL)
        except Document.DoesNotExist:
            return {
                'complete': False,
                'error': 'No se encontró reporte interno',
                'details': []
            }

        internal_supplies = internal_doc.supplies.all()
        traceability_results = []
        complete_count = 0

        for supply in internal_supplies:
            result = self._verify_supply_traceability(supply)
            traceability_results.append(result)
            if result['complete']:
                complete_count += 1

        total_supplies = len(internal_supplies)
        completion_percentage = (complete_count / total_supplies * 100) if total_supplies > 0 else 0

        return {
            'complete': completion_percentage >= 95,  # 95% de trazabilidad completa
            'completion_percentage': completion_percentage,
            'total_supplies': total_supplies,
            'complete_supplies': complete_count,
            'details': traceability_results,
            'missing_items': [
                result['supply_name']
                for result in traceability_results
                if not result['complete']
            ]
        }

    def _verify_supply_traceability(self, supply: Supply) -> Dict:
        """Verifica trazabilidad de un insumo específico"""

        result = {
            'supply_name': supply.name,
            'ref_code': supply.ref_code,
            'lot_code': supply.lot_code,
            'udi_label_present': supply.udi_label_present,
            'ref_complete': bool(supply.ref_code),
            'lot_complete': bool(supply.lot_code),
            'udi_complete': supply.udi_label_present,
            'complete': False,
            'issues': []
        }

        # Verificar cada componente
        if not result['ref_complete']:
            result['issues'].append('Falta código REF')

        if not result['lot_complete']:
            result['issues'].append('Falta código LOT')

        if not result['udi_complete']:
            result['issues'].append('Falta etiqueta UDI')

        # Trazabilidad completa requiere REF, LOT y UDI
        result['complete'] = (
            result['ref_complete'] and
            result['lot_complete'] and
            result['udi_complete']
        )

        return result


class VerificationEngine:
    """Motor principal de verificación"""

    def __init__(self):
        self.basic_verifier = BasicDataVerifier()
        self.supply_verifier = SupplyVerifier()
        self.traceability_verifier = TraceabilityVerifier()

    def verify_case(self, case: SurgicalCase) -> VerificationResult:
        """
        Ejecuta verificación completa de un caso quirúrgico

        Returns:
            VerificationResult object
        """
        start_time = timezone.now()

        try:
            # Verificar datos básicos
            basic_results = self.basic_verifier.verify_case(case)

            # Verificar insumos
            supply_results = self.supply_verifier.verify_supplies(case)

            # Verificar trazabilidad
            traceability_results = self.traceability_verifier.verify_traceability(case)

            # Calcular score general
            score = self._calculate_overall_score(
                basic_results, supply_results, traceability_results
            )

            # Determinar si requiere revisión
            requires_review = (
                not basic_results['match'] or
                not supply_results['match'] or
                not traceability_results['complete'] or
                score < 85
            )

            # Crear o actualizar resultado
            verification, created = VerificationResult.objects.update_or_create(
                surgical_case=case,
                defaults={
                    'basic_data_match': basic_results['match'],
                    'supplies_match': supply_results['match'],
                    'traceability_complete': traceability_results['complete'],
                    'requires_review': requires_review,
                    'basic_data_details': basic_results,
                    'supplies_details': supply_results,
                    'traceability_details': traceability_results,
                    'discrepancies': self._compile_discrepancies(
                        basic_results, supply_results, traceability_results
                    ),
                    'verification_score': score,
                    'processing_time': (timezone.now() - start_time).total_seconds()
                }
            )

            return verification

        except Exception as e:
            logger.error(f"Error en verificación del caso {case.case_number}: {str(e)}")
            raise VerificationError(f"Error en verificación: {str(e)}")

    def _calculate_overall_score(self, basic_results: Dict,
                                 supply_results: Dict,
                                 traceability_results: Dict) -> float:
        """Calcula score general de verificación (0-100)"""

        # Pesos por componente
        weights = {
            'basic_data': 0.3,
            'supplies': 0.5,
            'traceability': 0.2
        }

        # Scores individuales
        basic_score = basic_results.get('match_percentage', 0)
        supply_score = supply_results.get('match_percentage', 0)
        traceability_score = traceability_results.get('completion_percentage', 0)

        # Score ponderado
        overall_score = (
            basic_score * weights['basic_data'] +
            supply_score * weights['supplies'] +
            traceability_score * weights['traceability']
        )

        return round(overall_score, 2)

    def _compile_discrepancies(self, basic_results: Dict,
                               supply_results: Dict,
                               traceability_results: Dict) -> List[str]:
        """Compila todas las discrepancias encontradas"""
        discrepancies = []

        # Discrepancias de datos básicos
        if 'discrepancies' in basic_results:
            discrepancies.extend(basic_results['discrepancies'])

        # Discrepancias de insumos
        if 'discrepancies' in supply_results:
            discrepancies.extend(supply_results['discrepancies'])

        # Problemas de trazabilidad
        if 'missing_items' in traceability_results:
            for item in traceability_results['missing_items']:
                discrepancies.append(f"Trazabilidad incompleta: {item}")

        return discrepancies
