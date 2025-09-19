# VG Medical – Verificación de Documentos Quirúrgicos

Solución en **Django + DRF** para:
- Ingerir **3 documentos** por cirugía (interno, hospital, descripción del médico).
- **Cruzar y verificar** datos básicos y **conciliar insumos** (con tolerancia a sinónimos y ruido).
- Validar **trazabilidad UDI** (REF/LOT/etiquetas) en el interno.
- Generar **reporte estructurado** (JSON) y un mecanismo de **aprendizaje** (equivalencias).

## Requisitos

- Docker y Docker Compose
- (Opcional) `httpie` o `curl` para probar endpoints

## Estructura relevante

```
vgmedical_verification/
  apps/
    document_processor/
      models.py
      parsers.py
      services.py
      api/
        views/document_processor.py
        serializers/document_processor.py
      urls.py
    verification/
      engine.py
  config/ (settings, urls del proyecto)
docker-compose.local.yml
```

> Las rutas exactas pueden variar, pero los comandos asumen un servicio `django` en `docker-compose.local.yml`.

---

## 1) Configuración de entorno

Crea tus variables de entorno (si no las tienes). Con cookiecutter-django normalmente hay `.envs/`:

```
.envs/
  .local/
    .django
    .postgres
```

Valores mínimos típicos:

**`.envs/.local/.django`**
```
DJANGO_DEBUG=True
DJANGO_SECRET_KEY=dev-secret-key
DJANGO_ALLOWED_HOSTS=*
DJANGO_SECURE_SSL_REDIRECT=False
```

**`.envs/.local/.postgres`**
```
POSTGRES_DB=vgmedical_local
POSTGRES_USER=debug
POSTGRES_PASSWORD=debug
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
```

> Si ya usas cookiecutter, probablemente ya están listos.

---

## 2) Levantar servicios

### 2.1 Build (sin cache para garantizar binarios limpios)
```bash
docker compose -f docker-compose.local.yml build --no-cache
```

### 2.2 Subir stack
```bash
docker compose -f docker-compose.local.yml up -d
```

Comprueba que los servicios `postgres`, `redis` (si aplica) y `django` están **healthy**:
```bash
docker compose -f docker-compose.local.yml ps
```

---

## 3) Migraciones y superusuario

### 3.1 Aplicar migraciones
```bash
docker compose -f docker-compose.local.yml run --rm django python manage.py migrate
```

### 3.2 (Opcional) Cargar fixtures de ejemplo
Si incluyes equivalencias base u otros datos:
```bash
docker compose -f docker-compose.local.yml run --rm django   python manage.py loaddata catalog/fixtures/items.json catalog/fixtures/synonyms.json
```

> Ajusta rutas si tus fixtures están en otro lugar.

### 3.3 Crear superusuario
```bash
docker compose -f docker-compose.local.yml run --rm django python manage.py createsuperuser
```

### 3.4 Acceso a admin
- URL: `http://localhost:8000/admin/`
- Usuario/clave: los que definiste en `createsuperuser`.

---

## 4) URLs de la API

Asegúrate de incluir las rutas del app en el `urls.py` del proyecto o usa el `urls.py` del app `document_processor`:

**Proyecto (`config/urls.py`), ejemplo:**
```python
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('vgmedical_verification.apps.document_processor.api.urls', namespace='document_processor')),
]
```

**Rutas del app (`vgmedical_verification/apps/document_processor/api/urls.py`):**
```python
from django.urls import path
from vgmedical_verification.apps.document_processor.api.views.document_processor import (
    ingest_case_view, case_report_view, create_equivalence_view, suggest_equivalences_view
)

app_name = "document_processor"

urlpatterns = [
    path('api/cases/ingest/', ingest_case_view, name='cases-ingest'),
    path('api/cases/<uuid:case_id>/report/', case_report_view, name='cases-report'),
    path('api/equivalences/', create_equivalence_view, name='equivalences-create'),
    path('api/cases/<uuid:case_id>/suggest-equivalences/', suggest_equivalences_view, name='cases-suggest-equivalences'),
]
```

---

## 5) Probar la ingesta y verificación

> Los endpoints requieren autenticación. Si tienes sesión de admin abierta, puedes usar **SessionAuth** desde el navegador o tokens según tu configuración.

### 5.1 Ingesta (3 documentos)
**Con `httpie`:**
```bash
http -a user:pass POST :8000/api/cases/ingest/   internal@/ruta/al/interno.pdf   hospital@/ruta/al/hospital.pdf   description@/ruta/a/la_descripcion.pdf   case_data:='{"patient_name":"Ana Diaz","doctor_name":"Dr. Lopez"}'
```

**Con `curl`:**
```bash
curl -u user:pass -X POST http://localhost:8000/api/cases/ingest/   -F internal=@/ruta/al/interno.pdf   -F hospital=@/ruta/al/hospital.pdf   -F description=@/ruta/a/la_descripcion.pdf   -F 'case_data={"patient_name":"Ana Diaz","doctor_name":"Dr. Lopez"}'
```

**Respuesta esperada (201):**
```json
{
  "case_id": "UUID",
  "case_number": "VG_20250919_123456_ab12cd34",
  "status": "processed"
}
```

### 5.2 Reporte del caso
```bash
http -a user:pass GET :8000/api/cases/<UUID>/report/
```

**Respuesta (200):** JSON con:
- `coincidencias_basicas` / `basic_data_verification`
- `supplies_verification`
- `traceability_verification`
- `discrepancies`, `verification_score`, `requires_review`, etc.

### 5.3 Mecanismo de aprendizaje (equivalencias)
```bash
http -a user:pass POST :8000/api/equivalences/   canonical_name="tornillo encefalico 3.5x55 mm"   aliases:='["tornillo 3.5x55","tornillo encefálico 3.5 × 55mm"]'
```

**Respuesta (201):** equivalencia creada/actualizada.

### 5.4 Sugerencias automáticas (opcional)
```bash
http -a user:pass GET :8000/api/cases/<UUID>/suggest-equivalences/
```

---

## 6) Correr tests

Si usas **pytest**:
```bash
docker compose -f docker-compose.local.yml run --rm django pytest -q
```

Si usas **unittest**:
```bash
docker compose -f docker-compose.local.yml run --rm django python manage.py test
```

---

## 7) Paquetes clave

Asegúrate de tener en `requirements`:
```
Django
djangorestframework
rapidfuzz>=3.0.0
PyPDF2
pillow
pytesseract         # si vas a usar OCR
python-dateutil     # opcional para fechas
```

> **OCR:** para usar `pytesseract` en Docker, agrega al Dockerfile:
> ```
> apt-get update && apt-get install -y tesseract-ocr tesseract-ocr-spa
> ```
> Si el PDF no tiene texto embebido, el sistema lo avisa con un **warning**; el OCR es un **mejora opcional** en esta entrega.

---

## 8) Troubleshooting

- **`OperationalError: could not connect to server`**  
  Asegura que `postgres` esté arriba:  
  `docker compose -f docker-compose.local.yml ps`  
  Reinicia `django`:  
  `docker compose -f docker-compose.local.yml up -d --build`

- **OCR no disponible**  
  Si no instalaste Tesseract, los PDFs con solo imágenes no extraerán texto. Para la entrega, se simula parsing sobre texto embebido. Deja OCR como **stretch goal** documentado.

- **Streams vacíos al parsear**  
  La ingesta ya **parsea antes de guardar** y usa `seek(0)`. Si cambias este orden, volverán los vacíos.

- **Equivalencias no aplican**  
  Verifica que los **aliases** estén normalizados y que el **umbral** (`rapidfuzz`) sea suficiente. Puedes ajustar umbrales en `settings` si fue expuesto ahí.

---

## 9) Roadmap corto

- Añadir OCR completo para PDFs escaneados.
- Endpoint de **feedback** por insumo (aceptar/rechazar match y crear equivalencia).
- Exportar reporte en **CSV** adicional al JSON.
- Integración con **Odoo** (adapter).

---

## 10) Licencia

Este proyecto se entrega como parte de una prueba técnica. Uso interno/demo.
