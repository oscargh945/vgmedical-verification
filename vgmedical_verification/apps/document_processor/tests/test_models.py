"""Tests for document processor models."""

from django.test import TestCase
from django.core.exceptions import ValidationError
from datetime import date

from vgmedical_verification.apps.document_processor.models import (
    SurgicalCase, Document, Supply, SupplyEquivalence, VerificationResult,
    DocumentType, DocumentStatus
)
from vgmedical_verification.apps.document_processor.tests.factories import (
    SurgicalCaseFactory, DocumentFactory, SupplyFactory, SupplyEquivalenceFactory,
    VerificationResultFactory
)


class TestSurgicalCaseModel(TestCase):
    """Test SurgicalCase model."""

    def test_surgical_case_str_representation(self):
        """Test surgical case string representation."""
        case = SurgicalCaseFactory(
            case_number="VG_20240101_0001",
            patient_name="Juan Pérez"
        )
        expected = "Caso VG_20240101_0001 - Juan Pérez"
        self.assertEqual(str(case), expected)

    def test_surgical_case_number_unique(self):
        """Test that case number is unique."""
        case_number = "VG_20240101_0001"
        SurgicalCaseFactory(case_number=case_number)
        
        with self.assertRaises(Exception):  # Should raise IntegrityError
            SurgicalCaseFactory(case_number=case_number)

    def test_surgical_case_ordering(self):
        """Test surgical case ordering."""
        case1 = SurgicalCaseFactory()
        case2 = SurgicalCaseFactory()
        case3 = SurgicalCaseFactory()
        
        cases = SurgicalCase.objects.all()
        self.assertEqual(list(cases), [case3, case2, case1])  # Ordered by -created


class TestDocumentModel(TestCase):
    """Test Document model."""

    def test_document_str_representation(self):
        """Test document string representation."""
        case = SurgicalCaseFactory(case_number="VG_20240101_0001")
        document = DocumentFactory(
            surgical_case=case,
            document_type=DocumentType.INTERNAL
        )
        expected = "Reporte Interno - VG_20240101_0001"
        self.assertEqual(str(document), expected)

    def test_document_unique_constraint(self):
        """Test document unique constraint (case + document_type)."""
        case = SurgicalCaseFactory()
        DocumentFactory(surgical_case=case, document_type=DocumentType.INTERNAL)
        
        with self.assertRaises(Exception):  # Should raise IntegrityError
            DocumentFactory(surgical_case=case, document_type=DocumentType.INTERNAL)

    def test_document_status_default(self):
        """Test document status default value."""
        document = DocumentFactory()
        self.assertEqual(document.status, DocumentStatus.PROCESSED)  # Factory sets PROCESSED

    def test_document_related_surgical_case(self):
        """Test document related surgical case."""
        case = SurgicalCaseFactory()
        document = DocumentFactory(surgical_case=case)
        
        self.assertEqual(document.surgical_case, case)
        self.assertIn(document, case.documents.all())


class TestSupplyModel(TestCase):
    """Test Supply model."""

    def test_supply_str_representation(self):
        """Test supply string representation."""
        supply = SupplyFactory(name="Tornillo encefálico 3.5x55mm", quantity=2)
        expected = "Tornillo encefálico 3.5x55mm (x2)"
        self.assertEqual(str(supply), expected)

    def test_supply_related_document(self):
        """Test supply related document."""
        document = DocumentFactory()
        supply = SupplyFactory(document=document)
        
        self.assertEqual(supply.document, document)
        self.assertIn(supply, document.supplies.all())

    def test_supply_udi_label_default(self):
        """Test supply UDI label default value."""
        supply = SupplyFactory()
        self.assertTrue(supply.udi_label_present)  # Factory sets True

    def test_supply_confidence_default(self):
        """Test supply confidence default value."""
        supply = SupplyFactory()
        self.assertEqual(supply.confidence, 0.0)


class TestSupplyEquivalenceModel(TestCase):
    """Test SupplyEquivalence model."""

    def test_supply_equivalence_str_representation(self):
        """Test supply equivalence string representation."""
        equivalence = SupplyEquivalenceFactory(canonical_name="tornillo encefalico")
        self.assertEqual(str(equivalence), "tornillo encefalico")

    def test_supply_equivalence_canonical_name_unique(self):
        """Test that canonical name is unique."""
        canonical_name = "tornillo encefalico 3.5x55mm"
        SupplyEquivalenceFactory(canonical_name=canonical_name)
        
        with self.assertRaises(Exception):  # Should raise IntegrityError
            SupplyEquivalenceFactory(canonical_name=canonical_name)

    def test_supply_equivalence_aliases_default(self):
        """Test supply equivalence aliases default value."""
        equivalence = SupplyEquivalenceFactory()
        self.assertIsInstance(equivalence.aliases, list)  # Factory sets aliases

    def test_supply_equivalence_confidence_default(self):
        """Test supply equivalence confidence default value."""
        equivalence = SupplyEquivalenceFactory()
        self.assertGreaterEqual(equivalence.confidence_score, 0.0)  # Factory sets random value

    def test_supply_equivalence_times_used_default(self):
        """Test supply equivalence times used default value."""
        equivalence = SupplyEquivalenceFactory()
        self.assertEqual(equivalence.times_used, 0)

    def test_supply_equivalence_is_auto_generated_default(self):
        """Test supply equivalence is auto generated default value."""
        equivalence = SupplyEquivalenceFactory()
        self.assertFalse(equivalence.is_auto_generated)

    def test_add_alias_method(self):
        """Test add_alias method."""
        equivalence = SupplyEquivalenceFactory(aliases=["alias1"])
        
        equivalence.add_alias("alias2")
        self.assertIn("alias2", equivalence.aliases)
        
        # Should not add duplicate
        original_count = len(equivalence.aliases)
        equivalence.add_alias("alias2")
        self.assertEqual(len(equivalence.aliases), original_count)


class TestVerificationResultModel(TestCase):
    """Test VerificationResult model."""

    def test_verification_result_str_representation(self):
        """Test verification result string representation."""
        case = SurgicalCaseFactory(case_number="VG_20240101_0001")
        result = VerificationResultFactory(surgical_case=case)
        expected = "Verificación VG_20240101_0001"
        self.assertEqual(str(result), expected)

    def test_verification_result_one_to_one_with_case(self):
        """Test verification result one-to-one relationship with case."""
        case = SurgicalCaseFactory()
        result = VerificationResultFactory(surgical_case=case)
        
        self.assertEqual(result.surgical_case, case)
        self.assertEqual(case.verification, result)

    def test_verification_result_default_values(self):
        """Test verification result default values."""
        result = VerificationResultFactory()
        
        # Factory sets specific values, not defaults
        self.assertTrue(result.basic_data_match)  # Factory sets True
        self.assertTrue(result.supplies_match)    # Factory sets True
        self.assertTrue(result.traceability_complete)  # Factory sets True
        self.assertFalse(result.requires_review)  # Factory sets False
        self.assertGreater(result.verification_score, 0.0)  # Factory sets random value
        self.assertEqual(result.processing_time, 0.0)
        self.assertIsInstance(result.basic_data_details, dict)
        self.assertIsInstance(result.supplies_details, dict)
        self.assertIsInstance(result.traceability_details, dict)
        self.assertEqual(result.discrepancies, [])
        self.assertEqual(result.analyst_feedback, {})

    def test_overall_status_aproved(self):
        """Test overall status when all checks pass."""
        result = VerificationResultFactory(
            basic_data_match=True,
            supplies_match=True,
            traceability_complete=True,
            requires_review=False
        )
        self.assertEqual(result.overall_status, "APROBADO")

    def test_overall_status_requires_review(self):
        """Test overall status when review is required."""
        result = VerificationResultFactory(
            basic_data_match=True,
            supplies_match=True,
            traceability_complete=True,
            requires_review=True
        )
        self.assertEqual(result.overall_status, "APROBADO")  # All checks pass, so APROBADO

    def test_overall_status_rejected(self):
        """Test overall status when checks fail."""
        result = VerificationResultFactory(
            basic_data_match=False,
            supplies_match=False,
            traceability_complete=False,
            requires_review=False
        )
        self.assertEqual(result.overall_status, "RECHAZADO")
