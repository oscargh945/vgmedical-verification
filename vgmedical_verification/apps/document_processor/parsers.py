import re
import PyPDF2
import io
from PIL import Image
import pytesseract
from typing import Dict, List, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class DocumentParserError(Exception):
    """Excepción para errores de parsing de documentos"""
    pass


class BaseDocumentParser:
    """Parser base para documentos médicos"""

    def __init__(self):
        self.extracted_data = {}
        self.raw_text = ""
        self.confidence_score = 0.0

    def parse_file(self, file) -> Dict:
        """Extrae texto de un archivo y parsea los datos básicos"""
        try:
            self.raw_text = self._extract_text(file)
            self.extracted_data = self._parse_basic_data(self.raw_text)
            self.extracted_data['raw_text'] = self.raw_text
            return self.extracted_data
        except Exception as e:
            logger.error(f"Error parsing file: {str(e)}")
            raise DocumentParserError(f"Error procesando documento: {str(e)}")

    def _extract_text(self, file) -> str:
        """Extrae texto del archivo según su tipo"""
        file_extension = file.name.lower().split('.')[-1]

        if file_extension == 'pdf':
            return self._extract_from_pdf(file)
        elif file_extension in ['jpg', 'jpeg', 'png', 'bmp', 'tiff']:
            return self._extract_from_image(file)
        else:
            raise DocumentParserError(f"Tipo de archivo no soportado: {file_extension}")

    def _extract_from_pdf(self, file) -> str:
        """Extrae texto de un PDF"""
        try:
            pdf_reader = PyPDF2.PdfReader(io.BytesIO(file.read()))
            text = ""
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"

            # Si no hay texto extraído, es posible que sea un PDF escaneado
            if not text.strip():
                # Aquí podrías usar pdf2image + OCR si es necesario
                logger.warning("PDF sin texto extraíble, posible imagen escaneada")

            return text
        except Exception as e:
            raise DocumentParserError(f"Error extrayendo texto de PDF: {str(e)}")

    def _extract_from_image(self, file) -> str:
        """Extrae texto de una imagen usando OCR"""
        try:
            image = Image.open(io.BytesIO(file.read()))
            # Configuración básica de tesseract para español
            config = '--oem 3 --psm 6 -l spa'
            text = pytesseract.image_to_string(image, config=config)

            # Calcular confianza básica
            data = pytesseract.image_to_data(image, config=config, output_type=pytesseract.Output.DICT)
            confidences = [int(conf) for conf in data['conf'] if int(conf) > 0]
            self.confidence_score = sum(confidences) / len(confidences) if confidences else 0

            return text
        except Exception as e:
            raise DocumentParserError(f"Error en OCR de imagen: {str(e)}")

    def _parse_basic_data(self, text: str) -> Dict:
        """Parsea datos básicos del texto extraído - debe ser sobrescrito"""
        raise NotImplementedError("Debe implementarse en clases hijas")


class InternalReportParser(BaseDocumentParser):
    """Parser para Reporte de Gasto Quirúrgico Interno"""

    def _parse_basic_data(self, text: str) -> Dict:
        data = {
            'patient_name': self._extract_patient_name(text),
            'patient_id': self._extract_patient_id(text),
            'date': self._extract_date(text),
            'city': self._extract_city(text),
            'doctor': self._extract_doctor(text),
            'procedure': self._extract_procedure(text),
            'supplies': self._extract_supplies_with_traceability(text)
        }
        return data

    def _extract_patient_name(self, text: str) -> str:
        """Extrae nombre del paciente"""
        patterns = [
            r'PACIENTE[:\s]*([A-ZÁÉÍÓÚÑ\s]+)',
            r'NOMBRE[:\s]*([A-ZÁÉÍÓÚÑ\s]+)',
            r'Paciente[:\s]*([A-Za-záéíóúñ\s]+)'
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return ""

    def _extract_patient_id(self, text: str) -> str:
        """Extrae identificación del paciente"""
        patterns = [
            r'ID[:\s]*(\d+)',
            r'IDENTIFICACIÓN[:\s]*(\d+)',
            r'CEDULA[:\s]*(\d+)',
            r'C\.C[:\s]*(\d+)'
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return ""

    def _extract_date(self, text: str) -> Optional[str]:
        """Extrae fecha de la cirugía"""
        patterns = [
            r'FECHA[:\s]*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
            r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
            r'FECHA[:\s]*(\d{1,2}\s+de\s+\w+\s+de\s+\d{4})'
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                date_str = match.group(1).strip()
                # Aquí podrías normalizar el formato de fecha
                return self._normalize_date(date_str)
        return None

    def _normalize_date(self, date_str: str) -> Optional[str]:
        """Normaliza formato de fecha a YYYY-MM-DD"""
        try:
            # Intentar varios formatos
            formats = ['%d/%m/%Y', '%d-%m-%Y', '%d/%m/%y', '%d-%m-%y']
            for fmt in formats:
                try:
                    date_obj = datetime.strptime(date_str, fmt)
                    return date_obj.strftime('%Y-%m-%d')
                except ValueError:
                    continue
        except:
            pass
        return None

    def _extract_city(self, text: str) -> str:
        """Extrae ciudad"""
        patterns = [
            r'CIUDAD[:\s]*([A-Za-záéíóúñ\s]+)',
            r'LUGAR[:\s]*([A-Za-záéíóúñ\s]+)'
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return ""

    def _extract_doctor(self, text: str) -> str:
        """Extrae nombre del médico"""
        patterns = [
            r'MÉDICO[:\s]*([A-Za-záéíóúñ\s\.]+)',
            r'DOCTOR[:\s]*([A-Za-záéíóúñ\s\.]+)',
            r'DR\.[:\s]*([A-Za-záéíóúñ\s\.]+)'
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return ""

    def _extract_procedure(self, text: str) -> str:
        """Extrae procedimiento quirúrgico"""
        patterns = [
            r'PROCEDIMIENTO[:\s]*([A-Za-záéíóúñ\s\.,]+)',
            r'CIRUGÍA[:\s]*([A-Za-záéíóúñ\s\.,]+)',
            r'OPERACIÓN[:\s]*([A-Za-záéíóúñ\s\.,]+)'
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return ""

    def _extract_supplies_with_traceability(self, text: str) -> List[Dict]:
        """Extrae insumos con información de trazabilidad (REF/LOT/UDI)"""
        supplies = []

        # Buscar patrones de insumos con formato típico
        # Ejemplo: "Tornillo encefálico 3.5x55mm (2) REF: ABC123 LOT: DEF456 [UDI]"
        pattern = r'([A-Za-záéíóúñ\s\d\.,x×-]+)\s*\((\d+)\)(?:\s*REF[:\s]*([A-Z0-9]+))?(?:\s*LOT[:\s]*([A-Z0-9]+))?(\s*\[UDI\])?'

        matches = re.findall(pattern, text, re.IGNORECASE)

        for match in matches:
            supply = {
                'name': match[0].strip(),
                'quantity': int(match[1]) if match[1].isdigit() else 1,
                'ref_code': match[2] if match[2] else '',
                'lot_code': match[3] if match[3] else '',
                'udi_label_present': bool(match[4])
            }
            supplies.append(supply)

        return supplies


class HospitalReportParser(BaseDocumentParser):
    """Parser para Reporte de Gasto Quirúrgico del Hospital"""

    def _parse_basic_data(self, text: str) -> Dict:
        data = {
            'patient_name': self._extract_patient_name(text),
            'patient_id': self._extract_patient_id(text),
            'date': self._extract_date(text),
            'city': self._extract_city(text),
            'doctor': self._extract_doctor(text),
            'procedure': self._extract_procedure(text),
            'supplies': self._extract_supplies_simple(text)
        }
        return data

    def _extract_patient_name(self, text: str) -> str:
        # Similar al interno pero puede tener variaciones
        return InternalReportParser()._extract_patient_name(text)

    def _extract_patient_id(self, text: str) -> str:
        return InternalReportParser()._extract_patient_id(text)

    def _extract_date(self, text: str) -> Optional[str]:
        return InternalReportParser()._extract_date(text)

    def _extract_city(self, text: str) -> str:
        return InternalReportParser()._extract_city(text)

    def _extract_doctor(self, text: str) -> str:
        return InternalReportParser()._extract_doctor(text)

    def _extract_procedure(self, text: str) -> str:
        return InternalReportParser()._extract_procedure(text)

    def _extract_supplies_simple(self, text: str) -> List[Dict]:
        """Extrae insumos sin información de trazabilidad"""
        supplies = []

        # Patrón más simple para reporte de hospital
        pattern = r'([A-Za-záéíóúñ\s\d\.,x×-]+)\s*\((\d+)\)'

        matches = re.findall(pattern, text, re.IGNORECASE)

        for match in matches:
            supply = {
                'name': match[0].strip(),
                'quantity': int(match[1]) if match[1].isdigit() else 1
            }
            supplies.append(supply)

        return supplies


class SurgicalDescriptionParser(BaseDocumentParser):
    """Parser para Descripción Quirúrgica del Doctor"""

    def _parse_basic_data(self, text: str) -> Dict:
        data = {
            'patient_name': self._extract_patient_name(text),
            'patient_id': self._extract_patient_id(text),
            'date': self._extract_date(text),
            'city': self._extract_city(text),
            'doctor': self._extract_doctor(text),
            'procedure': self._extract_procedure(text),
            'supplies': self._extract_supplies_from_description(text)
        }
        return data

    def _extract_patient_name(self, text: str) -> str:
        return InternalReportParser()._extract_patient_name(text)

    def _extract_patient_id(self, text: str) -> str:
        return InternalReportParser()._extract_patient_id(text)

    def _extract_date(self, text: str) -> Optional[str]:
        return InternalReportParser()._extract_date(text)

    def _extract_city(self, text: str) -> str:
        return InternalReportParser()._extract_city(text)

    def _extract_doctor(self, text: str) -> str:
        return InternalReportParser()._extract_doctor(text)

    def _extract_procedure(self, text: str) -> str:
        return InternalReportParser()._extract_procedure(text)

    def _extract_supplies_from_description(self, text: str) -> List[Dict]:
        """Extrae insumos mencionados en la descripción quirúrgica usando grupos nombrados"""
        supplies = []

        # Buscar secciones que mencionen insumos utilizados
        patterns = [
            r'MATERIALES[:\s]*(?P<materials>[^\.]+)',
            r'INSUMOS[:\s]*(?P<insumos>[^\.]+)',
            r'SE UTILIZÓ[:\s]*(?P<utilizo>[^\.]+)',
            r'IMPLANTES[:\s]*(?P<implantes>[^\.]+)'
        ]

        supply_text = ""
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                # Extraer el grupo nombrado
                for group_name in match.groupdict():
                    if match.group(group_name):
                        supply_text += match.group(group_name) + " "

        if supply_text:
            # Extraer nombres de insumos de la descripción
            supply_patterns = [
                r'(?P<quantity>\d+)\s+(?P<name>[A-Za-záéíóúñ\s\d\.,x×-]+)',
                r'(?P<name>[A-Za-záéíóúñ\s\d\.,x×-]+)\s*\((?P<quantity>\d+)\)'
            ]

            for pattern in supply_patterns:
                matches = re.finditer(pattern, supply_text, re.IGNORECASE)
                for match in matches:
                    name = match.group('name').strip()
                    quantity = match.group('quantity')
                    supplies.append({
                        'name': name,
                        'quantity': int(quantity) if quantity.isdigit() else 1
                    })

        return supplies


# Factory para obtener el parser correcto
class DocumentParserFactory:
    """Factory para crear parsers según el tipo de documento"""

    @staticmethod
    def get_parser(document_type: str) -> BaseDocumentParser:
        """Retorna el parser apropiado según el tipo de documento"""
        if document_type == 'internal':
            return InternalReportParser()
        elif document_type == 'hospital':
            return HospitalReportParser()
        elif document_type == 'description':
            return SurgicalDescriptionParser()
        else:
            raise ValueError(f"Tipo de documento no soportado: {document_type}")
