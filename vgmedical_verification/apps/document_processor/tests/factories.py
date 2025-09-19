import factory
from factory.django import DjangoModelFactory
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.utils import timezone
from datetime import date, timedelta
import json

from vgmedical_verification.apps.document_processor.models import (
    SurgicalCase, Document, Supply, SupplyEquivalence, VerificationResult,
    DocumentType, DocumentStatus
)

User = get_user_model()


class UserFactory(DjangoModelFactory):
    class Meta:
        model = User

    email = factory.Sequence(lambda n: f"user{n}@example.com")
    full_name = factory.Faker('name')


class SurgicalCaseFactory(DjangoModelFactory):
    class Meta:
        model = SurgicalCase

    case_number = factory.Sequence(lambda n: f"VG_{timezone.now().strftime('%Y%m%d')}_{n:04d}")
    patient_name = factory.Faker('name', locale='es_ES')
    patient_id = factory.Faker('random_number', digits=10)
    surgery_date = factory.LazyFunction(lambda: date.today() - timedelta(days=1))
    city = factory.Faker('city', locale='es_ES')
    doctor_name = factory.Sequence(lambda n: f"Dr. García {n}")
    procedure = factory.Iterator([
        'Osteosíntesis de fractura de tibia',
        'Artrodesis lumbar L4-L5',
        'Fijación de fractura de fémur'
    ])


class DocumentFactory(DjangoModelFactory):
    class Meta:
        model = Document

    surgical_case = factory.SubFactory(SurgicalCaseFactory)
    document_type = DocumentType.INTERNAL
    status = DocumentStatus.PROCESSED
    file = factory.LazyAttribute(
        lambda obj: ContentFile(
            f"Documento simulado para {obj.document_type}",
            name=f"document_{obj.document_type}.pdf"
        )
    )
    extracted_text = factory.LazyAttribute(
        lambda obj: f"Texto extraído del documento {obj.document_type}")
    extracted_patient_name = factory.LazyAttribute(lambda obj: obj.surgical_case.patient_name)
    extracted_patient_id = factory.LazyAttribute(lambda obj: obj.surgical_case.patient_id)
    extracted_date = factory.LazyAttribute(lambda obj: obj.surgical_case.surgery_date)
    processed_at = factory.LazyFunction(timezone.now)


class SupplyFactory(DjangoModelFactory):
    class Meta:
        model = Supply

    document = factory.SubFactory(DocumentFactory)
    name = factory.Iterator([
        'Tornillo encefálico 3.5x55mm',
        'Placa de titanio curva 4 agujeros',
        'Pin de Steinmann 2.0mm',
        'Tornillo canulado 7.3mm'
    ])
    quantity = factory.Faker('random_int', min=1, max=5)
    ref_code = factory.Faker('bothify', text='REF##??###')
    lot_code = factory.Faker('bothify', text='LOT##??###')
    udi_label_present = True


class SupplyEquivalenceFactory(DjangoModelFactory):
    class Meta:
        model = SupplyEquivalence

    canonical_name = factory.Iterator([
        'tornillo encefalico 3.5x55mm',
        'placa titanio curva 4 agujeros',
        'pin steinmann 2.0mm'
    ])
    aliases = factory.LazyAttribute(
        lambda obj: [
            obj.canonical_name,
            obj.canonical_name.replace(' ', '_'),
            obj.canonical_name.upper()
        ]
    )
    confidence_score = factory.Faker('pyfloat', min_value=0.8, max_value=1.0, right_digits=2)


class VerificationResultFactory(DjangoModelFactory):
    class Meta:
        model = VerificationResult

    surgical_case = factory.SubFactory(SurgicalCaseFactory)
    basic_data_match = True
    supplies_match = True
    traceability_complete = True
    requires_review = False
    verification_score = factory.Faker('pyfloat', min_value=85.0, max_value=100.0, right_digits=2)
    basic_data_details = factory.LazyFunction(lambda: {'match': True, 'match_percentage': 95.0})
    supplies_details = factory.LazyFunction(lambda: {'match': True, 'match_percentage': 90.0})
    traceability_details = factory.LazyFunction(lambda: {'complete': True, 'completion_percentage': 100.0})
    discrepancies = factory.List([])
