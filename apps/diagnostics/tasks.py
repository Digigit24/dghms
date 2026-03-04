"""
Celery tasks for the Diagnostics module.
Handles async import/export of Investigation records.
"""
import os

from celery import shared_task
from django.core.cache import cache
from django.utils import timezone


# ---------------------------------------------------------------------------
# Import task
# ---------------------------------------------------------------------------

@shared_task(bind=True, name='diagnostics.import_investigations')
def import_investigations_task(
    self,
    file_path: str,
    file_format: str,
    tenant_id: str,
    field_mapping: dict,
    skip_duplicates: bool = True,
    update_existing: bool = False,
):
    """
    Async task: read the temp file saved by preview_import, apply field_mapping,
    and bulk-create/update Investigation records.

    Progress is tracked in Django cache so the client can poll import_status.

    Args:
        file_path:       Absolute path to the temp upload file.
        file_format:     'xlsx' or 'csv'.
        tenant_id:       Tenant UUID string.
        field_mapping:   {model_field: excel_column_name} dict.
        skip_duplicates: If True, skip rows that already exist.
        update_existing: If True, update existing records (overrides skip_duplicates).
    """
    task_id = self.request.id
    _set(task_id, 'status', 'processing')
    _set(task_id, 'progress', 0)

    try:
        from .import_export import InvestigationImporter

        with open(file_path, 'rb') as fh:
            file_content = fh.read()

        def progress_cb(current: int, total: int):
            pct = int((current / total) * 100) if total > 0 else 0
            _set(task_id, 'progress', pct)

        importer = InvestigationImporter(
            tenant_id=tenant_id,
            field_mapping=field_mapping,
            skip_duplicates=skip_duplicates,
            update_existing=update_existing,
        )

        if file_format == 'xlsx':
            result = importer.import_from_xlsx(file_content, progress_cb)
        elif file_format == 'csv':
            result = importer.import_from_csv(file_content, progress_cb)
        else:
            result = {
                'success': False,
                'error': f'Unsupported format: {file_format}',
                'imported': 0, 'updated': 0, 'skipped': 0, 'errors': [],
            }

        _set(task_id, 'status', 'completed')
        _set(task_id, 'progress', 100)
        _set(task_id, 'result', result)
        return result

    except Exception as exc:
        err = {'success': False, 'error': str(exc), 'imported': 0, 'updated': 0, 'skipped': 0, 'errors': [str(exc)]}
        _set(task_id, 'status', 'failed')
        _set(task_id, 'result', err)
        raise  # Let Celery mark the task as FAILURE

    finally:
        # Always clean up the temp file
        try:
            os.remove(file_path)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Export task
# ---------------------------------------------------------------------------

@shared_task(bind=True, name='diagnostics.export_investigations')
def export_investigations_task(
    self,
    tenant_id: str,
    file_format: str,
    filters: dict = None,
):
    """
    Async task: export Investigation records to xlsx or csv.
    File bytes are cached; client downloads via download_export endpoint.

    Args:
        tenant_id:   Tenant UUID string.
        file_format: 'xlsx' or 'csv'.
        filters:     Optional dict with keys: category, is_active, search.
    """
    task_id = self.request.id
    _set(task_id, 'exp_status', 'processing')

    try:
        from .models import Investigation
        from .import_export import InvestigationExporter

        qs = Investigation.objects.filter(tenant_id=tenant_id).order_by('category', 'name')

        if filters:
            if 'category' in filters and filters['category']:
                qs = qs.filter(category=filters['category'])
            if 'is_active' in filters:
                qs = qs.filter(is_active=filters['is_active'])
            if 'search' in filters and filters['search']:
                qs = qs.filter(name__icontains=filters['search'])

        exporter = InvestigationExporter(qs)

        if file_format == 'xlsx':
            file_bytes = exporter.export_to_xlsx()
        elif file_format == 'csv':
            file_bytes = exporter.export_to_csv()
        else:
            raise ValueError(f'Unsupported format: {file_format}')

        cache_key = f'inv_export_{task_id}_file'
        cache.set(cache_key, file_bytes, timeout=3600)

        result = {
            'success': True,
            'total_records': qs.count(),
            'cache_key': cache_key,
            'file_format': file_format,
            'generated_at': timezone.now().isoformat(),
        }
        _set(task_id, 'exp_status', 'completed')
        _set(task_id, 'exp_result', result)
        return result

    except Exception as exc:
        err = {'success': False, 'error': str(exc)}
        _set(task_id, 'exp_status', 'failed')
        _set(task_id, 'exp_result', err)
        raise


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def _set(task_id: str, key: str, value, timeout: int = 3600):
    cache.set(f'inv_{key}_{task_id}', value, timeout=timeout)


def get_import_cache(task_id: str) -> dict:
    return {
        'status':   cache.get(f'inv_status_{task_id}'),
        'progress': cache.get(f'inv_progress_{task_id}', 0),
        'result':   cache.get(f'inv_result_{task_id}'),
    }


def get_export_cache(task_id: str) -> dict:
    return {
        'status': cache.get(f'inv_exp_status_{task_id}'),
        'result': cache.get(f'inv_exp_result_{task_id}'),
    }
