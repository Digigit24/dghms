"""
Import/Export utilities for Investigations.

Two-step import flow:
  1. POST preview_import  → upload file, get columns + mapping suggestions
  2. POST start_import    → submit field_mapping, Celery processes the saved file

Export flow:
  1. GET export_investigations → Celery builds file, returns task_id
  2. GET download_export?task_id=xxx → stream file to client
"""
import csv
import io
import os
import uuid
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from django.conf import settings

from .models import Investigation


# ---------------------------------------------------------------------------
# Field registry – what model fields can be mapped from an Excel column
# ---------------------------------------------------------------------------

IMPORTABLE_FIELDS: Dict[str, Dict[str, str]] = {
    'name':          {'label': 'TEST / Test Name',      'description': 'Name of the investigation'},
    'base_charge':   {'label': 'PRICE / Charge',        'description': 'Base charge / price for the test'},
    'specimen_type': {'label': 'SPECIMEN TYPE',         'description': 'Type of specimen (Blood, Urine, etc.)'},
    'reported_by':   {'label': 'REPORTED / Reported By','description': 'Who reports this test'},
    'category':      {'label': 'CATEGORY',              'description': 'Test category (Haematology, Clinical Chemistry …)'},
    'code':          {'label': 'CODE / Test Code',      'description': 'Short unique code (auto-generated if blank)'},
    'description':   {'label': 'DESCRIPTION',           'description': 'Additional test description'},
    'is_active':     {'label': 'IS ACTIVE',             'description': 'true / false (default: true)'},
}

# ---------------------------------------------------------------------------
# Category normalisation – accept any reasonable spelling from Excel
# ---------------------------------------------------------------------------

CATEGORY_MAP: Dict[str, str] = {
    'haematology':        'haematology',
    'hematology':         'haematology',
    'haemo':              'haematology',
    'hemo':               'haematology',
    'blood':              'haematology',
    'clinical chemistry': 'clinical_chemistry',
    'clinical_chemistry': 'clinical_chemistry',
    'clin chem':          'clinical_chemistry',
    'biochemistry':       'biochemistry',
    'biochem':            'biochemistry',
    'microbiology':       'microbiology',
    'micro':              'microbiology',
    'serology':           'serology',
    'sero':               'serology',
    'immunology':         'immunology',
    'immuno':             'immunology',
    'histopathology':     'histopathology',
    'histopath':          'histopathology',
    'cytology':           'cytology',
    'cyto':               'cytology',
    'genetics':           'genetics',
    'molecular biology':  'molecular_biology',
    'molecular_biology':  'molecular_biology',
    'mol bio':            'molecular_biology',
    'blood bank':         'blood_bank',
    'blood_bank':         'blood_bank',
    'toxicology':         'toxicology',
    'tox':                'toxicology',
    'endocrinology':      'endocrinology',
    'endo':               'endocrinology',
    'radiology':          'radiology',
    'radio':              'radiology',
    'ultrasound':         'ultrasound',
    'usg':                'ultrasound',
    'echo':               'ultrasound',
    'ct scan':            'ct_scan',
    'ct_scan':            'ct_scan',
    'ct':                 'ct_scan',
    'mri':                'mri',
    'xray':               'xray',
    'x-ray':              'xray',
    'x ray':              'xray',
    'ecg':                'ecg',
    'ekg':                'ecg',
    'cardiology':         'cardiology',
    'cardio':             'cardiology',
    'pathology':          'pathology',
    'path':               'pathology',
    'laboratory':         'laboratory',
    'lab':                'laboratory',
    'other':              'other',
}


# ---------------------------------------------------------------------------
# File preview – step 1 of the import flow
# ---------------------------------------------------------------------------

class InvestigationFilePreview:
    """
    Parse an uploaded file and return column names + sample rows
    so the frontend can render a mapping UI.
    """

    MAX_SAMPLE_ROWS = 5

    @classmethod
    def preview(cls, file_content: bytes, file_format: str) -> Dict[str, Any]:
        if file_format == 'xlsx':
            return cls._preview_xlsx(file_content)
        elif file_format == 'csv':
            return cls._preview_csv(file_content)
        return {'success': False, 'error': f'Unsupported format: {file_format}'}

    @classmethod
    def _preview_xlsx(cls, file_content: bytes) -> Dict[str, Any]:
        try:
            df = pd.read_excel(io.BytesIO(file_content), nrows=cls.MAX_SAMPLE_ROWS)
            columns = list(df.columns)
            sample = df.fillna('').to_dict('records')
            return {
                'success': True,
                'columns': columns,
                'sample_rows': sample,
                'total_columns': len(columns),
                'mapping_suggestions': cls._suggest_mapping(columns),
                'importable_fields': IMPORTABLE_FIELDS,
            }
        except Exception as exc:
            return {'success': False, 'error': f'Excel read error: {exc}'}

    @classmethod
    def _preview_csv(cls, file_content: bytes) -> Dict[str, Any]:
        try:
            text = file_content.decode('utf-8-sig')
            reader = csv.DictReader(io.StringIO(text))
            columns = list(reader.fieldnames or [])
            sample = []
            for i, row in enumerate(reader):
                if i >= cls.MAX_SAMPLE_ROWS:
                    break
                sample.append(dict(row))
            return {
                'success': True,
                'columns': columns,
                'sample_rows': sample,
                'total_columns': len(columns),
                'mapping_suggestions': cls._suggest_mapping(columns),
                'importable_fields': IMPORTABLE_FIELDS,
            }
        except Exception as exc:
            return {'success': False, 'error': f'CSV read error: {exc}'}

    @staticmethod
    def _suggest_mapping(columns: List[str]) -> Dict[str, str]:
        """
        Auto-suggest {model_field: excel_column} by matching common synonyms.
        All suggestions are optional – the user can override them.
        """
        col_lower: Dict[str, str] = {c.lower().strip(): c for c in columns}

        HINTS: Dict[str, List[str]] = {
            'name':          ['test', 'test name', 'name', 'investigation', 'investigation name', 'test_name'],
            'base_charge':   ['price', 'charge', 'base charge', 'base_charge', 'mrp', 'cost', 'amount', 'rate', 'fees'],
            'specimen_type': ['specimen', 'specimen type', 'specimen_type', 'sample', 'sample type'],
            'reported_by':   ['reported', 'reported by', 'reported_by', 'reporter', 'reporting by', 'reporting'],
            'category':      ['category', 'department', 'dept', 'section', 'type', 'test type', 'lab type'],
            'code':          ['code', 'test code', 'test_code', 'investigation code', 'short code'],
            'description':   ['description', 'desc', 'details', 'notes'],
            'is_active':     ['is active', 'is_active', 'active', 'status', 'enabled'],
        }

        suggestions: Dict[str, str] = {}
        for field, hints in HINTS.items():
            for hint in hints:
                if hint in col_lower:
                    suggestions[field] = col_lower[hint]
                    break
        return suggestions


# ---------------------------------------------------------------------------
# Importer – step 2 of the import flow (called inside Celery task)
# ---------------------------------------------------------------------------

class InvestigationImporter:
    """
    Import investigations from a file using a caller-supplied field mapping.

    field_mapping: {model_field: excel_column_name}
    e.g. {'name': 'TEST', 'base_charge': 'PRICE', 'category': 'CATEGORY'}
    """

    def __init__(
        self,
        tenant_id: str,
        field_mapping: Dict[str, str],
        skip_duplicates: bool = True,
        update_existing: bool = False,
    ):
        self.tenant_id = tenant_id
        self.field_mapping = field_mapping          # {model_field → excel_column}
        self.skip_duplicates = skip_duplicates
        self.update_existing = update_existing

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------

    def import_from_xlsx(self, file_content: bytes, progress_cb=None, row_cb=None, cancel_check=None) -> Dict[str, Any]:
        try:
            df = pd.read_excel(io.BytesIO(file_content))
            rows = df.fillna('').to_dict('records')
            return self._process_rows(rows, progress_cb, row_cb, cancel_check)
        except Exception as exc:
            return self._error_result(f'Excel parsing error: {exc}')

    def import_from_csv(self, file_content: bytes, progress_cb=None, row_cb=None, cancel_check=None) -> Dict[str, Any]:
        try:
            text = file_content.decode('utf-8-sig')
            rows = list(csv.DictReader(io.StringIO(text)))
            return self._process_rows(rows, progress_cb, row_cb, cancel_check)
        except Exception as exc:
            return self._error_result(f'CSV parsing error: {exc}')

    # ------------------------------------------------------------------
    # Core processing
    # ------------------------------------------------------------------

    def _process_rows(self, rows: List[Dict], progress_cb=None, row_cb=None, cancel_check=None) -> Dict[str, Any]:
        imported = updated = skipped = 0
        errors: List[str] = []
        total = len(rows)
        cancelled = False

        for idx, raw_row in enumerate(rows, start=1):
            # Check cancel flag before processing each row
            if cancel_check and cancel_check():
                cancelled = True
                break

            if progress_cb:
                progress_cb(idx, total)

            mapped = self._extract(raw_row)
            if not mapped:
                errors.append(f'Row {idx}: No mapped fields found – check your field mapping.')
                skipped += 1
                action = 'error'
                name = f'Row {idx}'
                if row_cb:
                    row_cb(idx, total, name, action, imported, updated, skipped)
                continue

            clean, row_errors = self._clean(mapped, idx)
            if row_errors:
                errors.extend(row_errors)

            name = clean.get('name') or clean.get('code') or f'Row {idx}'

            # At least name or code must survive cleaning
            if not clean.get('name') and not clean.get('code'):
                errors.append(f'Row {idx}: "name" or "code" is required.')
                skipped += 1
                if row_cb:
                    row_cb(idx, total, name, 'error', imported, updated, skipped)
                continue

            try:
                existing = self._find_existing(clean)
                if existing:
                    if self.update_existing:
                        self._update_investigation(existing, clean)
                        updated += 1
                        action = 'updated'
                    elif self.skip_duplicates:
                        errors.append(f'Row {idx}: Already exists – skipped (name/code match).')
                        skipped += 1
                        action = 'skipped'
                    else:
                        self._create_investigation(clean)
                        imported += 1
                        action = 'imported'
                else:
                    self._create_investigation(clean)
                    imported += 1
                    action = 'imported'
            except Exception as exc:
                errors.append(f'Row {idx}: DB error – {exc}')
                skipped += 1
                action = 'error'

            if row_cb:
                row_cb(idx, total, name, action, imported, updated, skipped)

        return {
            'success': (imported + updated) > 0 or total == 0,
            'imported': imported,
            'updated': updated,
            'skipped': skipped,
            'total_rows': total,
            'cancelled': cancelled,
            'processed_rows': imported + updated + skipped,
            'errors': errors,
        }

    def _extract(self, raw_row: Dict) -> Dict[str, Any]:
        """Pull only the mapped columns from raw_row."""
        data: Dict[str, Any] = {}
        for field, column in self.field_mapping.items():
            if column and column in raw_row:
                data[field] = raw_row[column]
        return data

    def _clean(self, data: Dict[str, Any], row_num: int) -> Tuple[Dict[str, Any], List[str]]:
        """Normalise and validate values; return (cleaned_dict, errors)."""
        clean: Dict[str, Any] = {}
        errors: List[str] = []

        for field, raw in data.items():
            # Treat pandas floats that represent NaN as empty
            if raw == '' or raw is None:
                continue

            if field == 'base_charge':
                try:
                    clean['base_charge'] = Decimal(str(raw))
                except (InvalidOperation, ValueError):
                    errors.append(f'Row {row_num}: Invalid price "{raw}" – defaulting to 0.')
                    clean['base_charge'] = Decimal('0.00')

            elif field == 'category':
                clean['category'] = CATEGORY_MAP.get(str(raw).lower().strip(), 'other')

            elif field == 'is_active':
                clean['is_active'] = str(raw).lower().strip() in ('true', '1', 'yes', 'y', 'active')

            else:
                clean[field] = str(raw).strip()

        return clean, errors

    def _find_existing(self, clean: Dict) -> Optional[Investigation]:
        if clean.get('code'):
            obj = Investigation.objects.filter(
                tenant_id=self.tenant_id,
                code=clean['code'],
            ).first()
            if obj:
                return obj
        if clean.get('name'):
            return Investigation.objects.filter(
                tenant_id=self.tenant_id,
                name__iexact=clean['name'],
            ).first()
        return None

    def _create_investigation(self, clean: Dict):
        code = clean.get('code') or self._make_code(clean.get('name', ''))
        code = self._unique_code(code)
        Investigation.objects.create(
            tenant_id=self.tenant_id,
            name=clean.get('name', ''),
            code=code,
            category=clean.get('category', 'other'),
            base_charge=clean.get('base_charge', Decimal('0.00')),
            specimen_type=clean.get('specimen_type', ''),
            reported_by=clean.get('reported_by', ''),
            description=clean.get('description', ''),
            is_active=clean.get('is_active', True),
        )

    @staticmethod
    def _update_investigation(obj: Investigation, clean: Dict):
        for field in ('name', 'category', 'base_charge', 'specimen_type',
                      'reported_by', 'description', 'is_active'):
            if field in clean:
                setattr(obj, field, clean[field])
        obj.save()

    def _unique_code(self, base: str) -> str:
        code = base
        suffix = 1
        while Investigation.objects.filter(tenant_id=self.tenant_id, code=code).exists():
            code = f'{base}_{suffix}'
            suffix += 1
        return code

    @staticmethod
    def _make_code(name: str) -> str:
        if not name:
            return f'INV{uuid.uuid4().hex[:6].upper()}'
        words = name.upper().split()
        if len(words) == 1:
            return words[0][:10]
        return ''.join(w[0] for w in words[:6])

    @staticmethod
    def _error_result(msg: str) -> Dict[str, Any]:
        return {'success': False, 'error': msg, 'imported': 0, 'updated': 0, 'skipped': 0, 'errors': [msg]}


# ---------------------------------------------------------------------------
# Exporter
# ---------------------------------------------------------------------------

class InvestigationExporter:
    """Export an Investigation queryset to xlsx or csv."""

    EXPORT_FIELDS = [
        'id', 'name', 'code', 'category',
        'base_charge', 'specimen_type', 'reported_by',
        'description', 'is_active',
    ]

    def __init__(self, queryset):
        self.queryset = queryset

    def export_to_xlsx(self) -> bytes:
        data = [self._row(inv) for inv in self.queryset]
        df = pd.DataFrame(data, columns=self.EXPORT_FIELDS)
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='Investigations')
        buf.seek(0)
        return buf.getvalue()

    def export_to_csv(self) -> bytes:
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=self.EXPORT_FIELDS, extrasaction='ignore')
        writer.writeheader()
        for inv in self.queryset:
            writer.writerow(self._row(inv))
        return buf.getvalue().encode('utf-8')

    def _row(self, inv: Investigation) -> Dict[str, Any]:
        return {
            'id':            inv.id,
            'name':          inv.name,
            'code':          inv.code,
            'category':      inv.category,
            'base_charge':   float(inv.base_charge),
            'specimen_type': inv.specimen_type,
            'reported_by':   inv.reported_by,
            'description':   inv.description,
            'is_active':     inv.is_active,
        }

    @staticmethod
    def build_template() -> bytes:
        """Return a ready-to-fill xlsx template with sample rows."""
        sample = [
            {
                'TEST':          'Complete Blood Count',
                'PRICE':         150.00,
                'SPECIMEN TYPE': 'Blood (EDTA)',
                'REPORTED':      'Pathologist',
                'CATEGORY':      'Haematology',
                'CODE':          'CBC',
                'DESCRIPTION':   'Full haematological profile',
                'IS_ACTIVE':     'true',
            },
            {
                'TEST':          'Blood Glucose Fasting',
                'PRICE':         80.00,
                'SPECIMEN TYPE': 'Blood (Serum)',
                'REPORTED':      'Biochemist',
                'CATEGORY':      'Clinical Chemistry',
                'CODE':          'BGF',
                'DESCRIPTION':   'Fasting blood sugar test',
                'IS_ACTIVE':     'true',
            },
            {
                'TEST':          'Urine Routine',
                'PRICE':         60.00,
                'SPECIMEN TYPE': 'Urine',
                'REPORTED':      'Lab Technician',
                'CATEGORY':      'Microbiology',
                'CODE':          'URN',
                'DESCRIPTION':   'Routine urine examination',
                'IS_ACTIVE':     'true',
            },
        ]
        df = pd.DataFrame(sample)
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='Template')
            # Auto-fit columns
            ws = writer.sheets['Template']
            for i, col in enumerate(df.columns):
                ws.set_column(i, i, max(len(col) + 4, 20))
        buf.seek(0)
        return buf.getvalue()


# ---------------------------------------------------------------------------
# Temp-file helpers (used between preview and actual import)
# ---------------------------------------------------------------------------

def save_temp_import_file(file_content: bytes, file_format: str) -> str:
    """
    Save uploaded file to a temp location and return its path.
    The Celery task will read this path, then delete it.
    """
    tmp_dir = os.path.join(settings.MEDIA_ROOT, 'diagnostics', 'temp_imports')
    os.makedirs(tmp_dir, exist_ok=True)
    file_name = f'{uuid.uuid4().hex}.{file_format}'
    file_path = os.path.join(tmp_dir, file_name)
    with open(file_path, 'wb') as fh:
        fh.write(file_content)
    return file_path
