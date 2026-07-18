# opd/views.py
from django.db.models import Q, Count, Sum, Avg, F
from django.utils import timezone
from django.db import transaction
from datetime import date, timedelta
from decimal import Decimal

import structlog

from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
import django_filters

from common.drf_auth import HMSPermission, HMSPermissionAllowOwnView, IsAuthenticated
from common.mixins import TenantViewSetMixin
from common import permission_evaluator
from .filters import VisitFilter
from .services.stats import (
    compute_bill_statistics,
    compute_doctor_stats,
    compute_visit_daily_trend,
    compute_visit_statistics,
)
from common.cache import CeliyoCache
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

from drf_spectacular.utils import (
    extend_schema,
    extend_schema_view,
    OpenApiParameter,
    OpenApiResponse
)

from .models import (
    ClinicalNote, Visit, OPDBill, ProcedureMaster, ProcedurePackage, Service,
    VisitFinding, VisitAttachment, OPDBillItem,
    ClinicalNoteTemplateGroup, ClinicalNoteTemplate,
    ClinicalNoteTemplateField, ClinicalNoteTemplateFieldOption,
    ClinicalNoteTemplateResponse, ClinicalNoteTemplateFieldResponse,
    ClinicalNoteResponseTemplate
)
from .serializers import (
    VisitListSerializer, VisitDetailSerializer, VisitCreateUpdateSerializer,
    VisitSetFollowUpSerializer,
    OPDBillListSerializer, OPDBillDetailSerializer, OPDBillCreateUpdateSerializer, OPDBillItemSerializer,
    ProcedureMasterListSerializer, ProcedureMasterDetailSerializer,
    ProcedureMasterCreateUpdateSerializer,
    ServiceListSerializer, ServiceDetailSerializer, ServiceCreateUpdateSerializer,
    ProcedurePackageListSerializer, ProcedurePackageDetailSerializer,
    ProcedurePackageCreateUpdateSerializer,

    ClinicalNoteListSerializer, ClinicalNoteDetailSerializer,
    ClinicalNoteCreateUpdateSerializer,
    VisitFindingListSerializer, VisitFindingDetailSerializer,
    VisitFindingCreateUpdateSerializer,
    VisitAttachmentListSerializer, VisitAttachmentDetailSerializer,
    VisitAttachmentCreateUpdateSerializer,
    OPDBillStatisticsSerializer,
    ClinicalNoteTemplateGroupListSerializer, ClinicalNoteTemplateGroupDetailSerializer,
    ClinicalNoteTemplateGroupCreateUpdateSerializer,
    ClinicalNoteTemplateListSerializer, ClinicalNoteTemplateDetailSerializer,
    ClinicalNoteTemplateCreateUpdateSerializer,
    ClinicalNoteTemplateFieldListSerializer, ClinicalNoteTemplateFieldDetailSerializer,
    ClinicalNoteTemplateFieldCreateUpdateSerializer,
    ClinicalNoteTemplateFieldOptionSerializer,
    ClinicalNoteTemplateResponseListSerializer, ClinicalNoteTemplateResponseDetailSerializer,
    ClinicalNoteTemplateResponseCreateUpdateSerializer,
    ClinicalNoteTemplateFieldResponseSerializer,
    ClinicalNoteTemplateFieldResponseCreateUpdateSerializer,
    ClinicalNoteResponseTemplateDetailSerializer
)


log = structlog.get_logger(__name__)


def _own_doctor_profile(request):
    """Resolve the caller's tenant-scoped DoctorProfile, if one exists."""
    from apps.doctors.models import DoctorProfile

    try:
        return DoctorProfile.objects.filter(
            tenant_id=request.tenant_id,
            user_id=request.user_id,
        ).first()
    except ValueError:
        return None


def _invalidate_today_cache(tenant_id):
    """Best-effort invalidation; Redis outages must not fail OPD writes."""
    try:
        CeliyoCache().delete_pattern(f"opd:today:{tenant_id}")
    except Exception as exc:
        log.warning(
            "opd_today_cache_bust_failed",
            tenant_id=str(tenant_id),
            error=str(exc),
        )


# ============================================================================
# HMS PERMISSION CONFIGURATION FOR OPD MODULE
# Uses JWT-based permissions from auth backend
# ============================================================================


# ============================================================================
# VISIT VIEWSET
# ============================================================================

@extend_schema_view(
    list=extend_schema(
        summary="List OPD Visits",
        description="Get paginated list of OPD visits with filtering and search",
        parameters=[
            OpenApiParameter(name='patient', type=int, description='Filter by patient ID'),
            OpenApiParameter(name='doctor', type=int, description='Filter by doctor ID'),
            OpenApiParameter(name='status', type=str, description='Filter by status'),
            OpenApiParameter(name='payment_status', type=str, description='Filter by payment status'),
            OpenApiParameter(name='visit_type', type=str, description='Filter by visit type'),
            OpenApiParameter(name='visit_date', type=str, description='Filter by visit date (YYYY-MM-DD)'),
            OpenApiParameter(name='follow_up_required', type=bool, description='Filter visits requiring follow-up'),
            OpenApiParameter(name='follow_up_date_from', type=str, description='Follow-up date on or after (YYYY-MM-DD)'),
            OpenApiParameter(name='follow_up_date_to', type=str, description='Follow-up date on or before (YYYY-MM-DD)'),
            OpenApiParameter(name='search', type=str, description='Search by visit number or patient name'),
        ],
        tags=['OPD - Visits']
    ),
    retrieve=extend_schema(
        summary="Get Visit Details",
        description="Retrieve detailed information about a specific visit",
        tags=['OPD - Visits']
    ),
    create=extend_schema(
        summary="Create Visit",
        description="Create a new OPD visit (Receptionist, Doctor, Admin)",
        tags=['OPD - Visits']
    ),
    update=extend_schema(
        summary="Update Visit",
        description="Update visit details (Receptionist, Doctor, Admin)",
        tags=['OPD - Visits']
    ),
    partial_update=extend_schema(
        summary="Partial Update Visit",
        description="Partially update visit details",
        tags=['OPD - Visits']
    )
)
class VisitViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    """
    OPD Visit Management

    Handles patient visits, queue management, and visit workflow.
    Uses JWT-based HMS permissions from the auth backend.
    """
    queryset = Visit.objects.select_related(
        'patient', 'doctor', 'appointment', 'referred_by'
    ).prefetch_related(
         'findings', 'attachments'
    )
    permission_classes = [HMSPermissionAllowOwnView]
    hms_module = 'opd'  # Maps to permissions.hms.opd in JWT

    # Action → HMS permission name mapping.
    # Keys must match PERMISSION_SCHEMA hms.opd actions in constants.py:
    # view, create, edit, delete, export, consult, bill, settings
    action_permission_map = {
        'list': 'view',
        'retrieve': 'view',
        'create': 'create',
        'update': 'edit',
        'partial_update': 'edit',
        'set_follow_up': 'edit',
        'destroy': 'delete',
        'today': 'view',
        'queue': 'view',
        'start': 'consult',           # starting a consultation → consult permission
        'stats': 'view',
        'statistics': 'view',
        'template_responses': 'view',
        'unbilled_requisitions': 'bill',  # billing-related view
        'sync_clinical_charges': 'edit',
    }

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = VisitFilter
    search_fields = ['visit_number', 'patient__first_name', 'patient__last_name']
    ordering_fields = ['visit_date', 'entry_time', 'queue_position', 'total_amount']

    def get_permissions(self):
        # sync_clinical_charges is an internal/background call — only requires auth
        if self.action == 'sync_clinical_charges':
            return [IsAuthenticated()]
        return super().get_permissions()

    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action == 'list':
            return VisitListSerializer
        elif self.action in ['create', 'update', 'partial_update']:
            return VisitCreateUpdateSerializer
        return VisitDetailSerializer

    def create(self, request, *args, **kwargs):
        """Create a visit and return full detail (VisitCreateUpdateSerializer's own
        Meta.fields is a narrow write-only list — it doesn't even include `id` —
        so callers that need the new visit's id/visit_number/patient_name/etc.
        right after create (e.g. to open a print preview) would get an
        incomplete response. Mirrors ClinicalNoteTemplateResponseViewSet.create().
        """
        write_serializer = self.get_serializer(data=request.data)
        write_serializer.is_valid(raise_exception=True)
        self.perform_create(write_serializer)
        read_serializer = VisitDetailSerializer(
            write_serializer.instance,
            context=self.get_serializer_context()
        )
        headers = self.get_success_headers(write_serializer.data)
        return Response(read_serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def get_queryset(self):
        """Filter queryset based on JWT roles"""
        if self.action == 'set_follow_up':
            # This action deliberately avoids the normal patient/doctor joins
            # and findings/attachments prefetches; it needs only four Visit
            # columns and get_object() still performs object permission checks.
            return Visit.objects.filter(
                tenant_id=self.request.tenant_id,
            ).only(
                'id',
                'tenant_id',
                'follow_up_required',
                'follow_up_date',
                'follow_up_notes',
            )
        queryset = super().get_queryset()
        # JWT auth: use request.roles, never request.user.groups
        # TenantViewSetMixin already scopes by tenant_id.
        # HMSPermission gates action access. For "own" read scope, apply the
        # ownership constraint here because DRF's list-level permission check
        # has no object/owner context.
        if (
            self.action in {'list', 'today', 'queue', 'stats', 'statistics'}
            and permission_evaluator.normalize_grant(self.request, 'hms.opd.view') == 'own'
            and not permission_evaluator.normalize_grant(self.request, 'admin.full_access.enabled') == 'all'
            and not getattr(self.request, 'is_super_admin', False)
        ):
            own_doctor = _own_doctor_profile(self.request)
            own_filter = Q(created_by_id=self.request.user_id)
            if own_doctor is not None:
                own_filter |= Q(doctor_id=own_doctor.id)
            queryset = queryset.filter(own_filter)
        return queryset

    def perform_create(self, serializer):
        super().perform_create(serializer)
        _invalidate_today_cache(self.request.tenant_id)

    def perform_update(self, serializer):
        super().perform_update(serializer)
        _invalidate_today_cache(self.request.tenant_id)

    @extend_schema(
        summary="Set or clear a visit follow-up",
        description=(
            "Lightweight tenant-scoped update of only follow_up_required, "
            "follow_up_date, and optional follow_up_notes."
        ),
        request=VisitSetFollowUpSerializer,
        tags=['OPD - Visits'],
    )
    @action(detail=True, methods=['post'], url_path='set_follow_up')
    def set_follow_up(self, request, pk=None):
        """Update only follow-up fields without the full Visit serializer path."""
        visit = self.get_object()
        payload = VisitSetFollowUpSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        values = payload.validated_data
        update_values = {
            'follow_up_required': values['follow_up_required'],
            'follow_up_date': values['follow_up_date'],
            'updated_at': timezone.now(),
        }
        if 'follow_up_notes' in values:
            update_values['follow_up_notes'] = values['follow_up_notes']

        Visit.objects.filter(
            pk=visit.pk,
            tenant_id=request.tenant_id,
        ).update(**update_values)

        visit.follow_up_required = update_values['follow_up_required']
        visit.follow_up_date = update_values['follow_up_date']
        visit.updated_at = update_values['updated_at']
        if 'follow_up_notes' in update_values:
            visit.follow_up_notes = update_values['follow_up_notes']

        return Response({
            'success': True,
            'message': 'Follow-up updated.',
            'data': {
                'id': visit.id,
                'follow_up_required': visit.follow_up_required,
                'follow_up_date': (
                    visit.follow_up_date.isoformat()
                    if visit.follow_up_date is not None
                    else None
                ),
                'follow_up_notes': visit.follow_up_notes or '',
            },
        })

    @extend_schema(
        summary="Get Today's Visits",
        description="Get all visits scheduled for today with queue information.",
        responses={200: VisitListSerializer(many=True)},
        tags=['OPD - Visits']
    )
    @action(detail=False, methods=['get'])
    def today(self, request):
        """Get today's visits"""
        today = date.today()
        visits = self.get_queryset().filter(visit_date=today)

        serializer = VisitListSerializer(visits, many=True)
        return Response({
            'success': True,
            'count': visits.count(),
            'data': serializer.data
        })

    @extend_schema(
        summary="Get Queue Status",
        description="Get current queue status grouped by patient status",
        tags=['OPD - Visits']
    )
    @action(detail=False, methods=['get'])
    def queue(self, request):
        """Get current queue status grouped by status"""
        today = date.today()

        # Get all today's active visits
        queryset = self.get_queryset().filter(visit_date=today)
        if request.query_params.get('doctor') == 'me':
            own_doctor = _own_doctor_profile(request)
            if own_doctor is None:
                queryset = queryset.none()
            else:
                queryset = queryset.filter(doctor_id=own_doctor.id)

        # Group by status
        waiting = queryset.filter(status='waiting').order_by('entry_time')
        called = queryset.filter(status='called').order_by('entry_time')
        in_consultation = queryset.filter(status='in_consultation').order_by('entry_time')

        return Response({
            'success': True,
            'data': {
                'waiting': VisitListSerializer(waiting, many=True).data,
                'called': VisitListSerializer(called, many=True).data,
                'in_consultation': VisitListSerializer(in_consultation, many=True).data,
            }
        })

    @extend_schema(
        summary="Call Next Patient",
        description=(
            "Call the next waiting patient in the OPD queue. If doctor_id is "
            "provided, the oldest waiting visit assigned to that doctor is "
            "prioritized; otherwise the oldest global waiting visit is called."
        ),
        parameters=[
            OpenApiParameter(
                name='doctor_id', type=int, required=False,
                description='Optional doctor ID to prioritize the queue for that doctor.'
            )
        ],
        responses={200: VisitDetailSerializer},
        tags=['OPD - Visits']
    )
    @action(detail=False, methods=['post'])
    def call_next(self, request):
        """Call next patient in queue"""
        doctor_id = request.query_params.get('doctor_id') or request.data.get('doctor_id')

        today = date.today()
        base_qs = self.get_queryset().filter(
            visit_date=today,
            status='waiting'
        )

        next_visit = None
        doctor_id_int = None
        if doctor_id:
            try:
                doctor_id_int = int(doctor_id)
            except (ValueError, TypeError):
                return Response(
                    {'success': False, 'error': 'doctor_id must be an integer'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            # Prioritize the oldest waiting visit already assigned to this doctor.
            next_visit = base_qs.filter(doctor_id=doctor_id_int).order_by('entry_time').first()

        if not next_visit:
            # Fall back to the global queue.
            next_visit = base_qs.order_by('entry_time').first()

        if not next_visit:
            return Response({
                'success': False,
                'message': 'No patients in queue'
            })

        # Update visit status
        next_visit.status = 'called'
        if doctor_id_int:
            next_visit.doctor_id = doctor_id_int
        next_visit.consultation_start_time = timezone.now()
        next_visit.save()

        serializer = VisitDetailSerializer(next_visit)
        return Response({
            'success': True,
            'message': 'Patient called',
            'data': serializer.data
        })

    @extend_schema(
        summary="Start Consultation",
        description="Mark visit as in-consultation (doctor starts seeing the patient)",
        tags=['OPD - Visits']
    )
    @action(detail=True, methods=['post'])
    def start(self, request, pk=None):
        """Start consultation for a visit"""
        visit = self.get_object()

        if visit.status == 'in_consultation':
            serializer = VisitDetailSerializer(visit)
            return Response({'success': True, 'message': 'Already in consultation', 'data': serializer.data})

        if visit.status == 'completed':
            return Response(
                {'success': False, 'error': {'code': 'VISIT_ALREADY_COMPLETED', 'message': 'Visit is already completed.'}},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY
            )

        visit.status = 'in_consultation'
        if not visit.consultation_start_time:
            visit.consultation_start_time = timezone.now()
        visit.save(update_fields=['status', 'consultation_start_time'])

        serializer = VisitDetailSerializer(visit)
        return Response({'success': True, 'message': 'Consultation started', 'data': serializer.data})

    @extend_schema(
        summary="Complete Visit",
        description="Mark visit as completed",
        tags=['OPD - Visits']
    )
    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        """Complete a visit"""
        visit = self.get_object()

        if visit.status == 'completed':
            return Response({
                'success': False,
                'message': 'Visit already completed'
            })

        visit.status = 'completed'
        visit.consultation_end_time = timezone.now()

        diagnosis = request.data.get('diagnosis', '')
        if diagnosis:
            visit.diagnosis = diagnosis

        follow_up_date = request.data.get('follow_up_date')
        if follow_up_date:
            visit.follow_up_date = follow_up_date

        follow_up_notes = request.data.get('notes', '')
        if follow_up_notes:
            visit.follow_up_notes = follow_up_notes

        visit.save()

        # Update patient's last visit date
        visit.patient.last_visit_date = timezone.now()
        visit.patient.total_visits = F('total_visits') + 1
        visit.patient.save()

        # Status/revenue changed — bust the cached today statistics.
        _invalidate_today_cache(request.tenant_id)

        serializer = VisitDetailSerializer(visit)
        return Response({
            'success': True,
            'message': 'Visit completed',
            'data': serializer.data
        })

    @extend_schema(
        summary="Get Visit Statistics",
        description=(
            "Get statistics for visits (daily, weekly, monthly). Pass "
            "group_by=day to additionally receive a daily_trend series "
            "(visits, completed, revenue per day) for the requested range, "
            "cached for 300 seconds."
        ),
        parameters=[
            OpenApiParameter(name='period', type=str, description='day, week, month'),
            OpenApiParameter(name='date', type=str, description='Specific date YYYY-MM-DD (overrides period)'),
            OpenApiParameter(name='date_from', type=str, description='Range start YYYY-MM-DD (overrides period)'),
            OpenApiParameter(name='date_to', type=str, description='Range end YYYY-MM-DD (overrides period)'),
            OpenApiParameter(
                name='group_by', type=str,
                description='Set to "day" to include a daily_trend breakdown in the response.'
            ),
        ],
        tags=['OPD - Visits']
    )
    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """
        Get visit statistics.

        Query params:
          period   — 'day' (default) | 'week' | 'month'
          date     — specific date YYYY-MM-DD (overrides period)
          date_from / date_to — explicit date range (overrides period)
        """
        today = date.today()

        # Allow an explicit date range or a specific date
        date_from_str = request.query_params.get('date_from')
        date_to_str = request.query_params.get('date_to')
        specific_date_str = request.query_params.get('date')

        # Cache only today's default (no date params, period=day)
        period_param = request.query_params.get('period', 'day')
        _use_cache = (not date_from_str and not date_to_str and not specific_date_str and period_param == 'day')
        if _use_cache:
            cache = CeliyoCache()
            cached = cache.get(f"opd:today:{request.tenant_id}")
            if cached is not None:
                return Response(cached)

        if specific_date_str:
            try:
                from datetime import datetime
                specific_date = datetime.strptime(specific_date_str, '%Y-%m-%d').date()
                start_date = specific_date
                end_date = specific_date
            except ValueError:
                start_date = today
                end_date = today
        elif date_from_str or date_to_str:
            from datetime import datetime
            start_date = datetime.strptime(date_from_str, '%Y-%m-%d').date() if date_from_str else today
            end_date = datetime.strptime(date_to_str, '%Y-%m-%d').date() if date_to_str else today
        else:
            period = request.query_params.get('period', 'day')
            if period == 'week':
                start_date = today - timedelta(days=7)
            elif period == 'month':
                start_date = today - timedelta(days=30)
            else:
                start_date = today
            end_date = today

        # Shared computation with the consolidated dashboard endpoint —
        # see apps/opd/services/stats.py (tenant-scoped inside the service).
        result = {
            'success': True,
            'period': request.query_params.get('period', 'day'),
            'date_from': str(start_date),
            'date_to': str(end_date),
            'data': compute_visit_statistics(request.tenant_id, start_date, end_date),
        }

        # Optional daily trend, e.g. ?group_by=day
        group_by = request.query_params.get('group_by')
        if group_by == 'day':
            trend_cache_key = f"opd:visits:trend:{request.tenant_id}:{start_date}:{end_date}"
            cache = CeliyoCache()
            daily_trend = cache.get(trend_cache_key)
            if daily_trend is None:
                daily_trend = compute_visit_daily_trend(
                    request.tenant_id, start_date, end_date
                )
                cache.set(trend_cache_key, daily_trend, ttl=300)
            result['data']['daily_trend'] = daily_trend
            # Trend responses are range-specific; skip the today-only cache below.
            _use_cache = False

        if _use_cache:
            CeliyoCache().set(f"opd:today:{request.tenant_id}", result, ttl=60)
        return Response(result)

    @extend_schema(
        summary="Per-doctor visit statistics",
        description=(
            "Per-doctor aggregation of visit statistics for the admin dashboard. "
            "Pass doctor=me to restrict the result to the caller's own doctor "
            "profile (resolved from the JWT user_id)."
        ),
        parameters=[
            OpenApiParameter(name='date_from', type=str, description='Range start YYYY-MM-DD (default: today)'),
            OpenApiParameter(name='date_to', type=str, description='Range end YYYY-MM-DD (default: date_from)'),
            OpenApiParameter(name='date', type=str, description='Single day shortcut (backward compat)'),
            OpenApiParameter(
                name='doctor', type=str,
                description='Set to "me" to restrict results to the requesting doctor only.'
            ),
        ],
        tags=['OPD - Visits'],
    )
    @action(detail=False, methods=['get'])
    def doctor_stats(self, request):
        """
        Per-doctor aggregation of visit statistics for admin dashboard.

        Query params:
          date_from — YYYY-MM-DD  (range start; default: today)
          date_to   — YYYY-MM-DD  (range end;   default: date_from)
          date      — YYYY-MM-DD  (single day shortcut, backward compat)
          doctor    — "me" to restrict to the requesting user's own doctor profile

        If date_from/date_to are provided they take priority over date.
        """
        import datetime as dt

        from apps.doctors.models import DoctorProfile

        today = dt.date.today()

        def _parse(s):
            try:
                return dt.date.fromisoformat(s)
            except (ValueError, TypeError):
                return None

        date_from_str = request.query_params.get('date_from')
        date_to_str   = request.query_params.get('date_to')
        date_str      = request.query_params.get('date')

        if date_from_str:
            date_from = _parse(date_from_str) or today
            date_to   = _parse(date_to_str)   or date_from
        elif date_str:
            date_from = _parse(date_str) or today
            date_to   = date_from
        else:
            date_from = today
            date_to   = today

        # Ensure from <= to
        if date_from > date_to:
            date_from, date_to = date_to, date_from

        is_single_day = date_from == date_to

        # ?doctor=me — resolve the caller's own tenant-scoped doctor profile
        # from the JWT user_id and restrict results to that doctor only.
        own_doctor_id = None
        if request.query_params.get('doctor') == 'me':
            try:
                own_doctor = DoctorProfile.objects.filter(
                    tenant_id=request.tenant_id,
                    user_id=request.user_id,
                ).first()
            except ValueError:
                # request.user_id was not a valid UUID for this field lookup.
                own_doctor = None

            if own_doctor is None:
                return Response({
                    'success': True,
                    'date_from': str(date_from),
                    'date_to': str(date_to),
                    'is_single_day': is_single_day,
                    'data': [],
                })
            own_doctor_id = own_doctor.id

        # Shared, single-pass aggregation (no per-doctor queries) — see
        # apps/opd/services/stats.py; also used by the dashboard endpoint.
        doctor_rows = compute_doctor_stats(
            request.tenant_id, date_from, date_to, doctor_id=own_doctor_id
        )

        return Response({
            'success': True,
            # legacy
            'date': str(date_from),
            # new
            'date_from': str(date_from),
            'date_to':   str(date_to),
            'is_single_day': is_single_day,
            'data': doctor_rows,
        })

    @extend_schema(
        summary="Get/Create Template Responses for Visit",
        description="GET: List all template responses for this visit. POST: Create a new template response for this visit.",
        request=ClinicalNoteTemplateResponseCreateUpdateSerializer,
        responses={
            200: ClinicalNoteTemplateResponseListSerializer(many=True),
            201: ClinicalNoteTemplateResponseDetailSerializer,
        },
        tags=['OPD - Visits', 'OPD - Clinical Templates']
    )
    @action(detail=True, methods=['get', 'post'])
    def template_responses(self, request, pk=None):
        """
        GET: List all template responses for this visit
        POST: Create a new template response for this visit
        """
        visit = self.get_object()

        if request.method == 'GET':
            # List all template responses for this visit
            responses = visit.template_responses.select_related('template').all()
            serializer = ClinicalNoteTemplateResponseListSerializer(responses, many=True)
            return Response({
                'success': True,
                'count': responses.count(),
                'data': serializer.data
            })

        elif request.method == 'POST':
            # Create a new template response for this visit (OPD encounter)
            # Set encounter fields to current visit
            data = request.data.copy()
            data['encounter_type_name'] = 'opd'
            data['encounter_id'] = visit.id

            serializer = ClinicalNoteTemplateResponseCreateUpdateSerializer(
                data=data,
                context=self.get_serializer_context()
            )

            if serializer.is_valid():
                serializer.save()
                return Response({
                    'success': True,
                    'message': 'Template response created successfully',
                    'data': serializer.data
                }, status=status.HTTP_201_CREATED)

            return Response({
                'success': False,
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        summary="Preview Unbilled Requisitions",
        description="GET: Preview all unbilled clinical orders (diagnostics, medicines, procedures, therapies) for this visit",
        responses={
            200: OpenApiResponse(description='List of unbilled requisitions with their orders'),
        },
        tags=['OPD - Visits', 'OPD - Billing']
    )
    @action(detail=True, methods=['get'])
    def unbilled_requisitions(self, request, pk=None):
        """
        Preview all unbilled orders for this visit.

        Returns requisitions and orders that haven't been linked to bill items yet.
        Useful for showing what will be imported when sync_clinical_charges is called.
        """
        from django.contrib.contenttypes.models import ContentType
        from apps.diagnostics.models import (
            Requisition
        )
        from apps.panchakarma.models import PanchakarmaOrder

        visit = self.get_object()
        visit_ct = ContentType.objects.get_for_model(visit)

        # Get requisitions for this visit
        requisitions = Requisition.objects.filter(
            tenant_id=request.tenant_id,
            content_type=visit_ct,
            object_id=visit.pk
        ).prefetch_related(
            'orders', 'medicine_orders', 'procedure_orders', 'package_orders'
        )

        unbilled_items = []

        # Process each requisition
        for req in requisitions:
            req_data = {
                'requisition_id': req.id,
                'requisition_number': req.requisition_number,
                'requisition_type': req.requisition_type,
                'status': req.status,
                'order_date': req.order_date,
                'unbilled_orders': []
            }

            # DiagnosticOrders
            for order in req.orders.filter(bill_item_content_type__isnull=True).select_related('investigation'):
                req_data['unbilled_orders'].append({
                    'type': 'diagnostic',
                    'id': order.id,
                    'name': order.investigation.name,
                    'category': order.investigation.category,
                    'price': str(order.price),
                    'status': order.status
                })

            # MedicineOrders
            for order in req.medicine_orders.filter(bill_item_content_type__isnull=True).select_related('product'):
                req_data['unbilled_orders'].append({
                    'type': 'medicine',
                    'id': order.id,
                    'name': order.product.product_name,
                    'quantity': order.quantity,
                    'price': str(order.price),
                    'total': str(order.price * order.quantity),
                    'status': order.status
                })

            # ProcedureOrders
            for order in req.procedure_orders.filter(bill_item_content_type__isnull=True).select_related('procedure'):
                req_data['unbilled_orders'].append({
                    'type': 'procedure',
                    'id': order.id,
                    'name': order.procedure.name,
                    'quantity': order.quantity,
                    'price': str(order.price),
                    'total': str(order.price * order.quantity),
                    'status': order.status
                })

            # PackageOrders
            for order in req.package_orders.filter(bill_item_content_type__isnull=True).select_related('package'):
                req_data['unbilled_orders'].append({
                    'type': 'package',
                    'id': order.id,
                    'name': order.package.name,
                    'quantity': order.quantity,
                    'price': str(order.price),
                    'total': str(order.price * order.quantity),
                    'status': order.status
                })

            if req_data['unbilled_orders']:
                unbilled_items.append(req_data)

        # Also check for PanchakarmaOrders directly linked to this visit
        panchakarma_orders = PanchakarmaOrder.objects.filter(
            tenant_id=request.tenant_id,
            content_type=visit_ct,
            object_id=visit.pk,
            bill_item_content_type__isnull=True
        ).select_related('therapy')

        if panchakarma_orders.exists():
            therapy_data = {
                'requisition_id': None,
                'requisition_number': 'Direct Therapy Orders',
                'requisition_type': 'therapy',
                'status': 'ordered',
                'unbilled_orders': []
            }

            for order in panchakarma_orders:
                therapy_data['unbilled_orders'].append({
                    'type': 'therapy',
                    'id': order.id,
                    'name': order.therapy.name,
                    'price': str(order.therapy.base_charge),
                    'status': order.status
                })

            unbilled_items.append(therapy_data)

        # Calculate totals
        total_unbilled = sum(len(req['unbilled_orders']) for req in unbilled_items)
        estimated_amount = sum(
            float(order.get('total', order.get('price', 0)))
            for req in unbilled_items
            for order in req['unbilled_orders']
        )

        return Response({
            'success': True,
            'visit_id': visit.id,
            'visit_number': visit.visit_number,
            'total_unbilled_items': total_unbilled,
            'estimated_amount': estimated_amount,
            'requisitions': unbilled_items
        })

    @extend_schema(
        summary="Sync Clinical Charges to Billing",
        description="POST: Import all unbilled clinical orders to OPD bill items. Creates OPDBillItem entries and links them to source orders.",
        responses={
            200: OpenApiResponse(description='Successfully synced charges'),
        },
        tags=['OPD - Visits', 'OPD - Billing']
    )
    @action(detail=True, methods=['post'])
    def sync_clinical_charges(self, request, pk=None):
        """
        Sync all clinical charges (orders) to OPD billing items.
        This action:
        1. Finds or creates a master OPDBill for the visit.
        2. Identifies all unbilled items (where bill_item_link is null).
        3. Creates OPDBillItem entries for them, linked to the master bill.
        4. Updates the source Orders to link them to these new Bill Items.
        5. Bill totals are updated automatically by signals.
        """
        from django.contrib.contenttypes.models import ContentType
        from apps.diagnostics.models import (
            Requisition, DiagnosticOrder, MedicineOrder
        )
        from .models import OPDBill, OPDBillItem

        visit = self.get_object()

        if str(visit.tenant_id) != str(request.tenant_id):
            return Response(
                {'success': False, 'error': 'Access denied'},
                status=status.HTTP_403_FORBIDDEN
            )

        created_items_count = 0
        updated_orders_count = 0

        with transaction.atomic():
            # Get or create the single OPDBill for this visit
            # Try to find an existing unpaid or partially paid OPDBill for this visit.
            # If multiple exist, pick the most recent one.
            opd_bill_qs = OPDBill.objects.filter(
                visit=visit,
                tenant_id=request.tenant_id,
                payment_status__in=['unpaid', 'partial']
            ).order_by('-created_at') # Most recent first

            opd_bill = opd_bill_qs.first()

            if not opd_bill:
                # If no suitable bill found, create a new one.
                # Ensure doctor is assigned only if available from visit
                doctor_to_assign = visit.doctor if visit.doctor else None
                opd_bill = OPDBill.objects.create(
                    visit=visit,
                    tenant_id=request.tenant_id,
                    doctor=doctor_to_assign,
                    billed_by_id=request.user_id,
                    # Start at zero — signals/recalculation will update these once items are added
                    total_amount=Decimal('0.00'),
                    received_amount=Decimal('0.00'),
                )

            # Get ContentType for OPDBillItem  # noqa: F841
            bill_item_ct = ContentType.objects.get_for_model(OPDBillItem)  # noqa: F841
            visit_ct = ContentType.objects.get_for_model(visit)

            # Get all requisitions for this visit
            requisitions = Requisition.objects.filter(
                tenant_id=request.tenant_id,
                content_type=visit_ct,
                object_id=visit.pk
            )

            # Process DiagnosticOrders
            diagnostic_orders = DiagnosticOrder.objects.filter(
                tenant_id=request.tenant_id,
                requisition__in=requisitions,
                bill_item_content_type__isnull=True
            ).select_related('investigation')

            for order in diagnostic_orders:
                item = OPDBillItem.objects.create(
                    bill=opd_bill,
                    tenant_id=request.tenant_id,
                    item_name=order.investigation.name,
                    source='Lab' if order.investigation.category == 'laboratory' else 'Radiology',
                    quantity=1,
                    unit_price=order.price,
                    system_calculated_price=order.price,
                    origin_content_type=ContentType.objects.get_for_model(order),
                    origin_object_id=order.pk,
                    notes=f"Test: {order.investigation.code}"
                )
                order.bill_item_link = item
                order.save(update_fields=['bill_item_content_type', 'bill_item_object_id'])
                created_items_count += 1
                updated_orders_count += 1

            # Process other order types similarly...
            # (MedicineOrder, ProcedureOrder, PackageOrder, PanchakarmaOrder)
            # Example for MedicineOrder:
            medicine_orders = MedicineOrder.objects.filter(
                tenant_id=request.tenant_id,
                requisition__in=requisitions,
                bill_item_content_type__isnull=True
            ).select_related('product')

            for order in medicine_orders:
                item = OPDBillItem.objects.create(
                    bill=opd_bill,
                    tenant_id=request.tenant_id,
                    item_name=order.product.product_name,
                    source='Pharmacy',
                    quantity=order.quantity,
                    unit_price=order.price,
                    system_calculated_price=order.price,
                    origin_content_type=ContentType.objects.get_for_model(order),
                    origin_object_id=order.pk,
                    notes=f"Medicine - Qty: {order.quantity}"
                )
                order.bill_item_link = item
                order.save(update_fields=['bill_item_content_type', 'bill_item_object_id'])
                created_items_count += 1
                updated_orders_count += 1

            # Final bill calculation is handled by signals

        return Response({
            'success': True,
            'message': f'Synced {created_items_count} clinical charges to bill {opd_bill.bill_number}',
            'created_items': created_items_count,
            'updated_orders': updated_orders_count,
            'bill_id': opd_bill.id
        })


# ============================================================================
# OPD BILL VIEWSET
# ============================================================================

class OPDBillFilter(django_filters.FilterSet):
    patient = django_filters.NumberFilter(field_name='visit__patient_id')

    class Meta:
        model = OPDBill
        fields = ['patient', 'visit', 'doctor', 'payment_status', 'opd_type', 'charge_type']


@extend_schema_view(
    list=extend_schema(
        summary="List OPD Bills",
        description="Get paginated list of OPD bills with filtering",
        parameters=[
            OpenApiParameter(name='visit', type=int, description='Filter by visit ID'),
            OpenApiParameter(name='doctor', type=int, description='Filter by doctor ID'),
            OpenApiParameter(name='payment_status', type=str, description='Filter by payment status (paid, partial, unpaid)'),
            OpenApiParameter(name='opd_type', type=str, description='Filter by OPD type (consultation, follow_up, emergency)'),
            OpenApiParameter(name='charge_type', type=str, description='Filter by charge type (first_visit, revisit, follow_up, emergency)'),
            OpenApiParameter(name='search', type=str, description='Search by bill number, visit number, or patient name'),
        ],
        tags=['OPD - Bills']
    ),
    retrieve=extend_schema(
        summary="Get Bill Details",
        description="Retrieve detailed OPD bill information",
        tags=['OPD - Bills']
    ),
    create=extend_schema(
        summary="Create OPD Bill",
        description="Create a new OPD consultation bill",
        tags=['OPD - Bills']
    )
)
class OPDBillViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    """
    OPD Bill Management
    
    Handles OPD consultation billing.
    Uses Django model permissions for access control.
    """
    queryset = OPDBill.objects.select_related(
        'visit__patient', 'doctor'
    ).prefetch_related('items')
    permission_classes = [HMSPermission]
    hms_module = 'opd'

    action_permission_map = {
        'list': 'bill',
        'retrieve': 'bill',
        'create': 'bill',
        'update': 'bill',
        'partial_update': 'bill',
        'destroy': 'bill',
        'statistics': 'bill',
        'record_payment': 'bill',
    }

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = OPDBillFilter
    search_fields = ['bill_number', 'visit__visit_number', 'visit__patient__first_name']
    ordering_fields = ['bill_date', 'total_amount', 'payment_status']
    ordering = ['-bill_date']

    def get_serializer_class(self):
        """Return appropriate serializer"""
        if self.action == 'list':
            return OPDBillListSerializer
        elif self.action in ['create', 'update', 'partial_update']:
            return OPDBillCreateUpdateSerializer
        return OPDBillDetailSerializer

    @extend_schema(
        summary="Record Payment",
        description="Record a payment for an OPD bill",
        request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'amount': {'type': 'number'},
                    'payment_mode': {'type': 'string'},
                    'payment_details': {'type': 'object'}
                }
            }
        },
        tags=['OPD - Bills']
    )
    @action(detail=True, methods=['post'])
    def record_payment(self, request, pk=None):
        """Record payment for a bill and log to the unified BillPayment ledger."""
        bill = self.get_object()

        amount = request.data.get('amount')
        payment_mode = request.data.get('payment_mode', 'cash')
        payment_details = request.data.get('payment_details', {})
        notes = request.data.get('notes', '')

        if not amount:
            return Response(
                {'success': False, 'error': 'Amount is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Record payment on the bill model
        bill.record_payment(amount, payment_mode, payment_details)

        # Log to unified BillPayment ledger (non-blocking — failure won't rollback the payment)
        try:
            from apps.payments.models import BillPayment
            from decimal import Decimal
            patient_name = ''
            encounter_number = ''
            try:
                patient_name = bill.visit.patient.full_name if bill.visit and bill.visit.patient else ''
                encounter_number = bill.visit.visit_number if bill.visit else ''
            except Exception:
                pass

            BillPayment.objects.create(
                tenant_id=request.tenant_id,
                bill_type='opd',
                opd_bill=bill,
                bill_number=bill.bill_number or str(bill.id),
                patient_name=patient_name,
                encounter_number=encounter_number,
                amount=Decimal(str(amount)),
                payment_mode=payment_mode,
                notes=notes,
                recorded_by_user_id=request.user_id,
            )
        except Exception:
            pass  # Never let ledger failure break the payment

        serializer = OPDBillDetailSerializer(bill)
        return Response({
            'success': True,
            'message': 'Payment recorded',
            'data': serializer.data
        })

    @extend_schema(
        summary="Get OPD Bill Statistics",
        description="Statistical overview of OPD bills (Admin/Superadmin only).",
        parameters=[
            OpenApiParameter(name='period', type=str, description='day, week, month, year (default: month)')
        ],
        responses={200: OPDBillStatisticsSerializer},
        tags=['OPD - Bills']
    )
    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """Get OPD bill statistics"""
        # Allow superadmins or admins — JWT roles
        roles = getattr(request, 'roles', [])
        is_superadmin = getattr(request, 'is_super_admin', False)
        is_administrator = 'admin' in roles or 'administrator' in roles

        if not (is_superadmin or is_administrator):
            return Response({'success': False, 'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)

        period = request.query_params.get('period', 'month')
        today = date.today()

        if period == 'day':
            start_date = today
        elif period == 'week':
            start_date = today - timedelta(days=7)
        elif period == 'month':
            start_date = today - timedelta(days=30)
        elif period == 'year':
            start_date = today - timedelta(days=365)
        else:
            start_date = today - timedelta(days=30)

        # Shared computation with the consolidated dashboard endpoint —
        # see apps/opd/services/stats.py (tenant-scoped inside the service,
        # serialized through OPDBillStatisticsSerializer).
        data = compute_bill_statistics(request.tenant_id, start_date)
        return Response({'success': True, 'data': data})


# ============================================================================
# OPD BILL ITEM VIEWSET
# ============================================================================

@extend_schema_view(
    list=extend_schema(
        summary="List OPD Bill Items",
        description="Get paginated list of OPD bill items with filtering",
        parameters=[
            OpenApiParameter(name='bill', type=int, description='Filter by OPDBill ID'),
            OpenApiParameter(name='source', type=str, description='Filter by source (e.g., Pharmacy, Lab, Other)'),
            OpenApiParameter(name='search', type=str, description='Search by item name'),
        ],
        tags=['OPD - Bills']
    ),
    retrieve=extend_schema(
        summary="Get OPD Bill Item Details",
        description="Retrieve detailed OPD bill item information",
        tags=['OPD - Bills']
    ),
    create=extend_schema(
        summary="Create OPD Bill Item",
        description="Create a new OPD bill item (e.g., for miscellaneous charges). This manually adds an item to an existing OPDBill.",
        tags=['OPD - Bills']
    ),
    update=extend_schema(
        summary="Update OPD Bill Item",
        description="Update an existing OPD bill item",
        tags=['OPD - Bills']
    ),
    partial_update=extend_schema(
        summary="Partial Update OPD Bill Item",
        description="Partially update an existing OPD bill item",
        tags=['OPD - Bills']
    ),
    destroy=extend_schema(
        summary="Delete OPD Bill Item",
        description="Delete an OPD bill item",
        tags=['OPD - Bills']
    )
)
class OPDBillItemViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    """
    OPD Bill Item Management

    Handles individual line items within OPD bills.
    Allows for manual creation of items for miscellaneous charges.
    Uses Django model permissions for access control.
    """
    queryset = OPDBillItem.objects.all()
    permission_classes = [HMSPermission]
    hms_module = 'opd'

    action_permission_map = {
        'list': 'bill',
        'retrieve': 'bill',
        'create': 'bill',
        'update': 'bill',
        'partial_update': 'bill',
        'destroy': 'bill',
    }

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['bill', 'source']
    search_fields = ['item_name', 'notes']
    ordering_fields = ['id', 'bill', 'source', 'item_name']
    ordering = ['bill', 'id']

    def get_serializer_class(self):
        """Return appropriate serializer"""
        return OPDBillItemSerializer

    def perform_create(self, serializer):
        """
        Custom create to add tenant_id.
        Bill recalculation is handled automatically by signals.
        """
        request = self.request
        if hasattr(request, 'tenant_id'):
            serializer.validated_data['tenant_id'] = request.tenant_id

        # Ensure system_calculated_price is set if not provided for manual items
        if 'system_calculated_price' not in serializer.validated_data or serializer.validated_data['system_calculated_price'] is None:
            serializer.validated_data['system_calculated_price'] = serializer.validated_data.get('unit_price', Decimal('0.00'))

        serializer.save()
        # Signal will automatically recalculate parent bill totals

# ============================================================================
# PROCEDURE MASTER VIEWSET
# ============================================================================

@extend_schema_view(
    list=extend_schema(
        summary="List Procedure Masters",
        description="Get list of available procedures and tests",
        tags=['OPD - Procedures']
    ),
    retrieve=extend_schema(
        summary="Get Procedure Details",
        description="Retrieve procedure master details",
        tags=['OPD - Procedures']
    ),
    create=extend_schema(
        summary="Create Procedure Master",
        description="Create a new procedure/test (Admin only)",
        tags=['OPD - Procedures']
    )
)
class ProcedureMasterViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    """
    Procedure Master Management
    
    Manages procedure and test master data.
    Uses Django model permissions for access control.
    """
    queryset = ProcedureMaster.objects.all()
    permission_classes = [HMSPermission]
    hms_module = 'opd'

    action_permission_map = {
        'list': 'bill',
        'retrieve': 'bill',
        'create': 'settings',
        'update': 'settings',
        'partial_update': 'settings',
        'destroy': 'settings',
    }

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['category', 'is_active']
    search_fields = ['name', 'code', 'description']
    ordering_fields = ['name', 'category', 'default_charge']
    ordering = ['category', 'name']

    def get_serializer_class(self):
        """Return appropriate serializer"""
        if self.action == 'list':
            return ProcedureMasterListSerializer
        elif self.action in ['create', 'update', 'partial_update']:
            return ProcedureMasterCreateUpdateSerializer
        return ProcedureMasterDetailSerializer

    def get_queryset(self):
        """Filter active procedures by default"""
        queryset = super().get_queryset()

        # Show only active procedures unless explicitly requested
        show_inactive = self.request.query_params.get('show_inactive', 'false')
        if show_inactive.lower() != 'true':
            queryset = queryset.filter(is_active=True)

        return queryset


# ============================================================================
# SERVICE VIEWSET
# ============================================================================

@extend_schema_view(
    list=extend_schema(
        summary="List Services",
        description="Get list of billable hospital services (nursing, registration, administrative, equipment, misc, other).",
        tags=['OPD - Services']
    ),
    retrieve=extend_schema(
        summary="Get Service Details",
        description="Retrieve service master details",
        tags=['OPD - Services']
    ),
    create=extend_schema(
        summary="Create Service",
        description="Create a new billable service (Admin only)",
        tags=['OPD - Services']
    ),
    update=extend_schema(
        summary="Update Service",
        description="Update a service (Admin only)",
        tags=['OPD - Services']
    ),
    partial_update=extend_schema(
        summary="Partially Update Service",
        description="Partially update a service (Admin only)",
        tags=['OPD - Services']
    ),
    destroy=extend_schema(
        summary="Delete Service",
        description="Delete a service (Admin only)",
        tags=['OPD - Services']
    ),
)
class ServiceViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    """
    Service Catalog Management

    Manages billable hospital service master data (nursing charges,
    registration charges, RMO charges, consultation, BMW charges, ECG,
    monitor, etc). Mirrors ProcedureMasterViewSet's conventions exactly.
    Uses HMS permissions for access control.
    """
    queryset = Service.objects.all()
    permission_classes = [HMSPermission]
    hms_module = 'opd'

    action_permission_map = {
        'list': 'bill',
        'retrieve': 'bill',
        'create': 'settings',
        'update': 'settings',
        'partial_update': 'settings',
        'destroy': 'settings',
    }

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['category', 'is_active']
    search_fields = ['name', 'code']
    ordering_fields = ['name', 'category', 'default_charge']
    ordering = ['name']

    def get_serializer_class(self):
        """Return appropriate serializer"""
        if self.action == 'list':
            return ServiceListSerializer
        elif self.action in ['create', 'update', 'partial_update']:
            return ServiceCreateUpdateSerializer
        return ServiceDetailSerializer

    def get_queryset(self):
        """Filter active services by default"""
        queryset = super().get_queryset()

        show_inactive = self.request.query_params.get('show_inactive', 'false')
        if show_inactive.lower() != 'true':
            queryset = queryset.filter(is_active=True)

        return queryset


# ============================================================================
# PROCEDURE PACKAGE VIEWSET
# ============================================================================

@extend_schema_view(
    list=extend_schema(
        summary="List Procedure Packages",
        description="Get list of procedure packages with discounts",
        tags=['OPD - Procedures']
    ),
    retrieve=extend_schema(
        summary="Get Package Details",
        description="Retrieve package details with included procedures",
        tags=['OPD - Procedures']
    ),
    create=extend_schema(
        summary="Create Package",
        description="Create a new procedure package (Admin only)",
        tags=['OPD - Procedures']
    )
)
class ProcedurePackageViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    """
    Procedure Package Management
    
    Manages bundled procedures with discounted pricing.
    Uses Django model permissions for access control.
    """
    queryset = ProcedurePackage.objects.prefetch_related('procedures')
    permission_classes = [HMSPermission]
    hms_module = 'opd'

    action_permission_map = {
        'list': 'bill',
        'retrieve': 'bill',
        'create': 'settings',
        'update': 'settings',
        'partial_update': 'settings',
        'destroy': 'settings',
    }

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['is_active']
    search_fields = ['name', 'code']
    ordering_fields = ['name', 'discounted_charge']
    ordering = ['name']

    def get_serializer_class(self):
        """Return appropriate serializer"""
        if self.action == 'list':
            return ProcedurePackageListSerializer
        elif self.action in ['create', 'update', 'partial_update']:
            return ProcedurePackageCreateUpdateSerializer
        return ProcedurePackageDetailSerializer



# ============================================================================
# CLINICAL NOTE VIEWSET
# ============================================================================

@extend_schema_view(
    list=extend_schema(
        summary="List Clinical Notes",
        description="Get list of clinical notes",
        tags=['OPD - Clinical']
    ),
    retrieve=extend_schema(
        summary="Get Clinical Note",
        description="Retrieve detailed clinical documentation",
        tags=['OPD - Clinical']
    ),
    create=extend_schema(
        summary="Create Clinical Note",
        description="Create clinical documentation for a visit (Doctor, Admin)",
        tags=['OPD - Clinical']
    )
)
class ClinicalNoteViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    """
    Clinical Note Management
    
    Manages clinical documentation and medical records.
    Uses Django model permissions for access control.
    """
    queryset = ClinicalNote.objects.select_related(
        'visit__patient', 'referred_doctor'
    )
    permission_classes = [HMSPermission]
    hms_module = 'opd'

    action_permission_map = {
        'list': 'view',
        'retrieve': 'view',
        'create': 'consult',
        'update': 'consult',
        'partial_update': 'consult',
        'destroy': 'consult',
    }

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['visit__patient', 'referred_doctor']
    search_fields = ['visit__visit_number', 'diagnosis', 'present_complaints']
    ordering_fields = ['note_date']
    ordering = ['-note_date']

    def get_serializer_class(self):
        """Return appropriate serializer"""
        if self.action == 'list':
            return ClinicalNoteListSerializer
        elif self.action in ['create', 'update', 'partial_update']:
            return ClinicalNoteCreateUpdateSerializer
        return ClinicalNoteDetailSerializer

    def get_queryset(self):
        """Filter clinical notes — JWT auth, tenant already scoped by mixin"""
        return super().get_queryset()


# ============================================================================
# VISIT FINDING VIEWSET
# ============================================================================

@extend_schema_view(
    list=extend_schema(
        summary="List Visit Findings",
        description="Get list of physical examination findings",
        tags=['OPD - Clinical']
    ),
    retrieve=extend_schema(
        summary="Get Finding Details",
        description="Retrieve detailed examination findings",
        tags=['OPD - Clinical']
    ),
    create=extend_schema(
        summary="Record Findings",
        description="Record physical examination findings (Nurse, Doctor, Admin)",
        tags=['OPD - Clinical']
    )
)
class VisitFindingViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    """
    Visit Finding Management
    
    Manages physical examination and vital signs.
    Uses Django model permissions for access control.
    """
    queryset = VisitFinding.objects.select_related(
        'visit__patient'
    )
    permission_classes = [HMSPermission]
    hms_module = 'opd'

    action_permission_map = {
        'list': 'view',
        'retrieve': 'view',
        'create': 'consult',
        'update': 'consult',
        'partial_update': 'consult',
        'destroy': 'consult',
    }

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['visit', 'finding_type']
    search_fields = ['visit__visit_number', 'visit__patient__first_name']
    ordering_fields = ['finding_date']
    ordering = ['-finding_date']

    def get_serializer_class(self):
        """Return appropriate serializer"""
        if self.action == 'list':
            return VisitFindingListSerializer
        elif self.action in ['create', 'update', 'partial_update']:
            return VisitFindingCreateUpdateSerializer
        return VisitFindingDetailSerializer


# ============================================================================
# VISIT ATTACHMENT VIEWSET
# ============================================================================

@extend_schema_view(
    list=extend_schema(
        summary="List Visit Attachments",
        description="Get list of medical documents and files",
        tags=['OPD - Attachments']
    ),
    retrieve=extend_schema(
        summary="Get Attachment Details",
        description="Retrieve attachment details",
        tags=['OPD - Attachments']
    ),
    create=extend_schema(
        summary="Upload Attachment",
        description="Upload medical document or file",
        tags=['OPD - Attachments']
    )
)
class VisitAttachmentViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    """
    Visit Attachment Management
    
    Manages medical documents and file uploads.
    Uses Django model permissions for access control.
    """
    queryset = VisitAttachment.objects.select_related(
        'visit__patient'
    )
    permission_classes = [HMSPermission]
    hms_module = 'opd'

    action_permission_map = {
        'list': 'view',
        'retrieve': 'view',
        'create': 'edit',
        'update': 'edit',
        'partial_update': 'edit',
        'destroy': 'edit',
    }
    parser_classes = [MultiPartParser, FormParser]

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['visit', 'file_type']
    search_fields = ['visit__visit_number', 'file_name', 'description']
    ordering_fields = ['uploaded_at']
    ordering = ['-uploaded_at']

    def get_serializer_class(self):
        """Return appropriate serializer"""
        if self.action == 'list':
            return VisitAttachmentListSerializer
        elif self.action in ['create', 'update', 'partial_update']:
            return VisitAttachmentCreateUpdateSerializer
        return VisitAttachmentDetailSerializer


# ============================================================================
# CLINICAL NOTE TEMPLATE GROUP VIEWSET
# ============================================================================

@extend_schema_view(
    list=extend_schema(
        summary="List Template Groups",
        description="Get list of clinical note template groups",
        tags=['OPD - Clinical Templates']
    ),
    retrieve=extend_schema(
        summary="Get Template Group Details",
        description="Retrieve template group details with template count",
        tags=['OPD - Clinical Templates']
    ),
    create=extend_schema(
        summary="Create Template Group",
        description="Create a new template group (Admin only)",
        tags=['OPD - Clinical Templates']
    )
)
class ClinicalNoteTemplateGroupViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    """
    Clinical Note Template Group Management

    Manages template groups for organizing clinical note templates.
    Uses Django model permissions for access control.
    """
    queryset = ClinicalNoteTemplateGroup.objects.prefetch_related('templates')
    permission_classes = [HMSPermission]
    hms_module = 'opd'

    action_permission_map = {
        'list': 'view',
        'retrieve': 'view',
        'create': 'settings',
        'update': 'settings',
        'partial_update': 'settings',
        'destroy': 'settings',
    }

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['is_active']
    search_fields = ['name', 'description']
    ordering_fields = ['display_order', 'name']
    ordering = ['display_order', 'name']

    def get_serializer_class(self):
        """Return appropriate serializer"""
        if self.action == 'list':
            return ClinicalNoteTemplateGroupListSerializer
        elif self.action in ['create', 'update', 'partial_update']:
            return ClinicalNoteTemplateGroupCreateUpdateSerializer
        return ClinicalNoteTemplateGroupDetailSerializer

    def get_queryset(self):
        """Filter active groups by default"""
        queryset = super().get_queryset()

        # Show only active groups unless explicitly requested
        show_inactive = self.request.query_params.get('show_inactive', 'false')
        if show_inactive.lower() != 'true':
            queryset = queryset.filter(is_active=True)

        return queryset


# ============================================================================
# CLINICAL NOTE TEMPLATE VIEWSET
# ============================================================================

@extend_schema_view(
    list=extend_schema(
        summary="List Clinical Note Templates",
        description="Get list of clinical note templates with field count",
        tags=['OPD - Clinical Templates']
    ),
    retrieve=extend_schema(
        summary="Get Template Details",
        description="Retrieve template with all fields and options",
        tags=['OPD - Clinical Templates']
    ),
    create=extend_schema(
        summary="Create Template",
        description="Create a new clinical note template with fields (Admin only)",
        tags=['OPD - Clinical Templates']
    )
)
class ClinicalNoteTemplateViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    """
    Clinical Note Template Management

    Manages clinical note templates with dynamic fields.
    Uses Django model permissions for access control.
    """
    queryset = ClinicalNoteTemplate.objects.select_related(
        'group'
    ).prefetch_related(
        'fields__options'
    )
    permission_classes = [HMSPermission]
    hms_module = 'opd'

    action_permission_map = {
        'list': 'view',
        'retrieve': 'view',
        'create': 'settings',
        'update': 'settings',
        'partial_update': 'settings',
        'destroy': 'settings',
        'duplicate': 'settings',
    }

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['group', 'is_active']
    search_fields = ['name', 'code', 'description']
    ordering_fields = ['display_order', 'name', 'created_at']
    ordering = ['display_order', 'name']

    def get_serializer_class(self):
        """Return appropriate serializer"""
        if self.action == 'list':
            return ClinicalNoteTemplateListSerializer
        elif self.action in ['create', 'update', 'partial_update', 'duplicate']:
            return ClinicalNoteTemplateCreateUpdateSerializer
        return ClinicalNoteTemplateDetailSerializer

    def get_queryset(self):
        """Filter active templates by default"""
        queryset = super().get_queryset()

        # Show only active templates unless explicitly requested
        show_inactive = self.request.query_params.get('show_inactive', 'false')
        if show_inactive.lower() != 'true':
            queryset = queryset.filter(is_active=True)

        return queryset

    @extend_schema(
        summary="Duplicate Template",
        description="Create a copy of an existing template with all fields and options",
        request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'name': {'type': 'string'},
                    'code': {'type': 'string'}
                }
            }
        },
        tags=['OPD - Clinical Templates']
    )
    @action(detail=True, methods=['post'])
    def duplicate(self, request, pk=None):
        """Duplicate a template with all fields and options"""
        original = self.get_object()

        new_name = request.data.get('name', f"{original.name} (Copy)")
        new_code = request.data.get('code', f"{original.code}_copy")

        # Create new template
        new_template = ClinicalNoteTemplate.objects.create(
            tenant_id=original.tenant_id,
            name=new_name,
            code=new_code,
            group=original.group,
            description=original.description,
            is_active=original.is_active,
            display_order=original.display_order
        )

        # Duplicate all fields
        for field in original.fields.all():
            new_field = ClinicalNoteTemplateField.objects.create(
                tenant_id=field.tenant_id,
                template=new_template,
                field_label=field.field_label,
                field_name=field.field_name,
                field_type=field.field_type,
                is_required=field.is_required,
                placeholder=field.placeholder,
                help_text=field.help_text,
                default_value=field.default_value,
                min_value=field.min_value,
                max_value=field.max_value,
                min_length=field.min_length,
                max_length=field.max_length,
                display_order=field.display_order,
                column_width=field.column_width,
                show_condition=field.show_condition,
                is_active=field.is_active
            )

            # Duplicate options
            for option in field.options.all():
                ClinicalNoteTemplateFieldOption.objects.create(
                    tenant_id=option.tenant_id,
                    field=new_field,
                    option_value=option.option_value,
                    option_label=option.option_label,
                    display_order=option.display_order
                )

        serializer = ClinicalNoteTemplateDetailSerializer(new_template)
        return Response({
            'success': True,
            'message': 'Template duplicated successfully',
            'data': serializer.data
        })


# ============================================================================
# CLINICAL NOTE TEMPLATE FIELD VIEWSET
# ============================================================================

@extend_schema_view(
    list=extend_schema(
        summary="List Template Fields",
        description="Get list of template fields",
        tags=['OPD - Clinical Templates']
    ),
    retrieve=extend_schema(
        summary="Get Field Details",
        description="Retrieve field details with options",
        tags=['OPD - Clinical Templates']
    ),
    create=extend_schema(
        summary="Create Template Field",
        description="Create a new template field with options (Admin only)",
        tags=['OPD - Clinical Templates']
    )
)
class ClinicalNoteTemplateFieldViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    """
    Clinical Note Template Field Management

    Manages individual fields within templates.
    Uses Django model permissions for access control.
    """
    queryset = ClinicalNoteTemplateField.objects.select_related(
        'template'
    ).prefetch_related('options')
    permission_classes = [HMSPermission]
    hms_module = 'opd'

    action_permission_map = {
        'list': 'view',
        'retrieve': 'view',
        'create': 'settings',
        'update': 'settings',
        'partial_update': 'settings',
        'destroy': 'settings',
    }

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['template', 'field_type', 'is_required', 'is_active']
    search_fields = ['field_label', 'field_name', 'help_text']
    ordering_fields = ['display_order', 'field_label']
    ordering = ['template', 'display_order']

    def get_serializer_class(self):
        """Return appropriate serializer"""
        if self.action == 'list':
            return ClinicalNoteTemplateFieldListSerializer
        elif self.action in ['create', 'update', 'partial_update']:
            return ClinicalNoteTemplateFieldCreateUpdateSerializer
        return ClinicalNoteTemplateFieldDetailSerializer

    def get_queryset(self):
        """Filter by template if provided"""
        queryset = super().get_queryset()

        template_id = self.request.query_params.get('template_id')
        if template_id:
            queryset = queryset.filter(template_id=template_id)

        return queryset


# ============================================================================
# CLINICAL NOTE TEMPLATE FIELD OPTION VIEWSET
# ============================================================================

@extend_schema_view(
    list=extend_schema(
        summary="List Field Options",
        description="Get list of options for a specific field",
        tags=['OPD - Clinical Templates']
    ),
    retrieve=extend_schema(
        summary="Get Option Details",
        description="Retrieve option details",
        tags=['OPD - Clinical Templates']
    ),
    create=extend_schema(
        summary="Create Field Option",
        description="Create a new option for a field (Admin only)",
        tags=['OPD - Clinical Templates']
    )
)
class ClinicalNoteTemplateFieldOptionViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    """
    Clinical Note Template Field Option Management

    Manages options for select/radio/checkbox fields.
    Uses Django model permissions for access control.
    """
    queryset = ClinicalNoteTemplateFieldOption.objects.select_related('field')
    permission_classes = [HMSPermission]
    hms_module = 'opd'

    action_permission_map = {
        'list': 'view',
        'retrieve': 'view',
        'create': 'settings',
        'update': 'settings',
        'partial_update': 'settings',
        'destroy': 'settings',
    }

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['field']
    search_fields = ['option_label', 'option_value']
    ordering_fields = ['display_order', 'option_label']
    ordering = ['field', 'display_order']

    serializer_class = ClinicalNoteTemplateFieldOptionSerializer

    def get_queryset(self):
        """Filter by field if provided"""
        queryset = super().get_queryset()

        field_id = self.request.query_params.get('field_id')
        if field_id:
            queryset = queryset.filter(field_id=field_id)

        return queryset


# ============================================================================
# CLINICAL NOTE TEMPLATE RESPONSE VIEWSET
# ============================================================================

@extend_schema_view(
    list=extend_schema(
        summary="List Template Responses",
        description="Get list of filled template forms",
        tags=['OPD - Clinical Templates']
    ),
    retrieve=extend_schema(
        summary="Get Response Details",
        description="Retrieve filled template with all field responses",
        tags=['OPD - Clinical Templates']
    ),
    create=extend_schema(
        summary="Create Template Response",
        description="Fill out a clinical note template for a visit",
        tags=['OPD - Clinical Templates']
    )
)
class ClinicalNoteTemplateResponseViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    """
    Clinical Note Template Response Management

    Manages filled-out clinical note templates for both OPD and IPD encounters.
    Uses Django model permissions for access control.
    """
    queryset = ClinicalNoteTemplateResponse.objects.select_related(
        'template', 'content_type'
    ).prefetch_related('field_responses__field__options')
    permission_classes = [HMSPermission]
    hms_module = 'opd'
    parser_classes = [MultiPartParser, FormParser, JSONParser]  # For file upload support and JSON

    action_permission_map = {
        'list': 'view',
        'retrieve': 'view',
        'create': 'consult',
        'update': 'consult',
        'partial_update': 'consult',
        'destroy': 'consult',
        'compare': 'view',
        'mark_reviewed': 'consult',
        'convert_to_template': 'consult',
        'apply_template': 'consult',
    }

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['template', 'status', 'content_type', 'object_id']
    search_fields = ['template__name', 'template__code']
    ordering_fields = ['response_date', 'created_at']
    ordering = ['-response_date']

    def get_serializer_class(self):
        """Return appropriate serializer"""
        if self.action == 'list':
            return ClinicalNoteTemplateResponseListSerializer
        elif self.action in ['create', 'update', 'partial_update']:
            return ClinicalNoteTemplateResponseCreateUpdateSerializer
        return ClinicalNoteTemplateResponseDetailSerializer

    def create(self, request, *args, **kwargs):
        """Create a template response and return full detail (including id)."""
        write_serializer = self.get_serializer(data=request.data)
        write_serializer.is_valid(raise_exception=True)
        self.perform_create(write_serializer)
        # Return the full detail serializer so the client always gets an `id`
        read_serializer = ClinicalNoteTemplateResponseDetailSerializer(
            write_serializer.instance,
            context=self.get_serializer_context()
        )
        headers = self.get_success_headers(write_serializer.data)
        return Response(read_serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def get_queryset(self):
        """Filter by encounter if provided"""
        queryset = super().get_queryset()

        # Support two filtering styles:
        # 1. encounter_type + encounter_id  (legacy)
        # 2. encounter_type + object_id     (preferred, matches DRF filterset_fields)
        encounter_type = self.request.query_params.get('encounter_type')
        encounter_id = (
            self.request.query_params.get('encounter_id')
            or self.request.query_params.get('object_id')
        )

        if encounter_type and encounter_id:
            from django.contrib.contenttypes.models import ContentType

            # Normalise aliases so both frontend conventions work:
            # 'visit' / 'opd'      → opd.visit
            # 'admission' / 'ipd'  → ipd.admission
            et = encounter_type.lower()
            if et in ('opd', 'visit'):
                content_type = ContentType.objects.get(app_label='opd', model='visit')
            elif et in ('ipd', 'admission'):
                content_type = ContentType.objects.get(app_label='ipd', model='admission')
            else:
                return queryset.none()

            queryset = queryset.filter(
                content_type=content_type,
                object_id=encounter_id
            )

        return queryset

    @extend_schema(
        summary="Compare Two Responses",
        description="Compare two template responses for the same encounter and template to see what changed",
        request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'other_response_id': {
                        'type': 'integer',
                        'description': 'ID of the other response to compare with'
                    }
                },
                'required': ['other_response_id']
            }
        },
        responses={
            200: {
                'type': 'object',
                'properties': {
                    'success': {'type': 'boolean'},
                    'data': {'type': 'object'}
                }
            }
        },
        tags=['OPD - Clinical Templates']
    )
    @action(detail=True, methods=['post'])
    def compare(self, request, pk=None):
        """
        Compare this response with another response for the same visit/template.
        Returns field-by-field comparison showing what changed.
        """
        response1 = self.get_object()
        other_response_id = request.data.get('other_response_id')

        if not other_response_id:
            return Response({
                'success': False,
                'error': 'other_response_id is required'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            response2 = ClinicalNoteTemplateResponse.objects.get(
                id=other_response_id,
                tenant_id=request.tenant_id
            )
        except ClinicalNoteTemplateResponse.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Response not found'
            }, status=status.HTTP_404_NOT_FOUND)

        # Validate same encounter and template
        if (response1.content_type != response2.content_type or
            response1.object_id != response2.object_id or
            response1.template != response2.template):
            return Response({
                'success': False,
                'error': 'Can only compare responses from the same encounter and template'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Get comparison
        comparison = response1.compare_with_response(response2)

        return Response({
            'success': True,
            'data': comparison
        })

    @extend_schema(
        summary="Mark Response as Reviewed",
        description="Mark this template response as reviewed/approved by supervising doctor",
        request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'reviewed_by_id': {
                        'type': 'string',
                        'format': 'uuid',
                        'description': 'UUID of reviewing doctor (defaults to current user)'
                    }
                }
            }
        },
        tags=['OPD - Clinical Templates']
    )
    @action(detail=True, methods=['post'])
    def mark_reviewed(self, request, pk=None):
        """
        Mark a template response as reviewed/approved.
        """
        response_obj = self.get_object()

        # Get reviewing doctor ID (default to current user)
        reviewed_by_id = request.data.get('reviewed_by_id', request.user_id)

        # Update response
        response_obj.is_reviewed = True
        response_obj.reviewed_by_id = reviewed_by_id
        response_obj.reviewed_at = timezone.now()
        response_obj.status = 'reviewed'
        response_obj.save()

        serializer = ClinicalNoteTemplateResponseDetailSerializer(response_obj)
        return Response({
            'success': True,
            'message': 'Response marked as reviewed',
            'data': serializer.data
        })

    @extend_schema(
        summary="Convert Response to Reusable Template",
        description="Save this response as a reusable copy-paste template for future use",
        request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'template_name': {
                        'type': 'string',
                        'description': 'Name for the reusable template'
                    },
                    'description': {
                        'type': 'string',
                        'description': 'Description of what this template is for'
                    }
                },
                'required': ['template_name']
            }
        },
        tags=['OPD - Clinical Templates']
    )
    @action(detail=True, methods=['post'])
    def convert_to_template(self, request, pk=None):
        """
        Convert current response into a reusable copy-paste template.
        """
        response_obj = self.get_object()

        template_name = request.data.get('template_name')
        description = request.data.get('description', '')

        if not template_name:
            return Response({
                'success': False,
                'error': 'template_name is required'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Convert to template
        try:
            response_template = response_obj.convert_to_reusable_template(
                template_name=template_name,
                description=description,
                created_by_id=request.user_id
            )

            serializer = ClinicalNoteResponseTemplateDetailSerializer(response_template)
            return Response({
                'success': True,
                'message': 'Response converted to reusable template',
                'data': serializer.data
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        summary="Apply Template to Response",
        description="Populate this response with values from a saved copy-paste template",
        request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'response_template_id': {
                        'type': 'integer',
                        'description': 'ID of the response template to apply'
                    }
                },
                'required': ['response_template_id']
            }
        },
        tags=['OPD - Clinical Templates']
    )
    @action(detail=True, methods=['post'])
    def apply_template(self, request, pk=None):
        """
        Apply a saved response template to populate this response's fields.
        """
        response_obj = self.get_object()

        response_template_id = request.data.get('response_template_id')

        if not response_template_id:
            return Response({
                'success': False,
                'error': 'response_template_id is required'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            response_template = ClinicalNoteResponseTemplate.objects.get(
                id=response_template_id,
                tenant_id=request.tenant_id,
                is_active=True
            )
        except ClinicalNoteResponseTemplate.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Response template not found or inactive'
            }, status=status.HTTP_404_NOT_FOUND)

        # Apply template
        try:
            field_responses = response_obj.clone_from_template(response_template)

            return Response({
                'success': True,
                'message': f'Applied template "{response_template.name}"',
                'applied_fields': len(field_responses),
                'data': ClinicalNoteTemplateResponseDetailSerializer(response_obj).data
            })

        except Exception as e:
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)


# ============================================================================
# CLINICAL NOTE TEMPLATE FIELD RESPONSE VIEWSET
# ============================================================================

@extend_schema_view(
    list=extend_schema(
        summary="List Field Responses",
        description="Get list of individual field responses",
        tags=['OPD - Clinical Templates']
    ),
    retrieve=extend_schema(
        summary="Get Field Response Details",
        description="Retrieve field response details",
        tags=['OPD - Clinical Templates']
    ),
    create=extend_schema(
        summary="Create Field Response",
        description="Create individual field response",
        tags=['OPD - Clinical Templates']
    )
)
class ClinicalNoteTemplateFieldResponseViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    """
    Clinical Note Template Field Response Management

    Manages individual field responses within template responses.
    Uses Django model permissions for access control.
    """
    queryset = ClinicalNoteTemplateFieldResponse.objects.select_related(
        'response__visit', 'field'
    )
    permission_classes = [HMSPermission]
    hms_module = 'opd'

    action_permission_map = {
        'list': 'view',
        'retrieve': 'view',
        'create': 'consult',
        'update': 'consult',
        'partial_update': 'consult',
        'destroy': 'consult',
    }

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['response', 'field']
    search_fields = ['field__field_label', 'value_text']
    ordering_fields = ['field__display_order']
    ordering = ['response', 'field__display_order']

    def get_serializer_class(self):
        """Return appropriate serializer"""
        if self.action in ['create', 'update', 'partial_update']:
            return ClinicalNoteTemplateFieldResponseCreateUpdateSerializer
        return ClinicalNoteTemplateFieldResponseSerializer

    def get_queryset(self):
        """Filter by response if provided"""
        queryset = super().get_queryset()

        response_id = self.request.query_params.get('response_id')
        if response_id:
            queryset = queryset.filter(response_id=response_id)

        return queryset


# ============================================================================
# CLINICAL NOTE RESPONSE TEMPLATE VIEWSET (Copy-Paste Templates)
# ============================================================================

@extend_schema_view(
    list=extend_schema(
        summary="List My Response Templates",
        description="Get list of my saved copy-paste response templates",
        parameters=[
            OpenApiParameter(name='is_active', type=bool, description='Filter by active status'),
            OpenApiParameter(name='search', type=str, description='Search by name or description'),
        ],
        tags=['OPD - Clinical Templates']
    ),
    retrieve=extend_schema(
        summary="Get Response Template Details",
        description="Retrieve detailed information about a saved response template",
        tags=['OPD - Clinical Templates']
    ),
    create=extend_schema(
        summary="Create Response Template",
        description="Create a new copy-paste response template",
        tags=['OPD - Clinical Templates']
    ),
    update=extend_schema(
        summary="Update Response Template",
        description="Update an existing response template",
        tags=['OPD - Clinical Templates']
    ),
    partial_update=extend_schema(
        summary="Partial Update Response Template",
        description="Partially update a response template",
        tags=['OPD - Clinical Templates']
    ),
    destroy=extend_schema(
        summary="Delete Response Template",
        description="Delete a response template",
        tags=['OPD - Clinical Templates']
    )
)
class ClinicalNoteResponseTemplateViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    """
    Clinical Note Response Template Management (Copy-Paste Templates)

    Manages reusable copy-paste response templates for clinical notes.
    Allows doctors to save frequently used patterns for quick reuse.
    """
    queryset = ClinicalNoteResponseTemplate.objects.select_related('source_response')
    permission_classes = [HMSPermission]
    hms_module = 'opd'
    serializer_class = None  # Serializer not yet defined; placeholder

    def get_serializer_class(self):
        raise NotImplementedError("Serializer not yet implemented.")
