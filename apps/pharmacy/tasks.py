"""
Celery tasks for Pharmacy module
Handles async import/export operations
"""
from celery import shared_task
from django.core.cache import cache
from django.utils import timezone

from .models import PharmacyProduct
from .import_export import ProductImporter, ProductExporter


@shared_task(bind=True, name='pharmacy.import_products')
def import_products_task(self, file_content: bytes, file_format: str, tenant_id: str, skip_duplicates: bool = True):
    """
    Async task to import products from file

    Args:
        file_content: Binary file content
        file_format: 'csv', 'xlsx', or 'json'
        tenant_id: UUID of the tenant
        skip_duplicates: Whether to skip duplicate products

    Returns:
        dict: Import results with counts and errors
    """
    task_id = self.request.id

    # Update task progress
    cache.set(f'import_task_{task_id}_status', 'processing', timeout=3600)
    cache.set(f'import_task_{task_id}_progress', 0, timeout=3600)

    try:
        # Create importer
        importer = ProductImporter(tenant_id=tenant_id, skip_duplicates=skip_duplicates)

        # Import based on format
        if file_format == 'csv':
            result = importer.import_from_csv(file_content)
        elif file_format == 'xlsx':
            result = importer.import_from_xlsx(file_content)
        elif file_format == 'json':
            result = importer.import_from_json(file_content)
        else:
            result = {
                'success': False,
                'error': f'Unsupported file format: {file_format}',
                'imported': 0,
                'skipped': 0,
                'errors': []
            }

        # Update final status
        cache.set(f'import_task_{task_id}_status', 'completed', timeout=3600)
        cache.set(f'import_task_{task_id}_progress', 100, timeout=3600)
        cache.set(f'import_task_{task_id}_result', result, timeout=3600)

        return result

    except Exception as e:
        # Handle errors
        error_result = {
            'success': False,
            'error': str(e),
            'imported': 0,
            'skipped': 0,
            'errors': [str(e)]
        }

        cache.set(f'import_task_{task_id}_status', 'failed', timeout=3600)
        cache.set(f'import_task_{task_id}_result', error_result, timeout=3600)

        raise  # Re-raise for Celery to mark as failed


@shared_task(bind=True, name='pharmacy.export_products')
def export_products_task(self, tenant_id: str, file_format: str, filters: dict = None):
    """
    Async task to export products to file

    Args:
        tenant_id: UUID of the tenant
        file_format: 'csv', 'xlsx', or 'json'
        filters: Optional filters to apply to queryset

    Returns:
        bytes: File content
    """
    task_id = self.request.id

    # Update task progress
    cache.set(f'export_task_{task_id}_status', 'processing', timeout=3600)
    cache.set(f'export_task_{task_id}_progress', 0, timeout=3600)

    try:
        # Build queryset
        queryset = PharmacyProduct.objects.filter(tenant_id=tenant_id).select_related('category')

        # Apply filters if provided
        if filters:
            if 'is_active' in filters:
                queryset = queryset.filter(is_active=filters['is_active'])
            if 'category_id' in filters:
                queryset = queryset.filter(category_id=filters['category_id'])
            if 'company' in filters:
                queryset = queryset.filter(company__icontains=filters['company'])
            if 'search' in filters:
                queryset = queryset.filter(product_name__icontains=filters['search'])

        # Create exporter
        exporter = ProductExporter(queryset)

        # Export based on format
        if file_format == 'csv':
            file_content = exporter.export_to_csv()
        elif file_format == 'xlsx':
            file_content = exporter.export_to_xlsx()
        elif file_format == 'json':
            file_content = exporter.export_to_json()
        else:
            raise ValueError(f'Unsupported file format: {file_format}')

        # Store result in cache
        cache_key = f'export_task_{task_id}_file'
        cache.set(cache_key, file_content, timeout=3600)  # 1 hour

        # Update status
        cache.set(f'export_task_{task_id}_status', 'completed', timeout=3600)
        cache.set(f'export_task_{task_id}_progress', 100, timeout=3600)
        cache.set(f'export_task_{task_id}_result', {
            'success': True,
            'total_records': queryset.count(),
            'cache_key': cache_key,
            'file_format': file_format,
            'generated_at': timezone.now().isoformat()
        }, timeout=3600)

        return {
            'success': True,
            'cache_key': cache_key,
            'total_records': queryset.count()
        }

    except Exception as e:
        # Handle errors
        error_result = {
            'success': False,
            'error': str(e)
        }

        cache.set(f'export_task_{task_id}_status', 'failed', timeout=3600)
        cache.set(f'export_task_{task_id}_result', error_result, timeout=3600)

        raise  # Re-raise for Celery to mark as failed


@shared_task(name='pharmacy.update_search_vectors')
def update_search_vectors_task(tenant_id: str = None):
    """
    Update search vectors for all products (or specific tenant)
    Useful for bulk updates or migrations

    Args:
        tenant_id: Optional tenant UUID to update only specific tenant's products
    """
    from django.contrib.postgres.search import SearchVector

    queryset = PharmacyProduct.objects.all()
    if tenant_id:
        queryset = queryset.filter(tenant_id=tenant_id)

    # Bulk update search vectors
    queryset.update(
        search_vector=(
            SearchVector('product_name', weight='A', config='english') +
            SearchVector('company', weight='B', config='english') +
            SearchVector('batch_no', weight='C', config='english')
        )
    )

    return {
        'success': True,
        'updated_count': queryset.count(),
        'tenant_id': tenant_id
    }
