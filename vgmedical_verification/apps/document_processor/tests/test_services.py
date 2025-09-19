from django.test import TestCase
from django.core.files.base import ContentFile
from unittest.mock import patch, Mock

from vgmedical_verification.apps.document_processor.services.services import (
    DocumentProcessor, EquivalenceManager, process_surgical_case_files
)
from vgmedical_verification.users.tests.factories import UserFactory


class TestDocumentProcessor(TestCase):

    def setUp(self):
        self.processor = DocumentProcessor()
        self.user = UserFactory()

    def create_mock_files(self):
        return [
            {
                'file': ContentFile(b'Internal content', name='internal.pdf'),
                'document_type': 'internal',
                'case_data': {'patient_name': 'Test Patient'}
            },
            {
                'file': ContentFile(b'Hospital content', name='hospital.pdf'),
                'document_type': 'hospital',
                'case_data': {}
            },
            {
                'file': ContentFile(b'Description content', name='description.pdf'),
                'document_type': 'description',
                'case_data': {}
            }
        ]

    @patch('vgmedical_verification.apps.document_processor.services.services.DocumentParserFactory')
    def test_process_surgical_case_success(self, mock_parser_factory):
        mock_parser = Mock()
        mock_parser.parse_file.return_value = {
            'patient_name': 'Test Patient',
            'raw_text': 'Sample text',
            'supplies': [{'name': 'Test Supply', 'quantity': 1}]
        }
        mock_parser_factory.get_parser.return_value = mock_parser

        files_data = self.create_mock_files()

        with patch.object(self.processor.verification_engine, 'verify_case') as mock_verify:
            from .factories import VerificationResultFactory
            mock_verify.return_value = VerificationResultFactory()

            result = self.processor.process_surgical_case(files_data, self.user)
            self.assertIsNotNone(result)
            self.assertEqual(result.documents.count(), 3)


class TestEquivalenceManager(TestCase):

    def setUp(self):
        self.manager = EquivalenceManager()
        self.user = UserFactory()

    def test_add_equivalence_new(self):
        canonical = "tornillo encefalico 3.5x55mm"
        aliases = ["tornillo 3.5x55", "screw 3.5x55"]

        equivalence = self.manager.add_equivalence(canonical, aliases, self.user)

        self.assertEqual(equivalence.canonical_name, canonical.lower())
        self.assertEqual(len(equivalence.aliases), 2)
