from celery.result import AsyncResult
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from common.drf_auth import HMSPermission
from .import_export import (
    InvestigationExporter,
    InvestigationFilePreview,
    IMPORTABLE_FIELDS,
    save_temp_import_file,
)
from .models import (
    DiagnosticOrder, Investigation, InvestigationRange,
    LabReport, MedicineOrder, PackageOrder, ProcedureOrder, Requisition,
)
from .serializers import (
    DiagnosticOrderSerializer, InvestigationRangeSerializer,
    InvestigationSerializer, LabReportSerializer,
    MedicineOrderSerializer, PackageOrderSerializer,
    ProcedureOrderSerializer, RequisitionSerializer,
)
from .tasks import (
    export_investigations_task, get_export_cache, get_import_cache,
    import_investigations_task, set_cancel_flag,
)


# ---------------------------------------------------------------------------
# Investigation ViewSet (CRUD + import / export)
# ---------------------------------------------------------------------------

class InvestigationViewSet(viewsets.ModelViewSet):
    """
    CRUD for Investigation (master test list) plus async import/export.

    Import flow (two steps):
      1. POST  /investigations/preview_import/   – upload file, get column list
      2. POST  /investigations/start_import/     – send mapping, start Celery task

    Monitor:
      GET  /investigations/import_status/?task_id=<id>

    Export:
      GET  /investigations/export_investigations/?format=xlsx
      GET  /investigations/download_export/?task_id=<id>

    Template:
      GET  /investigations/import_template/
    """
    queryset = Investigation.objects.all()
    serializer_class = InvestigationSerializer
    permission_classes = [HMSPermission]
    hms_module = 'diagnostics'

    def get_queryset(self):
        qs = super().get_queryset()
        if hasattr(self.request, 'tenant_id'):
            qs = qs.filter(tenant_id=self.request.tenant_id)
        return qs

    # ------------------------------------------------------------------
    # Step 1 – Upload file → get columns + mapping suggestions
    # ------------------------------------------------------------------

    @action(
        detail=False,
        methods=['post'],
        url_path='preview_import',
        parser_classes=[MultiPartParser, FormParser],
    )
    def preview_import(self, request):
        """
        Upload an Excel/CSV file.
        Returns the detected column names, 5 sample rows, and auto-suggested
        field mapping so the user can confirm/adjust before importing.

        Body (multipart):
            file       – xlsx or csv file  (required)
            format     – 'xlsx' or 'csv'   (required)

        Response:
            {
              session_key,       ← pass this to start_import
              columns,           ← list of column names found in the file
              sample_rows,       ← first 5 data rows
              mapping_suggestions: {model_field: excel_column, …},
              importable_fields:  {model_field: {label, description}, …}
            }
        """
        file_format = request.data.get('format', '').lower()
        if file_format not in ('xlsx', 'csv'):
            return Response(
                {'success': False, 'error': 'format must be "xlsx" or "csv"'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if 'file' not in request.FILES:
            return Response(
                {'success': False, 'error': 'No file uploaded. Use the "file" field.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        file_bytes = request.FILES['file'].read()

        # Preview columns
        preview = InvestigationFilePreview.preview(file_bytes, file_format)
        if not preview.get('success'):
            return Response(preview, status=status.HTTP_400_BAD_REQUEST)

        # Save file to temp location; return a key so start_import can find it
        file_path = save_temp_import_file(file_bytes, file_format)

        return Response({
            'success': True,
            'session_key': file_path,   # opaque – frontend just passes it back
            'file_format': file_format,
            **preview,
        }, status=status.HTTP_200_OK)

    # ------------------------------------------------------------------
    # Step 2 – Submit mapping → kick off Celery task immediately
    # ------------------------------------------------------------------

    @action(detail=False, methods=['post'], url_path='start_import')
    def start_import(self, request):
        """
        Start the background import using the session_key from preview_import.

        Body (JSON):
            session_key      – value returned by preview_import  (required)
            file_format      – 'xlsx' or 'csv'                   (required)
            field_mapping    – {model_field: excel_column, …}    (required)
            skip_duplicates  – true/false (default true)
            update_existing  – true/false (default false)

        field_mapping example:
            {
              "name":          "TEST",
              "base_charge":   "PRICE",
              "specimen_type": "SPECIMEN TYPE",
              "reported_by":   "REPORTED",
              "category":      "CATEGORY"
            }

        All fields are optional – map only what you need.
        At least "name" or "code" must be mapped so records can be identified.

        Response (202 Accepted):
            { task_id, status_url }
        """
        session_key = request.data.get('session_key', '')
        file_format = request.data.get('file_format', '').lower()
        field_mapping = request.data.get('field_mapping', {})
        skip_duplicates = bool(request.data.get('skip_duplicates', True))
        update_existing = bool(request.data.get('update_existing', False))

        # Basic validation
        if not session_key:
            return Response(
                {'success': False, 'error': 'session_key is required (from preview_import).'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if file_format not in ('xlsx', 'csv'):
            return Response(
                {'success': False, 'error': 'file_format must be "xlsx" or "csv".'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not isinstance(field_mapping, dict) or not field_mapping:
            return Response(
                {'success': False, 'error': 'field_mapping must be a non-empty object.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate mapping keys
        unknown = [k for k in field_mapping if k not in IMPORTABLE_FIELDS]
        if unknown:
            return Response(
                {'success': False, 'error': f'Unknown model fields in mapping: {unknown}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Must map at least name or code
        if 'name' not in field_mapping and 'code' not in field_mapping:
            return Response(
                {'success': False, 'error': 'field_mapping must include at least "name" or "code".'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        import os
        if not os.path.exists(session_key):
            return Response(
                {'success': False, 'error': 'Upload session expired or invalid. Please re-upload.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Fire and forget – Celery picks it up immediately
        task = import_investigations_task.delay(
            file_path=session_key,
            file_format=file_format,
            tenant_id=str(request.tenant_id),
            field_mapping=field_mapping,
            skip_duplicates=skip_duplicates,
            update_existing=update_existing,
        )

        return Response({
            'success': True,
            'message': 'Import started in background. You can continue working.',
            'task_id': task.id,
            'status_url': f'/api/diagnostics/investigations/import_status/?task_id={task.id}',
        }, status=status.HTTP_202_ACCEPTED)

    # ------------------------------------------------------------------
    # Poll import progress
    # ------------------------------------------------------------------

    @action(detail=False, methods=['get'], url_path='import_status')
    def import_status(self, request):
        """
        Poll progress of a running import task.

        Query params:
            task_id – Celery task ID returned by start_import

        Response:
            { task_id, state, status, progress (0-100), result? }
        """
        task_id = request.query_params.get('task_id')
        if not task_id:
            return Response(
                {'success': False, 'error': 'task_id query param is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        celery_result = AsyncResult(task_id)
        cached = get_import_cache(task_id)

        data = {
            'success':     True,
            'task_id':     task_id,
            'state':       celery_result.state,
            'status':      cached['status'] or celery_result.state.lower(),
            'progress':    cached['progress'],
            # Live counters (update while task is running)
            'imported':    cached['imported'],
            'updated':     cached['updated'],
            'skipped':     cached['skipped'],
            # Current row being processed
            'current_row': cached['current_row'],
        }

        if celery_result.ready():
            if celery_result.successful():
                result = cached['result'] or celery_result.result
                data['result'] = result
                # Always mark as 'completed' when Celery says SUCCESS —
                # this covers both import tasks (which set inv_status cache)
                # and export tasks (which only set inv_exp_status cache).
                data['status'] = 'completed'
                data['progress'] = 100
                # When task is done, ensure top-level counters reflect final result
                # (live cache counters may still be 0 if task finished before first poll)
                if result and isinstance(result, dict):
                    data['imported'] = result.get('imported', data['imported'])
                    data['updated']  = result.get('updated',  data['updated'])
                    data['skipped']  = result.get('skipped',  data['skipped'])
            else:
                data['status'] = 'failed'
                data['error'] = str(celery_result.info)
        elif cached['result']:
            data['result'] = cached['result']

        return Response(data)

    # ------------------------------------------------------------------
    # Cancel a running import
    # ------------------------------------------------------------------

    @action(detail=False, methods=['post'], url_path='cancel_import')
    def cancel_import(self, request):
        """
        Signal a running import task to stop after the current row.

        Body (JSON):
            task_id – Celery task ID returned by start_import

        Response:
            { success, message }
        """
        task_id = request.data.get('task_id')
        if not task_id:
            return Response(
                {'success': False, 'error': 'task_id is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        celery_result = AsyncResult(task_id)
        if celery_result.ready():
            return Response(
                {'success': False, 'error': 'Task already finished, nothing to cancel.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        set_cancel_flag(task_id)
        return Response({
            'success': True,
            'message': 'Cancel signal sent. Import will stop after the current row.',
            'task_id': task_id,
        })

    # ------------------------------------------------------------------
    # Export – kick off async task
    # ------------------------------------------------------------------

    @action(detail=False, methods=['get'], url_path='export_investigations')
    def export_investigations(self, request):
        """
        Start an async export of investigations.

        Query params:
            file_format – 'xlsx' or 'csv'  (required)
            category    – filter by category slug  (optional)
            is_active   – 'true'/'false'            (optional)
            search      – name contains search term (optional)

        Response (202 Accepted):
            { task_id, status_url, download_url }
        """
        file_format = request.query_params.get('file_format', '').lower()
        if file_format not in ('xlsx', 'csv'):
            return Response(
                {'success': False, 'error': 'file_format must be "xlsx" or "csv".'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        filters = {}
        if 'category' in request.query_params:
            filters['category'] = request.query_params['category']
        if 'is_active' in request.query_params:
            filters['is_active'] = request.query_params['is_active'].lower() == 'true'
        if 'search' in request.query_params:
            filters['search'] = request.query_params['search']

        task = export_investigations_task.delay(
            tenant_id=str(request.tenant_id),
            file_format=file_format,
            filters=filters or None,
        )

        return Response({
            'success': True,
            'message': 'Export started in background.',
            'task_id': task.id,
            'status_url':   f'/api/diagnostics/investigations/import_status/?task_id={task.id}',
            'download_url': f'/api/diagnostics/investigations/download_export/?task_id={task.id}',
        }, status=status.HTTP_202_ACCEPTED)

    # ------------------------------------------------------------------
    # Download exported file
    # ------------------------------------------------------------------

    @action(detail=False, methods=['get'], url_path='download_export')
    def download_export(self, request):
        """
        Download a completed export file.

        Query params:
            task_id – from export_investigations response
        """
        task_id = request.query_params.get('task_id')
        if not task_id:
            return Response(
                {'success': False, 'error': 'task_id is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from django.core.cache import cache
        cached = get_export_cache(task_id)
        result = cached.get('result')

        if not result or not result.get('success'):
            return Response(
                {'success': False, 'error': 'Export not ready or failed. Check export status.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        file_bytes = cache.get(result['cache_key'])
        if not file_bytes:
            return Response(
                {'success': False, 'error': 'Export file expired. Please re-export.'},
                status=status.HTTP_410_GONE,
            )

        fmt = result.get('file_format', 'xlsx')
        content_type_map = {
            'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'csv':  'text/csv',
        }
        ext_map = {'xlsx': 'xlsx', 'csv': 'csv'}

        ts = timezone.now().strftime('%Y%m%d_%H%M%S')
        response = HttpResponse(file_bytes, content_type=content_type_map.get(fmt, 'application/octet-stream'))
        response['Content-Disposition'] = f'attachment; filename="investigations_{ts}.{ext_map.get(fmt, "bin")}"'
        return response

    # ------------------------------------------------------------------
    # Download blank template
    # ------------------------------------------------------------------

    @action(detail=False, methods=['get'], url_path='import_template')
    def import_template(self, request):
        """
        Download a pre-filled xlsx template showing the expected columns.
        Headers: TEST, PRICE, SPECIMEN TYPE, REPORTED, CATEGORY, CODE, DESCRIPTION, IS_ACTIVE
        """
        file_bytes = InvestigationExporter.build_template()
        response = HttpResponse(
            file_bytes,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response['Content-Disposition'] = 'attachment; filename="investigations_import_template.xlsx"'
        return response


# ---------------------------------------------------------------------------
# Remaining ViewSets (unchanged logic, just re-stated here for completeness)
# ---------------------------------------------------------------------------

class RequisitionViewSet(viewsets.ModelViewSet):
    queryset = Requisition.objects.all()
    serializer_class = RequisitionSerializer
    permission_classes = [HMSPermission]
    hms_module = 'diagnostics'

    def get_queryset(self):
        qs = super().get_queryset()
        if hasattr(self.request, 'tenant_id'):
            return qs.filter(tenant_id=self.request.tenant_id)
        return qs

    @action(detail=True, methods=['post'], url_path='add_medicine')
    def add_medicine(self, request, pk=None):
        requisition = self.get_object()
        if requisition.requisition_type != 'medicine':
            return Response(
                {'error': f'Requisition type is "{requisition.requisition_type}", not "medicine".'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        product_id = request.data.get('product_id')
        if not product_id:
            return Response({'error': 'product_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            from apps.pharmacy.models import PharmacyProduct
            product = PharmacyProduct.objects.get(id=product_id, tenant_id=request.tenant_id)
        except PharmacyProduct.DoesNotExist:
            return Response({'error': 'Product not found'}, status=status.HTTP_404_NOT_FOUND)

        medicine_order = MedicineOrder.objects.create(
            tenant_id=request.tenant_id,
            requisition=requisition,
            product=product,
            quantity=request.data.get('quantity', 1),
            price=request.data.get('price') or product.selling_price or product.mrp,
        )
        return Response(MedicineOrderSerializer(medicine_order).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='add_procedure')
    def add_procedure(self, request, pk=None):
        requisition = self.get_object()
        if requisition.requisition_type != 'procedure':
            return Response(
                {'error': f'Requisition type is "{requisition.requisition_type}", not "procedure".'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        procedure_id = request.data.get('procedure_id')
        if not procedure_id:
            return Response({'error': 'procedure_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            from apps.opd.models import ProcedureMaster
            procedure = ProcedureMaster.objects.get(id=procedure_id, tenant_id=request.tenant_id)
        except ProcedureMaster.DoesNotExist:
            return Response({'error': 'Procedure not found'}, status=status.HTTP_404_NOT_FOUND)

        procedure_order = ProcedureOrder.objects.create(
            tenant_id=request.tenant_id,
            requisition=requisition,
            procedure=procedure,
            quantity=request.data.get('quantity', 1),
            price=request.data.get('price') or procedure.default_charge,
        )
        return Response(ProcedureOrderSerializer(procedure_order).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='add_package')
    def add_package(self, request, pk=None):
        requisition = self.get_object()
        if requisition.requisition_type != 'package':
            return Response(
                {'error': f'Requisition type is "{requisition.requisition_type}", not "package".'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        package_id = request.data.get('package_id')
        if not package_id:
            return Response({'error': 'package_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            from apps.opd.models import ProcedurePackage
            package = ProcedurePackage.objects.get(id=package_id, tenant_id=request.tenant_id)
        except ProcedurePackage.DoesNotExist:
            return Response({'error': 'Package not found'}, status=status.HTTP_404_NOT_FOUND)

        package_order = PackageOrder.objects.create(
            tenant_id=request.tenant_id,
            requisition=requisition,
            package=package,
            quantity=request.data.get('quantity', 1),
            price=request.data.get('price') or package.discounted_charge,
        )
        return Response(PackageOrderSerializer(package_order).data, status=status.HTTP_201_CREATED)


class DiagnosticOrderViewSet(viewsets.ModelViewSet):
    queryset = DiagnosticOrder.objects.select_related('investigation', 'requisition__patient')
    serializer_class = DiagnosticOrderSerializer
    permission_classes = [HMSPermission]
    hms_module = 'diagnostics'

    def get_queryset(self):
        qs = super().get_queryset()
        if hasattr(self.request, 'tenant_id'):
            return qs.filter(tenant_id=self.request.tenant_id)
        return qs


class LabReportViewSet(viewsets.ModelViewSet):
    queryset = LabReport.objects.select_related('diagnostic_order__investigation', 'diagnostic_order__requisition__patient')
    serializer_class = LabReportSerializer
    permission_classes = [HMSPermission]
    parser_classes = [MultiPartParser, FormParser]
    hms_module = 'diagnostics'

    def get_queryset(self):
        qs = super().get_queryset()
        if hasattr(self.request, 'tenant_id'):
            return qs.filter(tenant_id=self.request.tenant_id)
        return qs


class InvestigationRangeViewSet(viewsets.ModelViewSet):
    queryset = InvestigationRange.objects.all()
    serializer_class = InvestigationRangeSerializer
    permission_classes = [HMSPermission]
    hms_module = 'diagnostics'

    def get_queryset(self):
        qs = super().get_queryset()
        if hasattr(self.request, 'tenant_id'):
            return qs.filter(tenant_id=self.request.tenant_id)
        return qs
