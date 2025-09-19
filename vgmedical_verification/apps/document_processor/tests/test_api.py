from django.test import TestCase
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APITestCase
from rest_framework import status
from unittest.mock import patch, Mock

from vgmedical_verification.users.tests.factories import UserFactory
from .factories import SurgicalCaseFactory, VerificationResultFactory


class TestCaseIngestAPI(APITestCase):

    def setUp(self):
        self.user = UserFactory()
        self.client.force_authenticate(user=self.user)
        self.ingest_url = reverse('api:document_processor:cases-ingest')

    def create_test_files(self):
        return {
            'internal': SimpleUploadedFile('internal.pdf', b'Internal content', content_type='application/pdf'),
            'hospital': SimpleUploadedFile('hospital.pdf', b'Hospital content', content_type='application/pdf'),
            'description': SimpleUploadedFile('description.pdf', b'Description content', content_type='application/pdf')
        }

    @patch('vgmedical_verification.apps.document_processor.api.views.document_processor.process_surgical_case_files')
    def test_ingest_case_success(self, mock_process_function):
        # Mock del resultado
        mock_case = SurgicalCaseFactory()
        mock_process_function.return_value = mock_case
        
        files = self.create_test_files()
        data = {**files, 'case_data': '{"patient_name": "Test Patient"}'}

        response = self.client.post(self.ingest_url, data, format='multipart')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('case_id', response.data)

    def test_ingest_case_missing_file(self):
        data = {'internal': SimpleUploadedFile('internal.pdf', b'content', content_type='application/pdf')}

        response = self.client.post(self.ingest_url, data, format='multipart')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class TestCaseReportAPI(APITestCase):

    def setUp(self):
        self.user = UserFactory()
        self.client.force_authenticate(user=self.user)
        self.case = SurgicalCaseFactory()
        self.verification = VerificationResultFactory(surgical_case=self.case)
        self.report_url = reverse('api:document_processor:cases-report', kwargs={'case_id': self.case.id})

    def test_get_case_report_success(self):
        response = self.client.get(self.report_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['case_id'], str(self.case.id))
        self.assertIn('verification_score', response.data)
