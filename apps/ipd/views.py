# ipd/views.py
import datetime
import uuid
from decimal import Decimal, InvalidOperation
import openai
import structlog
from django.http import HttpResponse
from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied
from django_filters.rest_framework import DjangoFilterBackend
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from django.db import transaction
from django.db.models import IntegerField, Count, Q, Avg, Sum, OuterRef, Subquery
from django.db.models.expressions import RawSQL
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiResponse, OpenApiExample
from common.mixins import TenantViewSetMixin
from common.cache import CeliyoCache
from common.drf_auth import HMSPermission, HMSPermissionAllowOwnView
from common import permission_evaluator
from common.responses import error_response, action_response, success_response, billing_error_response
from common import error_codes
from .models import (
    Ward, Bed, Admission, DischargePacket, BedTransfer, IPDBilling, IPDBillItem,
    IPDBillTemplate, IPDBillTemplateItem,
)
from .serializers import (
    WardSerializer, BedSerializer, BedListSerializer,
    AdmissionSerializer, AdmissionListSerializer,
    BedTransferSerializer, IPDBillingSerializer, IPDBillingListSerializer,
    IPDBillItemSerializer, IPDBillTemplateSerializer, IPDBillTemplateListSerializer,
    IPDBillTemplateFromBillRequestSerializer, IPDBillTemplateApplyRequestSerializer,
)
from .services.stats import (
    compute_admission_statistics,
    compute_billing_statistics,
    compute_ipd_doctor_stats,
)
from .services.discharge import collect_discharge_sections, generate_discharge_narrative
from .services.billing import (
    AdvanceApplyError,
    apply_advance_to_bill,
    build_billing_capabilities,
    get_ipd_billing_mode,
    has_active_non_mediclaim_bill,
)

log = structlog.get_logger(__name__)

# Cached wards+beds list TTL (occupancy counts are embedded, so every
# ward/bed/admission write busts this — see _bust_ward_cache call sites).
WARD_LIST_CACHE_TTL = 300


def _bust_ward_cache(tenant_id) -> None:
    """Bust the cached wards+beds occupancy list for a tenant."""
    try:
        CeliyoCache().delete_pattern(f"ipd:wards:{tenant_id}*")
    except Exception as exc:
        log.warning(
            "ipd_ward_cache_bust_failed",
            tenant_id=str(tenant_id),
            error=str(exc),
        )


def _recalculate_bed_charges_for_admission(admission) -> None:
    """Re-run bed-day charge calculation on every open bill for this admission.

    Called whenever admission_date changes, so length-of-stay-based bed
    charges reflect the corrected date instead of staying frozen at whatever
    was computed when the bill was first created. Paid and mediclaim bills
    are skipped (locked/lump-sum, not itemized by day). Uses the default
    force=False so a bed item staff have manually corrected
    (is_quantity_overridden=True) is left alone.
    """
    open_bills = admission.ipd_bills.exclude(payment_status='paid').exclude(bill_type='mediclaim')
    for billing in open_bills:
        billing.add_bed_charges()


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


class WardViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    """ViewSet for Ward management."""

    queryset = Ward.objects.all()
    serializer_class = WardSerializer
    hms_module = 'ipd'
    permission_classes = [HMSPermission]

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['type', 'is_active', 'floor']
    search_fields = ['name', 'floor']
    ordering_fields = ['name', 'floor', 'created_at']
    ordering = ['floor', 'name']

    def get_queryset(self):
        """Tenant-scoped wards annotated with bed occupancy counts.

        WardSerializer reads available_beds_count / occupied_beds_count /
        total_active_beds_count from these annotations; without them each
        ward row fell back to three per-object COUNT queries (N+1).
        """
        return super().get_queryset().annotate(
            available_beds_count=Count(
                'beds', filter=Q(beds__is_occupied=False, beds__is_active=True)
            ),
            occupied_beds_count=Count(
                'beds', filter=Q(beds__is_occupied=True, beds__is_active=True)
            ),
            total_active_beds_count=Count('beds', filter=Q(beds__is_active=True)),
        )

    def list(self, request, *args, **kwargs):
        """Cached wards list (`ipd:wards:{tenant_id}`).

        Only the unfiltered default listing is cached; any query params
        (filters/search/pagination) bypass the cache. The cache is busted on
        every ward/bed write and on admission create/discharge/transfer
        because occupancy counts are embedded in the response.
        """
        if request.query_params:
            return super().list(request, *args, **kwargs)

        cache = CeliyoCache()
        cache_key = f"ipd:wards:{request.tenant_id}"
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached)

        response = super().list(request, *args, **kwargs)
        if response.status_code == 200:
            cache.set(cache_key, response.data, ttl=WARD_LIST_CACHE_TTL)
        return response

    def perform_create(self, serializer):
        """Set tenant_id and created_by_user_id automatically."""
        serializer.save(tenant_id=self.request.tenant_id)
        _bust_ward_cache(self.request.tenant_id)

    def perform_update(self, serializer):
        super().perform_update(serializer)
        _bust_ward_cache(self.request.tenant_id)

    def perform_destroy(self, instance):
        super().perform_destroy(instance)
        _bust_ward_cache(self.request.tenant_id)

    @extend_schema(
        summary="Ward bed occupancy",
        description=(
            "Per-ward bed occupancy for the current tenant: total beds, "
            "occupied beds, and occupancy rate (percentage)."
        ),
        responses={200: OpenApiResponse(description="Per-ward occupancy breakdown")},
        tags=['IPD - Wards'],
    )
    @action(detail=False, methods=['get'])
    def occupancy(self, request):
        """Return per-ward bed occupancy counts and rate, tenant-scoped."""
        wards = self.get_queryset().filter(is_active=True).annotate(
            bed_total=Count('beds', filter=Q(beds__is_active=True)),
            bed_occupied=Count('beds', filter=Q(beds__is_active=True, beds__is_occupied=True)),
        ).order_by('floor', 'name')

        data = []
        for ward in wards:
            total = ward.bed_total or 0
            occupied = ward.bed_occupied or 0
            rate = round(occupied / total * 100, 1) if total > 0 else 0.0
            data.append({
                'ward': ward.name,
                'ward_id': ward.id,
                'ward_type': ward.type,
                'total_beds': total,
                'occupied': occupied,
                'rate': rate,
            })

        return Response({
            'success': True,
            'data': data,
        })


class BedViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    """ViewSet for Bed management."""

    queryset = Bed.objects.select_related('ward')
    hms_module = 'ipd'
    permission_classes = [HMSPermission]

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['ward', 'bed_type', 'is_occupied', 'status', 'is_active']
    search_fields = ['bed_number', 'ward__name']
    ordering_fields = ['bed_number', 'daily_charge', 'created_at']
    ordering = ['ward', 'bed_number']

    def get_serializer_class(self):
        if self.action == 'list':
            return BedListSerializer
        return BedSerializer

    def perform_create(self, serializer):
        """Set tenant_id automatically."""
        serializer.save(tenant_id=self.request.tenant_id)
        _bust_ward_cache(self.request.tenant_id)

    def perform_update(self, serializer):
        super().perform_update(serializer)
        _bust_ward_cache(self.request.tenant_id)

    def perform_destroy(self, instance):
        super().perform_destroy(instance)
        _bust_ward_cache(self.request.tenant_id)

    @action(detail=False, methods=['get'])
    def available(self, request):
        """
        Get available beds, optionally scoped to a ward via ?ward=<id>.

        NOTE: this is a custom @action, so DjangoFilterBackend (which powers
        filterset_fields on the plain list endpoint) never runs against it —
        the ward query param has to be applied manually here. The response is
        also explicitly wrapped in {"results": [...]} to match every other
        list endpoint in this API (StandardPagination's shape); returning a
        bare array here previously made frontend callers that read
        `response.results` silently get `undefined`.
        """
        beds = self.get_queryset().filter(is_occupied=False, status='available', is_active=True)
        ward_id = request.query_params.get('ward')
        if ward_id:
            beds = beds.filter(ward_id=ward_id)
        serializer = self.get_serializer(beds, many=True)
        return Response({'results': serializer.data})


from .filters import AdmissionFilter  # noqa: E402

class AdmissionViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    """ViewSet for IPD Admission management."""

    queryset = Admission.objects.select_related('patient', 'ward', 'bed')
    hms_module = 'ipd'
    permission_classes = [HMSPermissionAllowOwnView]

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = [
        'admission_id',
        'patient__first_name',
        'patient__last_name',
        'patient__mobile_primary',
        'provisional_diagnosis',
    ]
    ordering_fields = ['admission_date', 'discharge_date', 'created_at', 'los_days']
    ordering = ['-admission_date']

    filterset_class = AdmissionFilter

    def get_queryset(self):
        """
        Select related + annotate length-of-stay at DB level.

        The bill_total/bill_paid billing-snapshot annotation is deliberately
        NOT added here even though it's only used by the list row card —
        this get_queryset() is shared by 'active'/'doctor_stats', which call
        qs.aggregate(Count(...)) / qs.annotate(Count(...)) on top of it. A
        Sum() over the 'ipd_bills' reverse relation LEFT JOINs in every bill
        row; stacking a Count()/Avg() aggregate on top of that inflates every
        number by the number of joined bill rows (classic annotate-then-
        aggregate fan-out). It's added only for 'list' below, since that's
        the only action whose serializer (AdmissionListSerializer) exposes it.
        """
        today = timezone.now().date()
        # Scalar correlated subquery (not a Sum()/Count() over the reverse
        # 'ipd_bills' relation) — unlike bill_total/bill_paid below, this is
        # safe to add unconditionally here: it never LEFT JOINs in extra
        # rows, so it can't fan-out 'active'/'doctor_stats' aggregates the
        # way a Sum() annotation would (see this method's other docstring
        # note). Backs AdmissionSerializer/AdmissionListSerializer's
        # billing_capabilities.active_bill_id without an extra query per row.
        active_bill_subquery = IPDBilling.objects.filter(
            admission=OuterRef('pk')
        ).exclude(bill_type='mediclaim').order_by('-bill_date', '-id').values('id')[:1]

        queryset = Admission.objects.filter(
            tenant_id=self.request.tenant_id
        ).select_related('patient', 'ward', 'bed').annotate(
            # Use RawSQL so the PostgreSQL cast is unambiguous:
            # discharge_date::date and admission_date::date are both DATE,
            # so date - date → integer (days), never an interval/timedelta.
            los_days=RawSQL(
                "COALESCE(discharge_date::date, %s) - admission_date::date",
                (today,),
                output_field=IntegerField(),
            ),
            _active_bill_id=Subquery(active_bill_subquery, output_field=IntegerField()),
        )
        if (
            self.action in {'list', 'active', 'statistics'}
            and permission_evaluator.normalize_grant(self.request, 'hms.ipd.view') == 'own'
            and not permission_evaluator.normalize_grant(self.request, 'admin.full_access.enabled') == 'all'
            and not getattr(self.request, 'is_super_admin', False)
        ):
            queryset = queryset.filter(
                Q(doctor_id=self.request.user_id) |
                Q(created_by_user_id=self.request.user_id)
            )
        return queryset

    def list(self, request, *args, **kwargs):
        """
        Only the list row card needs bill_total/bill_paid (AdmissionListSerializer
        declares them; AdmissionSerializer used everywhere else does not), so
        the annotation is added here rather than in get_queryset() — see that
        method's docstring for why it can't live there.
        """
        queryset = self.get_queryset()
        if request.query_params.get('doctor') == 'me':
            own_doctor = _own_doctor_profile(request)
            if own_doctor is None:
                queryset = queryset.none()
            else:
                queryset = queryset.filter(doctor_id=own_doctor.user_id)
        queryset = self.filter_queryset(queryset).annotate(
            bill_total=Sum('ipd_bills__payable_amount'),
            bill_paid=Sum('ipd_bills__received_amount'),
        )
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page if page is not None else queryset, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    def get_serializer_class(self):
        if self.action == 'list':
            return AdmissionListSerializer
        return AdmissionSerializer

    def get_serializer_context(self):
        """Resolve the tenant's ipd_billing_mode once per request (not per
        row) and hand it to AdmissionSerializer/AdmissionListSerializer's
        billing_capabilities field via context — avoids an N+1 Hospital
        lookup on the list endpoint.
        """
        context = super().get_serializer_context()
        context['hospital_ipd_billing_mode'] = get_ipd_billing_mode(self.request.tenant_id)
        return context

    def perform_create(self, serializer):
        """Set tenant_id and created_by_user_id automatically."""
        serializer.save(
            tenant_id=self.request.tenant_id,
            created_by_user_id=self.request.user_id
        )
        CeliyoCache().delete_pattern(f"ipd:active:{self.request.tenant_id}")
        _bust_ward_cache(self.request.tenant_id)  # bed occupancy embedded in wards list

    def perform_update(self, serializer):
        old_admission_date = serializer.instance.admission_date
        super().perform_update(serializer)
        if serializer.instance.admission_date != old_admission_date:
            _recalculate_bed_charges_for_admission(serializer.instance)
        CeliyoCache().delete_pattern(f"ipd:active:{self.request.tenant_id}")
        _bust_ward_cache(self.request.tenant_id)

    # ── IPD Registration (merged patient + admission) ─────────────────────────
    def _registration_payload(self, admission, patient):
        """Merged patient + admission + guardian payload for the Registration form."""
        return {
            "admission_pk": admission.id,
            "admission_id": admission.admission_id,
            "admission_date": admission.admission_date,
            "admission_type": admission.admission_type,
            "reason": admission.reason,
            "provisional_diagnosis": admission.provisional_diagnosis,
            "doctor_id": str(admission.doctor_id) if admission.doctor_id else None,
            "reference_doctor_id": str(admission.reference_doctor_id) if admission.reference_doctor_id else None,
            "notify_reference_doctor": admission.notify_reference_doctor,
            "consulting_doctor_ids": admission.consulting_doctor_ids or [],
            "ward": admission.ward_id,
            "bed": admission.bed_id,
            "has_mediclaim": admission.has_mediclaim,
            "tpa_name": admission.tpa_name,
            "claim_status": admission.claim_status,
            "claim_reference_number": admission.claim_reference_number,
            "claim_notes": admission.claim_notes,
            "patient": {
                "id": patient.id,
                "patient_id": patient.patient_id,
                "title": patient.title,
                "first_name": patient.first_name,
                "middle_name": patient.middle_name,
                "last_name": patient.last_name,
                "gender": patient.gender,
                "date_of_birth": patient.date_of_birth,
                "age": patient.age,
                "mobile_primary": patient.mobile_primary,
                "blood_group": patient.blood_group,
                "marital_status": patient.marital_status,
                "aadhaar_number": patient.aadhaar_number,
                "height": patient.height,
                "weight": patient.weight,
                "bmi": patient.bmi,
                "address_line1": patient.address_line1,
                "photo_data": patient.photo_data,
                "guardian_first_name": patient.guardian_first_name,
                "guardian_middle_name": patient.guardian_middle_name,
                "guardian_last_name": patient.guardian_last_name,
                "guardian_mobile": patient.guardian_mobile,
                "guardian_gender": patient.guardian_gender,
                "guardian_relation": patient.guardian_relation,
                "guardian_address": patient.guardian_address,
                "guardian_photo_data": patient.guardian_photo_data,
            },
        }

    @action(detail=True, methods=["get", "patch"], url_path="registration")
    def registration(self, request, pk=None):
        """GET the merged registration data, or PATCH patient + admission together.

        Additive: existing admission create/update endpoints are untouched. The
        Registration form (front-end) uses this to edit demographics, guardian,
        images, admission type and doctors in a single call.
        """
        admission = self.get_object()
        patient = admission.patient

        if request.method.lower() == "get":
            return Response(self._registration_payload(admission, patient))

        data = request.data or {}
        patient_payload = data.get("patient") if isinstance(data.get("patient"), dict) else data

        patient_fields = [
            "title", "first_name", "middle_name", "last_name", "gender", "date_of_birth",
            "mobile_primary", "blood_group", "marital_status", "aadhaar_number",
            "height", "weight", "address_line1", "photo_data",
            "guardian_first_name", "guardian_middle_name", "guardian_last_name",
            "guardian_mobile", "guardian_gender", "guardian_relation",
            "guardian_address", "guardian_photo_data",
        ]
        from django.utils.dateparse import parse_date

        # Ward/bed allotment — validated up front (pure reads, no writes) so
        # a bed-validation failure can never happen after patient/admission
        # fields have already been written inside the atomic block below.
        # Only for admissions that don't have a bed yet: once a bed is
        # assigned, changing it must go through the dedicated Bed Transfer
        # flow (BedTransfer), not this endpoint — the front-end disables the
        # selector accordingly, but we guard here too so this call can never
        # silently steal a bed transfer.
        ward_to_set = None
        bed_to_set = None
        if admission.bed_id is None and ("ward" in data or "bed" in data):
            if data.get("bed"):
                try:
                    bed_to_set = Bed.objects.filter(tenant_id=request.tenant_id).get(pk=data["bed"])
                except Bed.DoesNotExist:
                    return error_response(
                        code=error_codes.BED_NOT_FOUND,
                        message="Selected bed was not found.",
                        status=status.HTTP_404_NOT_FOUND,
                        field="bed",
                    )
                requested_ward_id = data.get("ward")
                if requested_ward_id and bed_to_set.ward_id != int(requested_ward_id):
                    return error_response(
                        code=error_codes.BED_WARD_MISMATCH,
                        message="Selected bed does not belong to the selected ward.",
                        status=status.HTTP_400_BAD_REQUEST,
                        field="bed",
                    )
                if bed_to_set.is_occupied or bed_to_set.status != "available":
                    return error_response(
                        code=error_codes.BED_UNAVAILABLE,
                        message="Selected bed is no longer available. Please choose another bed.",
                        status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        field="bed",
                    )
                ward_to_set = bed_to_set.ward
            elif data.get("ward"):
                try:
                    ward_to_set = Ward.objects.filter(tenant_id=request.tenant_id).get(pk=data["ward"])
                except Ward.DoesNotExist:
                    return error_response(
                        code=error_codes.WARD_NOT_FOUND,
                        message="Selected ward was not found.",
                        status=status.HTTP_404_NOT_FOUND,
                        field="ward",
                    )

        old_admission_date = admission.admission_date

        with transaction.atomic():
            p_dirty = False
            for f in patient_fields:
                if f in patient_payload:
                    val = patient_payload[f]
                    if f in ("date_of_birth", "height", "weight") and val in ("", None):
                        val = None
                    elif f == "date_of_birth" and isinstance(val, str):
                        # Coerce the string to a date so PatientProfile.save() can
                        # compute age from date_of_birth.year.
                        val = parse_date(val)
                    elif val is None:
                        # Text columns are blank-able but NOT nullable — treat
                        # JSON null as "clear the field" instead of erroring.
                        val = ""
                    setattr(patient, f, val)
                    p_dirty = True
            if p_dirty:
                patient.save()  # recomputes age + bmi

            a_dirty = False
            for f in ["admission_date", "admission_type", "reason", "provisional_diagnosis",
                      "notify_reference_doctor", "consulting_doctor_ids",
                      "has_mediclaim", "tpa_name", "claim_status",
                      "claim_reference_number", "claim_notes"]:
                if f in data:
                    if f == "admission_date" and not data[f]:
                        continue
                    setattr(admission, f, data[f])
                    a_dirty = True
            if "reference_doctor_id" in data:
                admission.reference_doctor_id = data["reference_doctor_id"] or None
                a_dirty = True
            if data.get("doctor_id"):
                admission.doctor_id = data["doctor_id"]
                a_dirty = True

            if ward_to_set is not None:
                admission.ward = ward_to_set
                a_dirty = True
            if bed_to_set is not None:
                admission.bed = bed_to_set
                a_dirty = True

            if a_dirty:
                admission.save()
            if bed_to_set is not None:
                bed_to_set.mark_occupied()

        admission.refresh_from_db()
        patient.refresh_from_db()
        if admission.admission_date != old_admission_date:
            _recalculate_bed_charges_for_admission(admission)
        CeliyoCache().delete_pattern(f"ipd:active:{request.tenant_id}")
        _bust_ward_cache(request.tenant_id)  # bed may have been allotted above
        return action_response(
            message="Registration saved.",
            data=self._registration_payload(admission, patient),
        )

    def _parse_date_range(self, request):
        today = datetime.date.today()

        def parse(value):
            try:
                return datetime.date.fromisoformat(value)
            except (TypeError, ValueError):
                return None

        date_from_str = request.query_params.get('date_from')
        date_to_str = request.query_params.get('date_to')
        date_str = request.query_params.get('date')

        if date_from_str:
            date_from = parse(date_from_str) or today
            date_to = parse(date_to_str) or date_from
        elif date_str:
            date_from = parse(date_str) or today
            date_to = date_from
        else:
            date_from = today
            date_to = today

        if date_from > date_to:
            date_from, date_to = date_to, date_from

        return date_from, date_to

    def _discharge_packet_data(self, packet, sections=None):
        return {
            'id': packet.id,
            'admission': packet.admission_id,
            'status': packet.status,
            'narrative': packet.narrative,
            'sections': packet.sections_snapshot if sections is None else sections,
            'source_record_ids': packet.source_record_ids,
            'ai_model': packet.ai_model,
            'generation_count': packet.generation_count,
            'generated_at': packet.generated_at,
            'approved_at': packet.approved_at,
            'updated_at': packet.updated_at,
        }

    @action(detail=True, methods=['get', 'patch'], url_path='discharge-packet')
    def discharge_packet(self, request, pk=None):
        admission = self.get_object()
        packet, _ = DischargePacket.objects.get_or_create(
            tenant_id=request.tenant_id,
            admission=admission,
        )
        if request.method == 'PATCH':
            if 'narrative' in request.data:
                packet.narrative = str(request.data.get('narrative') or '')
            if request.data.get('approved') is True:
                if not packet.narrative.strip():
                    return Response({'error': 'A discharge summary is required before approval.'}, status=400)
                packet.status = 'approved'
                packet.approved_at = timezone.now()
                packet.approved_by_user_id = request.user_id
            elif 'narrative' in request.data and packet.status == 'approved':
                packet.status = 'generated'
                packet.approved_at = None
                packet.approved_by_user_id = None
            packet.save()
            return Response(self._discharge_packet_data(packet))

        if packet.status == 'approved' and packet.sections_snapshot:
            sections = packet.sections_snapshot
        else:
            sections, _ = collect_discharge_sections(admission)
        return Response(self._discharge_packet_data(packet, sections=sections))

    @action(detail=True, methods=['post'], url_path='discharge-packet/generate')
    def generate_discharge_packet(self, request, pk=None):
        admission = self.get_object()
        sections, record_ids = collect_discharge_sections(admission)
        try:
            narrative, model = generate_discharge_narrative(admission, sections)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except openai.AuthenticationError:
            # Distinct from the generic 502 below: an invalid/revoked API key
            # will fail identically on every retry, so telling the user to
            # "try again" is actively misleading. Logged separately so this
            # is instantly greppable instead of requiring traceback archaeology.
            log.exception('discharge_summary_openai_auth_failed', admission_id=admission.id)
            return Response(
                {'error': 'AI service is not configured correctly. Contact your administrator.'},
                status=502,
            )
        except Exception:
            log.exception('discharge_summary_generation_failed', admission_id=admission.id)
            return Response({'error': 'AI discharge summary generation failed. Please try again.'}, status=502)
        packet, _ = DischargePacket.objects.get_or_create(
            tenant_id=request.tenant_id,
            admission=admission,
        )
        packet.narrative = narrative
        packet.sections_snapshot = sections
        packet.source_record_ids = record_ids
        packet.ai_model = model
        packet.status = 'generated'
        packet.generation_count += 1
        packet.generated_at = timezone.now()
        packet.generated_by_user_id = request.user_id
        packet.approved_at = None
        packet.approved_by_user_id = None
        packet.save()
        return Response(self._discharge_packet_data(packet))

    @action(detail=True, methods=['post'])
    def discharge(self, request, pk=None):
        """Discharge a patient.

        Optionally pass discharge_date in ISO format to set a specific discharge time.
        If not provided, defaults to current time.
        """
        from django.utils import timezone

        admission = self.get_object()

        if admission.status != 'admitted':
            return Response(
                {'error': 'Patient is not currently admitted'},
                status=status.HTTP_400_BAD_REQUEST
            )

        discharge_type = request.data.get('discharge_type', 'Normal')
        discharge_summary = request.data.get('discharge_summary', '')
        if not discharge_summary:
            packet = DischargePacket.objects.filter(
                tenant_id=request.tenant_id, admission=admission
            ).first()
            if packet:
                discharge_summary = packet.narrative
        final_diagnosis = request.data.get('final_diagnosis', '')
        discharge_date = request.data.get('discharge_date')

        if final_diagnosis:
            admission.final_diagnosis = final_diagnosis

        # Validate discharge_date if provided
        if discharge_date:
            try:
                from dateutil.parser import isoparse
                discharge_datetime = isoparse(discharge_date)
            except (ValueError, TypeError):
                return Response(
                    {'error': 'Invalid discharge_date format. Use ISO 8601 format.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            if discharge_datetime < admission.admission_date:
                return Response(
                    {'error': 'Discharge date must be after or equal to admission date'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        else:
            discharge_datetime = timezone.now()

        if admission.admission_type == 'daycare' and (
            timezone.localdate(discharge_datetime) != timezone.localdate(admission.admission_date)
        ):
            log.warning(
                'daycare_discharge_rejected_outside_admission_day',
                admission_id=admission.id,
                tenant_id=str(request.tenant_id),
            )
            return Response(
                {'error': 'Daycare admissions must be discharged on the admission date.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if admission.admission_type == 'daycare':
            log.info(
                'daycare_discharge_requested',
                admission_id=admission.id,
                tenant_id=str(request.tenant_id),
            )

        admission.discharge(
            discharge_type=discharge_type,
            discharge_summary=discharge_summary,
            discharged_by_user_id=request.user_id,
            discharge_date=discharge_datetime
        )

        # Discharge frees the bed and changes admission counts — bust both
        # the IPD statistics cache and the wards+beds occupancy cache.
        CeliyoCache().delete_pattern(f"ipd:active:{request.tenant_id}")
        _bust_ward_cache(request.tenant_id)

        serializer = self.get_serializer(admission)
        return Response(serializer.data)

    @extend_schema(
        summary="List Active Admissions",
        description="Get all currently admitted patients for this tenant.",
        responses={200: AdmissionListSerializer(many=True)},
        tags=['IPD - Admissions'],
    )
    @action(detail=False, methods=['get'])
    def active(self, request):
        """Get all active admissions."""
        admissions = self.get_queryset().filter(status='admitted')
        serializer = self.get_serializer(admissions, many=True)
        return Response({
            'success': True,
            'data': serializer.data
        })

    @extend_schema(
        summary="IPD Admission Statistics",
        description=(
            "Aggregate statistics for IPD admissions. Optionally filter by "
            "admission date range via date_from/date_to. Live bed occupancy "
            "is always returned for the current tenant."
        ),
        parameters=[
            OpenApiParameter(name='date_from', type=str, description='Filter admissions admitted on or after (YYYY-MM-DD).'),
            OpenApiParameter(name='date_to', type=str, description='Filter admissions admitted on or before (YYYY-MM-DD).'),
        ],
        responses={200: OpenApiResponse(description="IPD admission statistics")},
        tags=['IPD - Admissions'],
    )
    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """
        Aggregate stats for IPD admissions.

        Query params:
          date_from  - YYYY-MM-DD  (filter admissions admitted on or after)
          date_to    - YYYY-MM-DD  (filter admissions admitted on or before)

        When no date params are given, returns all-time admission counts
        plus live bed occupancy. When dates are given, admission counts are
        scoped to that range (bed occupancy is always live / real-time).
        """
        # --- Date range (optional, no default to today) ---
        def _parse(val):
            try:
                return datetime.date.fromisoformat(val)
            except (TypeError, ValueError):
                return None

        date_from_str = request.query_params.get('date_from')
        date_to_str   = request.query_params.get('date_to')

        # Cache when no date params given (all-time + live bed stats)
        _use_cache = not date_from_str and not date_to_str
        if _use_cache:
            cache = CeliyoCache()
            cached = cache.get(f"ipd:active:{request.tenant_id}")
            if cached is not None:
                return Response(cached)
        date_from = _parse(date_from_str)
        date_to   = _parse(date_to_str)

        # Shared computation with the consolidated dashboard endpoint —
        # see apps/ipd/services/stats.py (tenant-scoped inside the service).
        result = {
            'success': True,
            'date_from': str(date_from) if date_from else None,
            'date_to':   str(date_to)   if date_to   else None,
            'data': compute_admission_statistics(
                request.tenant_id, date_from=date_from, date_to=date_to
            ),
        }
        if _use_cache:
            CeliyoCache().set(f"ipd:active:{request.tenant_id}", result, ttl=60)
        return Response(result)

    @extend_schema(
        summary="Per-doctor IPD admission statistics",
        description=(
            "Per-doctor IPD admission statistics for the IPD dashboard. Pass "
            "doctor=me to restrict the result to the caller's own admissions "
            "(resolved directly from the JWT user_id, since Admission.doctor_id "
            "stores the SuperAdmin user id)."
        ),
        parameters=[
            OpenApiParameter(name='date_from', type=str, description='Range start YYYY-MM-DD (default: today)'),
            OpenApiParameter(name='date_to', type=str, description='Range end YYYY-MM-DD (default: date_from)'),
            OpenApiParameter(name='date', type=str, description='Single day shortcut'),
            OpenApiParameter(
                name='doctor', type=str,
                description='Set to "me" to restrict results to the requesting doctor only.'
            ),
        ],
        tags=['IPD - Admissions'],
    )
    @action(detail=False, methods=['get'])
    def doctor_stats(self, request):
        """
        Per-doctor IPD admission statistics for the IPD dashboard.

        Query params:
          date_from - YYYY-MM-DD range start; default today
          date_to   - YYYY-MM-DD range end; default date_from
          date      - single day shortcut
          doctor    - "me" to restrict to the requesting user's own admissions
        """
        date_from, date_to = self._parse_date_range(request)

        # ?doctor=me — Admission.doctor_id stores the SuperAdmin user_id
        # directly (not a DoctorProfile FK), so we filter on request.user_id
        # with no extra lookup required.
        doctor_user_id = None
        if request.query_params.get('doctor') == 'me':
            doctor_user_id = request.user_id

        # Shared computation with the consolidated dashboard endpoint —
        # see apps/ipd/services/stats.py (single-pass aggregation + one
        # DoctorProfile query for enrichment).
        rows = compute_ipd_doctor_stats(
            request.tenant_id, date_from, date_to, doctor_user_id=doctor_user_id
        )

        return Response({
            'success': True,
            'date': str(date_from),
            'date_from': str(date_from),
            'date_to': str(date_to),
            'is_single_day': date_from == date_to,
            'data': rows,
        })

    @extend_schema(
        summary="Record an advance payment for an admission",
        description=(
            "Records money received from the patient/attendant ahead of billing, "
            "as one or two BillPayment ledger rows (bill_type='advance', linked "
            "to the admission, not to any specific bill). Use apply_advance to "
            "later move some or all of it onto a bill's received_amount."
        ),
        responses={200: OpenApiResponse(description="Advance recorded"), 400: OpenApiResponse(description="Invalid amount / discharged admission")},
        tags=['IPD - Billing'],
    )
    @action(detail=True, methods=['post'])
    def record_advance(self, request, pk=None):
        """POST /ipd/admissions/{id}/record_advance/

        body: { amount, payment_mode, cash_amount?, online_amount?, notes? }
        """
        from apps.payments.models import BillPayment
        from apps.payments.payment_splits import (
            PaymentEntryError, parse_payment_entries, total_amount, SPLIT_PAYMENT_MODE,
        )

        admission = self.get_object()
        if admission.status == 'discharged':
            return billing_error_response(
                'ADMISSION_DISCHARGED',
                'Cannot record an advance payment for a discharged admission.',
                status=400,
            )

        payment_mode = request.data.get('payment_mode', 'cash')
        notes = request.data.get('notes', '')
        try:
            entries = parse_payment_entries(request.data, payment_mode)
        except PaymentEntryError as exc:
            return billing_error_response('INVALID_AMOUNT', str(exc), status=400)

        patient_name = ''
        try:
            patient_name = admission.patient.full_name if admission.patient else ''
        except Exception:
            pass

        payment_group_id = uuid.uuid4()
        created_payments = []
        with transaction.atomic():
            for entry_mode, entry_amount in entries:
                created_payments.append(BillPayment.objects.create(
                    tenant_id=request.tenant_id,
                    bill_type='advance',
                    admission=admission,
                    patient_name=patient_name,
                    encounter_number=admission.admission_id,
                    amount=entry_amount,
                    payment_mode=entry_mode,
                    payment_group_id=payment_group_id,
                    notes=notes,
                    recorded_by_user_id=request.user_id,
                ))

        admission.refresh_from_db()
        log.info(
            "ipd_advance_recorded",
            tenant_id=str(request.tenant_id),
            admission_id=admission.id,
            amount=str(total_amount(entries)),
        )
        return Response({
            'success': True,
            'message': 'Advance payment recorded successfully.',
            'data': {
                'billing_capabilities': build_billing_capabilities(
                    admission, get_ipd_billing_mode(request.tenant_id)
                ),
            },
            'payment_group_id': str(payment_group_id),
            'receipt_numbers': [p.receipt_number for p in created_payments],
        }, status=200)

    @extend_schema(
        summary="Apply recorded advance to a bill",
        description=(
            "Moves some (or, if 'amount' is omitted, all remaining) of the "
            "admission's advance balance onto a specific bill's received_amount, "
            "capped at that bill's own remaining balance."
        ),
        responses={
            200: OpenApiResponse(description="Advance applied"),
            400: OpenApiResponse(description="Invalid amount / exceeds balance"),
            404: OpenApiResponse(description="Bill not found for this admission"),
        },
        tags=['IPD - Billing'],
    )
    @action(detail=True, methods=['post'])
    def apply_advance(self, request, pk=None):
        """POST /ipd/admissions/{id}/apply_advance/

        body: { bill_id, amount? }  — omit amount to apply the full remaining
        advance balance, capped at the bill's balance.
        """
        admission = self.get_object()
        bill_id = request.data.get('bill_id')
        if not bill_id:
            return billing_error_response(
                'VALIDATION_ERROR', 'bill_id is required.', status=400,
                field_errors={'bill_id': ['This field is required.']},
            )

        bill = IPDBilling.objects.filter(tenant_id=request.tenant_id, pk=bill_id).first()
        if bill is None:
            return billing_error_response('BILL_NOT_FOUND', 'Bill not found for this tenant.', status=404)

        try:
            bill = apply_advance_to_bill(admission, bill, request.data.get('amount'))
        except AdvanceApplyError as exc:
            return billing_error_response(exc.code, exc.message, status=exc.status)

        admission.refresh_from_db()
        log.info(
            "ipd_advance_applied",
            tenant_id=str(request.tenant_id),
            admission_id=admission.id,
            bill_id=bill.id,
        )
        bill_serializer = IPDBillingSerializer(bill, context=self.get_serializer_context())
        return Response({
            'success': True,
            'message': 'Advance applied to bill successfully.',
            'data': {
                'bill': bill_serializer.data,
                'billing_capabilities': build_billing_capabilities(
                    admission, get_ipd_billing_mode(request.tenant_id)
                ),
            },
        }, status=200)

    @extend_schema(
        summary="Consolidated IPD admission billing statement",
        description=(
            "Aggregates every non-mediclaim IPDBilling row for this admission "
            "into one consolidated printable statement (grand total, total "
            "received, advance applied, net balance, per-bill breakdown). "
            "Returns application/pdf by default; pass ?format=html for a raw "
            "HTML preview."
        ),
        parameters=[
            OpenApiParameter("letterhead", bool, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("language", str, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("format", str, OpenApiParameter.QUERY, required=False, description="'pdf' (default) or 'html'"),
        ],
        responses={200: OpenApiResponse(description="PDF or HTML statement")},
        tags=['IPD - Billing'],
    )
    @action(detail=True, methods=['get'])
    def statement(self, request, pk=None):
        """GET /ipd/admissions/{id}/statement/"""
        from apps.printing.rendering import (
            FORM_IPD_ADMISSION_STATEMENT,
            PrintFormCodeError,
            PrintNotFoundError,
            render_pdf_from_html,
            render_print_html,
        )

        admission = self.get_object()
        letterhead_raw = request.query_params.get('letterhead', 'true')
        letterhead = str(letterhead_raw).strip().lower() not in ('false', '0', 'no')
        language = (request.query_params.get('language') or 'en').strip().lower()
        response_format = (request.query_params.get('format') or 'pdf').strip().lower()

        try:
            html = render_print_html(
                FORM_IPD_ADMISSION_STATEMENT, request.tenant_id, admission.id, letterhead, language
            )
            if response_format == 'html':
                return HttpResponse(html, content_type='text/html')
            pdf_bytes = render_pdf_from_html(html)
        except PrintFormCodeError as exc:
            return billing_error_response('VALIDATION_ERROR', str(exc), status=400)
        except PrintNotFoundError as exc:
            return billing_error_response('NOT_FOUND', str(exc), status=404)

        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="ipd_admission_statement_{admission.id}.pdf"'
        return response


class BedTransferViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    """ViewSet for Bed Transfer management."""

    queryset = BedTransfer.objects.select_related('admission', 'from_bed', 'to_bed')
    serializer_class = BedTransferSerializer
    hms_module = 'ipd'
    permission_classes = [HMSPermission]

    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['admission']
    ordering_fields = ['transfer_date', 'created_at']
    ordering = ['-transfer_date']

    def perform_create(self, serializer):
        """Set tenant_id and performed_by_user_id automatically."""
        serializer.save(
            tenant_id=self.request.tenant_id,
            performed_by_user_id=self.request.user_id
        )
        # Transfer flips is_occupied on two beds — bust the wards+beds cache.
        _bust_ward_cache(self.request.tenant_id)


class IPDBillingViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    """ViewSet for IPD Billing management."""

    # select_related admission/patient/bed covers admission_id, patient_name
    # and get_bed_day_info(); prefetch_related('items') covers the nested
    # items list in IPDBilling(List)Serializer (was an N+1 on list).
    queryset = IPDBilling.objects.select_related(
        'admission', 'admission__patient', 'admission__bed'
    ).prefetch_related('items')
    hms_module = 'ipd'
    permission_classes = [HMSPermission]

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['payment_status', 'admission']
    search_fields = ['bill_number', 'admission__admission_id', 'admission__patient__first_name']
    ordering_fields = ['bill_date', 'total_amount', 'created_at']
    ordering = ['-bill_date']

    def get_serializer_class(self):
        if self.action == 'list':
            return IPDBillingListSerializer
        return IPDBillingSerializer

    def create(self, request, *args, **kwargs):
        """
        Create a new IPD Billing instance.
        The admission_id should be provided in the request data.

        After the bill is saved, if the admission has a bed assigned, this
        automatically computes remaining unbilled bed-days (via
        IPDBilling.get_bed_day_info()/add_bed_charges()) and inserts the Bed
        line item on the new bill when remaining_days > 0, so the frontend
        sees the auto-added room charge immediately in the response.
        """
        admission_id = request.data.get('admission')
        if not admission_id:
            return Response(
                {'error': 'Admission ID is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            admission = Admission.objects.get(id=admission_id, tenant_id=request.tenant_id)
        except Admission.DoesNotExist:
            return Response(
                {'error': 'Admission not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Check permission for the specific admission object
        self.check_object_permissions(request, admission)

        mode = get_ipd_billing_mode(request.tenant_id)
        if mode == 'single_accumulated' and has_active_non_mediclaim_bill(request.tenant_id, admission.id):
            return billing_error_response(
                'IPD_BILL_ALREADY_EXISTS',
                'This admission already has a bill under single-accumulated billing mode. '
                'Add items to the existing bill instead of creating a new one.',
                status=409,
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Pass tenant_id, user_id, and admission instance to the serializer's create method
        serializer.save(
            tenant_id=request.tenant_id,
            billed_by_id=request.user_id,
            admission=admission
        )
        billing = serializer.instance

        if admission.bed_id:
            billing.add_bed_charges()
            billing.refresh_from_db()

        log.info(
            "ipd_bill_created",
            tenant_id=str(request.tenant_id),
            bill_id=billing.id,
            admission_id=admission.id,
        )

        # Re-serialize so the response reflects any auto-added bed item and
        # the recalculated totals from add_bed_charges().
        output_serializer = self.get_serializer(billing)
        headers = self.get_success_headers(output_serializer.data)
        return Response(output_serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    @action(detail=False, methods=['post'], url_path='mediclaim')
    def create_mediclaim(self, request):
        """Create a lump-sum Mediclaim claim bill for an admission.

        Unlike the regular create() above, this never auto-adds bed charges
        or expects line items — it's a single-figure claim copy for the TPA,
        so it takes only a total_amount and records it as one bill item
        (total_amount is always derived from items, see
        IPDBilling._calculate_derived_totals). Blocked unless the admission
        already has a TPA/insurer selected on its Mediclaim tab — per the
        ask, a Mediclaim bill cannot exist before the TPA does.
        """
        admission_id = request.data.get('admission')
        if not admission_id:
            return error_response(error_codes.VALIDATION_ERROR, 'Admission ID is required.', status=400, field='admission')

        try:
            admission = Admission.objects.get(id=admission_id, tenant_id=request.tenant_id)
        except Admission.DoesNotExist:
            return error_response(error_codes.NOT_FOUND, 'Admission not found.', status=404, field='admission')

        self.check_object_permissions(request, admission)

        if not admission.has_mediclaim or not admission.tpa_name:
            return error_response(
                error_codes.VALIDATION_ERROR,
                'Select a TPA / insurance provider on the Mediclaim tab before creating a Mediclaim bill.',
                status=400,
            )

        try:
            total_amount = Decimal(str(request.data.get('total_amount', '')))
        except InvalidOperation:
            return error_response(
                error_codes.VALIDATION_ERROR, 'A valid total_amount is required.', status=400, field='total_amount'
            )
        if total_amount <= Decimal('0.00'):
            return error_response(
                error_codes.VALIDATION_ERROR, 'total_amount must be greater than zero.', status=400, field='total_amount'
            )

        with transaction.atomic():
            billing = IPDBilling.objects.create(
                tenant_id=request.tenant_id,
                admission=admission,
                billed_by_id=request.user_id,
                bill_type='mediclaim',
                payment_mode='insurance',
                diagnosis=request.data.get('diagnosis', '') or '',
                remarks=request.data.get('remarks', '') or '',
            )
            IPDBillItem.objects.create(
                tenant_id=request.tenant_id,
                bill=billing,
                item_name=f"Mediclaim Claim — {admission.tpa_name}",
                source='Other',
                quantity=1,
                system_calculated_price=total_amount,
                unit_price=total_amount,
                total_price=total_amount,
            )
        billing.refresh_from_db()

        log.info(
            "ipd_mediclaim_bill_created",
            tenant_id=str(request.tenant_id),
            bill_id=billing.id,
            admission_id=admission.id,
        )

        serializer = self.get_serializer(billing)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def add_bed_charges(self, request, pk=None):
        """Calculate and add bed charges to the bill.

        An explicit user action (the "Refresh" button) — always recomputes
        from the system, even if the bed item was previously manually
        corrected (force=True clears is_quantity_overridden too).
        """
        billing = self.get_object()
        billing.add_bed_charges(force=True)

        serializer = self.get_serializer(billing)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def add_payment(self, request, pk=None):
        """Add a payment to the bill and log it to the unified BillPayment ledger.

        For a single-mode payment, send {amount, payment_mode}. For a split
        cash+online payment, send {payment_mode: 'cash_online', cash_amount,
        online_amount} — at least one of the two must be greater than 0.
        Also used for Daycare bills (an IPDBilling row with
        admission.admission_type == 'daycare'); the ledger rows are tagged
        bill_type='daycare' in that case so they're separately reportable
        from regular IPD payments while still linking via ipd_bill.

        Runs inside a single transaction so the bill's received_amount and the
        BillPayment ledger row(s) either both commit or both roll back —
        unlike the previous best-effort ledger write, a failure here now
        fails the whole request instead of silently dropping the ledger row.
        """
        from apps.payments.models import BillPayment
        from apps.payments.payment_splits import PaymentEntryError, parse_payment_entries, total_amount, SPLIT_PAYMENT_MODE

        billing = self.get_object()
        payment_mode = request.data.get('payment_mode', 'cash')
        notes = request.data.get('notes', '')

        try:
            entries = parse_payment_entries(request.data, payment_mode)
        except PaymentEntryError as exc:
            return error_response("INVALID_AMOUNT", str(exc), status=400)

        amount = total_amount(entries)
        bill_mode = 'multiple' if payment_mode == SPLIT_PAYMENT_MODE else payment_mode

        patient_name = ''
        encounter_number = ''
        try:
            patient_name = billing.admission.patient.full_name if billing.admission and billing.admission.patient else ''
            encounter_number = billing.admission.admission_id if billing.admission else ''
        except Exception:
            pass

        bill_type = 'daycare' if billing.admission and billing.admission.admission_type == 'daycare' else 'ipd'

        payment_group_id = uuid.uuid4()
        created_payments = []
        with transaction.atomic():
            billing.record_payment(
                amount,
                mode=bill_mode,
                details={
                    'entries': [{'mode': m, 'amount': str(a)} for m, a in entries],
                    'notes': notes,
                },
            )

            for entry_mode, entry_amount in entries:
                created_payments.append(BillPayment.objects.create(
                    tenant_id=request.tenant_id,
                    bill_type=bill_type,
                    ipd_bill=billing,
                    bill_number=billing.bill_number or str(billing.id),
                    patient_name=patient_name,
                    encounter_number=encounter_number,
                    amount=entry_amount,
                    payment_mode=entry_mode,
                    payment_group_id=payment_group_id,
                    notes=notes,
                    recorded_by_user_id=request.user_id,
                ))

        serializer = self.get_serializer(billing)
        return action_response(
            "Payment recorded successfully.",
            data={
                **serializer.data,
                'payment_group_id': str(payment_group_id),
                'receipt_numbers': [p.receipt_number for p in created_payments],
            },
        )

    @extend_schema(
        summary="IPD Billing Statistics",
        description=(
            "Aggregate billing statistics for this tenant. Supports filtering "
            "by payment_status and admission via query parameters."
        ),
        parameters=[
            OpenApiParameter(name='payment_status', type=str, description='Filter by payment status'),
            OpenApiParameter(name='admission', type=int, description='Filter by admission ID'),
        ],
        responses={200: OpenApiResponse(description="IPD billing statistics")},
        tags=['IPD - Billing'],
    )
    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """Aggregate billing stats for this tenant. Respects active filters."""
        try:
            # Shared computation with the consolidated dashboard endpoint —
            # see apps/ipd/services/stats.py. The service builds a clean
            # tenant-scoped queryset (avoids Django 5.2's strict
            # aggregate-within-aggregate check) and mirrors the
            # ?payment_status= / ?admission= filters manually.
            agg = compute_billing_statistics(
                request.tenant_id,
                payment_status=request.query_params.get('payment_status'),
                admission_id=request.query_params.get('admission'),
            )

            return Response({'success': True, 'data': agg})
        except Exception as exc:
            log.error(
                "ipd_billing_statistics_failed",
                tenant_id=str(getattr(request, 'tenant_id', None)),
                error=str(exc),
                exc_info=True,
            )
            return Response(
                {
                    'success': False,
                    'error': {
                        'code': 'INTERNAL_SERVER_ERROR',
                        'message': 'Failed to compute billing statistics.',
                        'field': None,
                        'detail': {},
                    },
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        summary="Sync clinical charges to IPD bill",
        description=(
            "Identifies all unbilled clinical orders (diagnostics, medicine, "
            "procedures, packages, panchakarma) for this bill's admission, "
            "creates IPDBillItem entries for them, links each source order "
            "back to its new bill item, and finally re-syncs bed charges via "
            "add_bed_charges(). Idempotent: orders already linked to a bill "
            "item (bill_item_content_type is not null) are skipped on repeat "
            "calls."
        ),
        responses={200: IPDBillingSerializer},
        tags=['IPD - Billing'],
    )
    @action(detail=True, methods=['post'])
    def sync_clinical_charges(self, request, pk=None):
        """
        Sync all clinical charges (orders) to billing items.
        This action:
        1. Identifies all unbilled items for the admission.
        2. Creates IPDBillItem entries for them.
        3. Updates the source Orders to link them to these new Bill Items.
        4. Runs add_bed_charges() to ensure bed charges are up to date.
        """
        from apps.diagnostics.models import (
            Requisition, DiagnosticOrder, MedicineOrder,
            ProcedureOrder, PackageOrder
        )
        from apps.panchakarma.models import PanchakarmaOrder

        billing = self.get_object()
        admission = billing.admission

        if str(admission.tenant_id) != str(request.tenant_id):
            raise PermissionDenied("Access denied")

        created_count = 0

        with transaction.atomic():
            admission_ct = ContentType.objects.get_for_model(admission)
            requisitions = Requisition.objects.filter(
                tenant_id=request.tenant_id,
                content_type=admission_ct,
                object_id=admission.pk
            )

            # Process DiagnosticOrders
            diagnostic_orders = DiagnosticOrder.objects.filter(
                tenant_id=request.tenant_id,
                requisition__in=requisitions,
                bill_item_content_type__isnull=True  # Correct GFK null check
            ).select_related('investigation', 'requisition')

            for order in diagnostic_orders:
                item = IPDBillItem.objects.create(
                    tenant_id=request.tenant_id,
                    bill=billing,
                    item_name=order.investigation.name,
                    source='Lab' if order.investigation.category != 'radiology' else 'Radiology',
                    quantity=1,
                    unit_price=order.price,
                    system_calculated_price=order.price,
                    total_price=order.price,
                    origin_content_type=ContentType.objects.get_for_model(order),
                    origin_object_id=order.pk,
                    notes=f"Test: {order.investigation.code}"
                )
                order.bill_item_content_type = ContentType.objects.get_for_model(item)
                order.bill_item_object_id = item.pk
                order.save(update_fields=['bill_item_content_type', 'bill_item_object_id'])
                created_count += 1

            # Process MedicineOrders
            medicine_orders = MedicineOrder.objects.filter(
                tenant_id=request.tenant_id,
                requisition__in=requisitions,
                bill_item_content_type__isnull=True
            ).select_related('product', 'requisition')

            for order in medicine_orders:
                item = IPDBillItem.objects.create(
                    tenant_id=request.tenant_id,
                    bill=billing,
                    item_name=order.product.product_name,
                    source='Pharmacy',
                    quantity=order.quantity,
                    unit_price=order.price,
                    system_calculated_price=order.price,
                    total_price=order.price * order.quantity,
                    origin_content_type=ContentType.objects.get_for_model(order),
                    origin_object_id=order.pk,
                    notes=f"Medicine - Qty: {order.quantity}"
                )
                order.bill_item_content_type = ContentType.objects.get_for_model(item)
                order.bill_item_object_id = item.pk
                order.save(update_fields=['bill_item_content_type', 'bill_item_object_id'])
                created_count += 1

            # Process ProcedureOrders
            procedure_orders = ProcedureOrder.objects.filter(
                tenant_id=request.tenant_id,
                requisition__in=requisitions,
                bill_item_content_type__isnull=True
            ).select_related('procedure', 'requisition')

            for order in procedure_orders:
                item = IPDBillItem.objects.create(
                    tenant_id=request.tenant_id,
                    bill=billing,
                    item_name=order.procedure.name,
                    source='Procedure',
                    quantity=order.quantity,
                    unit_price=order.price,
                    system_calculated_price=order.price,
                    total_price=order.price * order.quantity,
                    origin_content_type=ContentType.objects.get_for_model(order),
                    origin_object_id=order.pk,
                    notes=f"Procedure - Qty: {order.quantity}"
                )
                order.bill_item_content_type = ContentType.objects.get_for_model(item)
                order.bill_item_object_id = item.pk
                order.save(update_fields=['bill_item_content_type', 'bill_item_object_id'])
                created_count += 1

            # Process PackageOrders
            package_orders = PackageOrder.objects.filter(
                tenant_id=request.tenant_id,
                requisition__in=requisitions,
                bill_item_content_type__isnull=True
            ).select_related('package', 'requisition')

            for order in package_orders:
                item = IPDBillItem.objects.create(
                    tenant_id=request.tenant_id,
                    bill=billing,
                    item_name=order.package.name,
                    source='Package',
                    quantity=order.quantity,
                    unit_price=order.price,
                    system_calculated_price=order.price,
                    total_price=order.price * order.quantity,
                    origin_content_type=ContentType.objects.get_for_model(order),
                    origin_object_id=order.pk,
                    notes=f"Package - Qty: {order.quantity}"
                )
                order.bill_item_content_type = ContentType.objects.get_for_model(item)
                order.bill_item_object_id = item.pk
                order.save(update_fields=['bill_item_content_type', 'bill_item_object_id'])
                created_count += 1

            # Process PanchakarmaOrders — this model has no admission/is_billed
            # fields; it only has content_type/object_id (EncounterMixin) and
            # the bill_item_content_type/bill_item_object_id/bill_item_link
            # GFK trio, mirroring the DiagnosticOrder pattern above.
            panchakarma_orders = PanchakarmaOrder.objects.filter(
                tenant_id=request.tenant_id,
                content_type=admission_ct,
                object_id=admission.pk,
                bill_item_content_type__isnull=True
            ).select_related('therapy')

            for order in panchakarma_orders:
                item = IPDBillItem.objects.create(
                    tenant_id=request.tenant_id,
                    bill=billing,
                    item_name=order.therapy.name,
                    source='Therapy',
                    quantity=1,
                    unit_price=order.therapy.base_charge,
                    system_calculated_price=order.therapy.base_charge,
                    total_price=order.therapy.base_charge,
                    origin_content_type=ContentType.objects.get_for_model(order),
                    origin_object_id=order.pk,
                    notes=f"Therapy: {order.therapy.code}" if order.therapy.code else "Therapy"
                )
                order.bill_item_content_type = ContentType.objects.get_for_model(item)
                order.bill_item_object_id = item.pk
                order.save(update_fields=['bill_item_content_type', 'bill_item_object_id'])
                created_count += 1

            # Bed charges are synced last, as promised in the docstring. This is
            # an explicit user-triggered sync, so force a recompute even if the
            # bed item was previously manually corrected.
            billing.add_bed_charges(force=True)

        billing.refresh_from_db()
        log.info(
            "ipd_bill_clinical_charges_synced",
            tenant_id=str(request.tenant_id),
            bill_id=billing.id,
            admission_id=admission.id,
            items_created=created_count,
        )

        serializer = self.get_serializer(billing)
        return Response(serializer.data)


class IPDBillItemViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    """ViewSet for IPD Bill Item management (line items within an IPD bill).

    Supports create, retrieve, list, update/partial_update (editable price,
    quantity, item_name, notes), and delete. Editing or deleting an item that
    existed before its bill's *last* transition into payment_status=='paid'
    is blocked with a 422 business-rule error (BILL_LOCKED) — items added
    AFTER that transition stay editable (see _item_is_locked()). Creating a
    new item is never blocked by this rule: a brand-new item, by definition,
    did not exist before any past transition.
    """

    queryset = IPDBillItem.objects.select_related('bill')
    serializer_class = IPDBillItemSerializer
    hms_module = 'ipd'
    permission_classes = [HMSPermission]

    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['bill', 'source']
    ordering_fields = ['created_at', 'total_price']
    ordering = ['-created_at']

    def _item_is_locked(self, bill, item):
        """An item is locked once its bill is fully paid AND the item
        existed before the bill's most recent unpaid/partial -> paid
        transition (IPDBilling.paid_transition_at). This is what lets a
        single_accumulated bill reach 'paid' mid-stay and still accept new
        charges afterwards — a plain "bill.payment_status == 'paid' blocks
        everything" rule would make that impossible, since a bill routinely
        re-enters 'paid' every time it's topped up to match new charges. Only
        items stamped as existing at (or before) that specific transition
        moment are locked; items created after it — even on a bill that is
        currently 'paid' — are never locked by this check.
        """
        if bill.payment_status != 'paid' or not bill.paid_transition_at:
            return False
        return item.created_at <= bill.paid_transition_at

    def perform_create(self, serializer):
        """Set tenant_id and compute total_price before the first save.

        total_price has no model default (NOT NULL, no default=) and is
        read_only on the serializer (clients never set it directly), so it
        must be computed here from unit_price * quantity before create() —
        otherwise every bill item creation would fail with a NOT NULL
        violation.
        """
        unit_price = serializer.validated_data.get('unit_price')
        quantity = serializer.validated_data.get('quantity', 1)
        instance = serializer.save(
            tenant_id=self.request.tenant_id,
            total_price=unit_price * quantity,
        )
        log.info(
            "ipd_bill_item_created",
            tenant_id=str(self.request.tenant_id),
            bill_id=instance.bill_id,
            item_id=instance.id,
            source=instance.source,
            is_price_overridden=instance.is_price_overridden,
        )

    @extend_schema(
        summary="Create IPD bill item",
        description=(
            "Create a line item on an IPD bill. Optionally pass catalog_type "
            "('procedure', 'package', 'service', 'investigation') and "
            "catalog_id to snapshot item_name/source/system_calculated_price "
            "from the tenant-scoped catalog row; unit_price may still be "
            "supplied to override the snapshot immediately. Never blocked by "
            "the paid-lock — new items always stay editable even once the "
            "bill is fully paid (see IPDBillItemViewSet's docstring)."
        ),
        responses={201: IPDBillItemSerializer},
        tags=['IPD - Billing'],
    )
    def create(self, request, *args, **kwargs):
        # No lock check here: a brand-new item is, by definition, created
        # after any past paid transition, so it is never locked — see
        # _item_is_locked()'s docstring.
        return super().create(request, *args, **kwargs)

    @extend_schema(
        summary="Update IPD bill item",
        description=(
            "Edit unit_price, quantity, item_name, or notes on a bill item. "
            "total_price and is_price_overridden are recomputed automatically, "
            "and the parent IPDBilling's derived totals (total_amount, "
            "payable_amount, balance_amount, payment_status) are recalculated "
            "and saved. Blocked with 422 BILL_LOCKED if this item existed "
            "before the bill's last transition into fully-paid."
        ),
        responses={200: IPDBillItemSerializer},
        tags=['IPD - Billing'],
    )
    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        if self._item_is_locked(instance.bill, instance):
            return error_response(
                code=error_codes.BILL_LOCKED,
                message="This item was billed before the bill's last paid transition and cannot be edited.",
                status=422,
            )
        return super().update(request, *args, **kwargs)

    @extend_schema(
        summary="Partially update IPD bill item",
        description=(
            "Partial update variant of the update action above — same "
            "recompute/lock-guard behavior."
        ),
        responses={200: IPDBillItemSerializer},
        tags=['IPD - Billing'],
    )
    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        if self._item_is_locked(instance.bill, instance):
            return error_response(
                code=error_codes.BILL_LOCKED,
                message="This item was billed before the bill's last paid transition and cannot be edited.",
                status=422,
            )
        return super().partial_update(request, *args, **kwargs)

    @extend_schema(
        summary="Delete IPD bill item",
        description=(
            "Delete a bill item. Blocked with 422 BILL_LOCKED if this item "
            "existed before the bill's last transition into fully-paid."
        ),
        responses={204: None},
        tags=['IPD - Billing'],
    )
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if self._item_is_locked(instance.bill, instance):
            return error_response(
                code=error_codes.BILL_LOCKED,
                message="This item was billed before the bill's last paid transition and cannot be edited.",
                status=422,
            )
        return super().destroy(request, *args, **kwargs)

    def perform_update(self, serializer):
        """Recompute total_price and trigger the parent bill's totals to recalculate."""
        instance = serializer.save(
            total_price=serializer.validated_data.get('unit_price', serializer.instance.unit_price)
            * serializer.validated_data.get('quantity', serializer.instance.quantity)
        )
        instance.bill._calculate_derived_totals()
        instance.bill.save(update_fields=[
            'total_amount', 'discount_amount', 'payable_amount',
            'balance_amount', 'payment_status', 'paid_transition_at',
        ])
        log.info(
            "ipd_bill_item_updated",
            tenant_id=str(self.request.tenant_id),
            bill_id=instance.bill_id,
            item_id=instance.id,
            is_price_overridden=instance.is_price_overridden,
        )

    def perform_destroy(self, instance):
        bill = instance.bill
        instance.delete()
        bill._calculate_derived_totals()
        bill.save(update_fields=[
            'total_amount', 'discount_amount', 'payable_amount',
            'balance_amount', 'payment_status', 'paid_transition_at',
        ])
        log.info(
            "ipd_bill_item_deleted",
            tenant_id=str(self.request.tenant_id),
            bill_id=bill.id,
        )


class IPDBillTemplateViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    """ViewSet for reusable IPD bill templates.

    Standard CRUD (tenant-scoped) with nested items writable on create, plus
    two custom actions: from_bill (snapshot an existing bill's non-Bed items
    into a new template) and apply (bulk-create fresh bill items on a bill
    from a template's items).
    """

    queryset = IPDBillTemplate.objects.prefetch_related('items')
    hms_module = 'ipd'
    permission_classes = [HMSPermission]

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['is_active']
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']

    def get_serializer_class(self):
        if self.action == 'list':
            return IPDBillTemplateListSerializer
        return IPDBillTemplateSerializer

    @extend_schema(
        summary="List IPD bill templates",
        description="List reusable IPD bill templates for this tenant.",
        responses={200: IPDBillTemplateListSerializer},
        tags=['IPD - Bill Templates'],
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(
        summary="Create IPD bill template",
        description=(
            "Create a bill template, optionally with a nested `items` list of "
            "{item_name, source, default_quantity, default_unit_price}. Any "
            "item with source='Bed' is rejected with a 400 — bed charges are "
            "always auto-computed per bill, never part of a reusable template."
        ),
        responses={201: IPDBillTemplateSerializer},
        tags=['IPD - Bill Templates'],
    )
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        serializer.save(
            tenant_id=self.request.tenant_id,
            created_by_user_id=self.request.user_id,
        )

    @extend_schema(
        summary="Create a bill template from an existing bill",
        description=(
            "Copies all of the given bill's current line items EXCEPT any "
            "with source='Bed' into a new IPDBillTemplate + "
            "IPDBillTemplateItems. Returns the created template with nested "
            "items (201)."
        ),
        request=IPDBillTemplateFromBillRequestSerializer,
        examples=[
            OpenApiExample(
                "FromBillRequest",
                value={"bill": 42, "name": "Standard Delivery Package", "description": "Optional notes"},
                request_only=True,
            ),
        ],
        responses={201: IPDBillTemplateSerializer},
        tags=['IPD - Bill Templates'],
    )
    @action(detail=False, methods=['post'], url_path='from_bill')
    def from_bill(self, request):
        bill_id = request.data.get('bill')
        name = request.data.get('name')
        description = request.data.get('description', '')

        if not bill_id or not name:
            return error_response(
                code=error_codes.VALIDATION_ERROR,
                message="'bill' and 'name' are required.",
                status=400,
            )

        bill = IPDBilling.objects.filter(tenant_id=request.tenant_id, pk=bill_id).first()
        if bill is None:
            return error_response(
                code=error_codes.BILL_NOT_FOUND,
                message="Bill not found for this tenant.",
                status=404,
            )

        with transaction.atomic():
            template = IPDBillTemplate.objects.create(
                tenant_id=request.tenant_id,
                name=name,
                description=description,
                created_by_user_id=request.user_id,
            )
            source_items = bill.items.exclude(source='Bed')
            for item in source_items:
                IPDBillTemplateItem.objects.create(
                    tenant_id=request.tenant_id,
                    template=template,
                    item_name=item.item_name,
                    source=item.source,
                    default_quantity=item.quantity,
                    default_unit_price=item.unit_price,
                )

        log.info(
            "ipd_bill_template_created_from_bill",
            tenant_id=str(request.tenant_id),
            template_id=template.id,
            bill_id=bill.id,
        )

        serializer = IPDBillTemplateSerializer(template, context={'request': request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @extend_schema(
        summary="Apply a bill template to a bill",
        description=(
            "Bulk-creates fresh IPDBillItem rows on the given bill from this "
            "template's items. Each new item gets a fresh "
            "system_calculated_price = default_unit_price, "
            "unit_price = default_unit_price, is_price_overridden=False, and "
            "no origin link back to the template — the copies are "
            "independent so later template edits never retroactively change "
            "past bills. Triggers the bill's derived totals to recalculate. "
            "Returns the list of newly created IPDBillItems."
        ),
        request=IPDBillTemplateApplyRequestSerializer,
        examples=[OpenApiExample("ApplyRequest", value={"bill": 42}, request_only=True)],
        responses={200: IPDBillItemSerializer(many=True)},
        tags=['IPD - Bill Templates'],
    )
    @action(detail=True, methods=['post'])
    def apply(self, request, pk=None):
        template = self.get_object()
        bill_id = request.data.get('bill')
        if not bill_id:
            return error_response(
                code=error_codes.VALIDATION_ERROR,
                message="'bill' is required.",
                status=400,
            )

        bill = IPDBilling.objects.filter(tenant_id=request.tenant_id, pk=bill_id).first()
        if bill is None:
            return error_response(
                code=error_codes.BILL_NOT_FOUND,
                message="Bill not found for this tenant.",
                status=404,
            )

        if bill.payment_status == 'paid':
            return error_response(
                code=error_codes.BILL_LOCKED,
                message="This bill is fully paid and cannot be edited.",
                status=422,
            )

        created_items = []
        with transaction.atomic():
            for template_item in template.items.filter(is_active=True):
                new_item = IPDBillItem.objects.create(
                    tenant_id=request.tenant_id,
                    bill=bill,
                    item_name=template_item.item_name,
                    source=template_item.source,
                    quantity=template_item.default_quantity,
                    unit_price=template_item.default_unit_price,
                    system_calculated_price=template_item.default_unit_price,
                    total_price=template_item.default_unit_price * template_item.default_quantity,
                    is_price_overridden=False,
                )
                created_items.append(new_item)

            bill._calculate_derived_totals()
            bill.save(update_fields=[
                'total_amount', 'discount_amount', 'payable_amount',
                'balance_amount', 'payment_status', 'paid_transition_at',
            ])

        log.info(
            "ipd_bill_template_applied",
            tenant_id=str(request.tenant_id),
            template_id=template.id,
            bill_id=bill.id,
            items_created=len(created_items),
        )

        serializer = IPDBillItemSerializer(created_items, many=True, context={'request': request})
        return success_response(data=serializer.data, message="Template applied to bill.")
