from django.urls import path
from vgmedical_verification.apps.document_processor.api.views.document_processor import (
    ingest_case_view, case_report_view, create_equivalence_view, suggest_equivalences_view
)

app_name = "document_processor"


urlpatterns = [
    path('cases/ingest/', ingest_case_view, name='cases-ingest'),
    path('cases/<uuid:case_id>/report/', case_report_view, name='cases-report'),
    path('equivalences/', create_equivalence_view, name='equivalences-create'),
    path('cases/<uuid:case_id>/suggest-equivalences/', suggest_equivalences_view, name='cases-suggest-equivalences'),
]
