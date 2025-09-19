from django.test import TestCase
from vgmedical_verification.apps.verification.engine import (
    SupplyMatcher, VerificationEngine
)
from vgmedical_verification.apps.document_processor.models import DocumentType
from .factories import SurgicalCaseFactory, SupplyEquivalenceFactory


class TestSupplyMatcher(TestCase):

    def setUp(self):
        self.matcher = SupplyMatcher()
        SupplyEquivalenceFactory(
            canonical_name="tornillo encefalico 3.5x55mm",
            aliases=["tornillo encefalico 3.5x55mm", "tornillo 3.5x55"]
        )

    def test_normalize_name(self):
        result = self.matcher._normalize_name("Tornillo Encefálico 3.5x55mm")
        self.assertEqual(result, "tornillo encefalico 3.5x55mm")

    def test_find_match_exact(self):
        candidates = ["Tornillo encefalico 3.5x55mm", "Placa curva"]
        result = self.matcher.find_match("Tornillo encefalico 3.5x55mm", candidates)
        self.assertIsNotNone(result)
        self.assertEqual(result[1], 100)  # 100% confidence


class TestVerificationEngine(TestCase):

    def setUp(self):
        self.engine = VerificationEngine()

    def test_verify_case(self):
        case = SurgicalCaseFactory()
        # Crear 3 documentos para el caso
        from .factories import DocumentFactory
        DocumentFactory(surgical_case=case, document_type=DocumentType.INTERNAL)
        DocumentFactory(surgical_case=case, document_type=DocumentType.HOSPITAL)
        DocumentFactory(surgical_case=case, document_type=DocumentType.DESCRIPTION)

        result = self.engine.verify_case(case)
        self.assertIsNotNone(result)
        self.assertGreaterEqual(result.verification_score, 0)
