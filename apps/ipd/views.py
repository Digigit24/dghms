# ipd/views.py
import datetime
import structlog
from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied
from django_filters.rest_framework import DjangoFilterBackend
from django.utils import timezone
from django.db import transaction
from django.db.models import IntegerField, Count, Q, Avg, Sum
from django.db.models.expressions import RawSQL
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiResponse
from common.mixins import TenantViewSetMixin
from common.cache import CeliyoCache
from common.drf_auth import HMSPermission
from common.responses import error_response, action_response
from .models import Ward, Bed, Admission, BedTransfer, IPDBilling, IPDBillItem
from .serializers import (
    WardSerializer, BedSerializer, BedListSerializer,
    AdmissionSerializer, AdmissionListSerializer,
    BedTransferSerializer, IPDBillingSerializer, IPDBillingListSerializer
)

log = structlog.get_logger(__name__)


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

    def perform_create(self, serializer):
        """Set tenant_id and created_by_user_id automatically."""
        serializer.save(tenant_id=self.request.tenant_id)

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

    @action(detail=False, methods=['get'])
    def available(self, request):
        """Get all available beds."""
        beds = self.get_queryset().filter(is_occupied=False, status='available', is_active=True)
        serializer = self.get_serializer(beds, many=True)
        return Response(serializer.data)


from .filters import AdmissionFilter  # noqa: E402

class AdmissionViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    """ViewSet for IPD Admission management."""

    queryset = Admission.objects.select_related('patient', 'ward', 'bed')
    hms_module = 'ipd'
    permission_classes = [HMSPermission]

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
        """Select related + annotate length-of-stay at DB level."""
        today = timezone.now().date()
        return Admission.objects.filter(
            tenant_id=self.request.tenant_id
        ).select_related('patient', 'ward', 'bed').annotate(
            # Use RawSQL so the PostgreSQL cast is unambiguous:
            # discharge_date::date and admission_date::date are both DATE,
            # so date - date → integer (days), never an interval/timedelta.
            los_days=RawSQL(
                "COALESCE(discharge_date::date, %s) - admission_date::date",
                (today,),
                output_field=IntegerField(),
            )
        )

    def get_serializer_class(self):
        if self.action == 'list':
            return AdmissionListSerializer
        return AdmissionSerializer

    def perform_create(self, serializer):
        """Set tenant_id and created_by_user_id automatically."""
        serializer.save(
            tenant_id=self.request.tenant_id,
            created_by_user_id=self.request.user_id
        )
        CeliyoCache().delete_pattern(f"ipd:active:{self.request.tenant_id}")

    def perform_update(self, serializer):
        super().perform_update(serializer)
        CeliyoCache().delete_pattern(f"ipd:active:{self.request.tenant_id}")

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
                    setattr(patient, f, val)
                    p_dirty = True
            if p_dirty:
                patient.save()  # recomputes age + bmi

            a_dirty = False
            for f in ["admission_date", "admission_type", "reason", "provisional_diagnosis",
                      "notify_reference_doctor", "consulting_doctor_ids"]:
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
            if a_dirty:
                admission.save()

        admission.refresh_from_db()
        patient.refresh_from_db()
        CeliyoCache().delete_pattern(f"ipd:active:{request.tenant_id}")
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

    def _enrich_doctor_rows(self, rows):
        from apps.doctors.models import DoctorProfile

        doctor_ids = [row['doctor_id'] for row in rows if row.get('doctor_id')]
        profiles = (
            DoctorProfile.objects
            .filter(tenant_id=self.request.tenant_id, user_id__in=doctor_ids)
            .prefetch_related('specialties')
        )
        profile_map = {str(profile.user_id): profile for profile in profiles}

        for row in rows:
            doctor_key = str(row.get('doctor_id') or '')
            profile = profile_map.get(doctor_key)
            if profile:
                row['doctor_name'] = profile.full_name
                row['doctor_specialty'] = ', '.join(s.name for s in profile.specialties.all()) or None
            else:
                row['doctor_name'] = f"Doctor {doctor_key[:8]}" if doctor_key else "Unassigned"
                row['doctor_specialty'] = None

            avg_stay = row.get('avg_length_of_stay_days')
            row['avg_length_of_stay_days'] = round(float(avg_stay), 1) if avg_stay is not None else None
            row['doctor'] = doctor_key

        return rows

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

        admission.discharge(
            discharge_type=discharge_type,
            discharge_summary=discharge_summary,
            discharged_by_user_id=request.user_id,
            discharge_date=discharge_datetime
        )

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
        today = datetime.date.today()

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

        # --- Admission queryset (scoped to tenant, optionally by date) ---
        qs = self.get_queryset()
        if date_from:
            qs = qs.filter(admission_date__date__gte=date_from)
        if date_to:
            qs = qs.filter(admission_date__date__lte=date_to)

        agg = qs.aggregate(
            total_admissions=Count('id'),
            currently_admitted=Count('id', filter=Q(status='admitted')),
            discharged_today=Count(
                'id',
                filter=Q(status='discharged', discharge_date__date=today)
            ),
            discharged=Count('id', filter=Q(status='discharged')),
            transferred=Count('id', filter=Q(status='transferred')),
            absconded=Count('id', filter=Q(status='absconded')),
            referred=Count('id', filter=Q(status='referred')),
            death=Count('id', filter=Q(status='death')),
            mediclaim=Count('id', filter=Q(has_mediclaim=True)),
            claim_not_started=Count('id', filter=Q(claim_status='not_started')),
            claim_documents_pending=Count('id', filter=Q(claim_status='documents_pending')),
            claim_submitted=Count('id', filter=Q(claim_status='submitted')),
            claim_under_review=Count('id', filter=Q(claim_status='under_review')),
            claim_approved=Count('id', filter=Q(claim_status='approved')),
            claim_rejected=Count('id', filter=Q(claim_status='rejected')),
            claim_settled=Count('id', filter=Q(claim_status='settled')),
        )

        avg_result = qs.filter(
            status='discharged',
            discharge_date__isnull=False,
            admission_date__isnull=False,
        ).aggregate(avg_stay=Avg('los_days'))

        # --- Live bed occupancy (never date-filtered) ---
        bed_agg = Bed.objects.filter(
            tenant_id=request.tenant_id, is_active=True
        ).aggregate(
            total_beds=Count('id'),
            occupied_beds=Count('id', filter=Q(is_occupied=True)),
            available_beds=Count('id', filter=Q(is_occupied=False, status='available')),
        )
        total_beds    = bed_agg['total_beds']    or 0
        occupied_beds = bed_agg['occupied_beds'] or 0
        available_beds = bed_agg['available_beds'] or 0
        occupancy_rate = round(occupied_beds / total_beds * 100, 1) if total_beds > 0 else 0

        result = {
            'success': True,
            'date_from': str(date_from) if date_from else None,
            'date_to':   str(date_to)   if date_to   else None,
            'data': {
                **{k: (v or 0) for k, v in agg.items()},
                'avg_length_of_stay_days': (
                    round(avg_result['avg_stay'], 1)
                    if avg_result.get('avg_stay') else None
                ),
                # Live bed stats
                'total_beds':     total_beds,
                'occupied_beds':  occupied_beds,
                'available_beds': available_beds,
                'occupancy_rate': occupancy_rate,
                'by_tpa': list(
                    qs.filter(has_mediclaim=True)
                    .values('tpa_name')
                    .annotate(count=Count('id'))
                    .order_by('-count')
                ),
            }
        }
        if _use_cache:
            CeliyoCache().set(f"ipd:active:{request.tenant_id}", result, ttl=120)
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

        qs = self.get_queryset().filter(
            admission_date__date__gte=date_from,
            admission_date__date__lte=date_to,
        )

        # ?doctor=me — Admission.doctor_id stores the SuperAdmin user_id
        # directly (not a DoctorProfile FK), so we filter on request.user_id
        # with no extra lookup required. Still tenant-scoped via get_queryset().
        if request.query_params.get('doctor') == 'me':
            qs = qs.filter(doctor_id=request.user_id)

        rows = list(
            qs.values('doctor_id').annotate(
                admissions_count=Count('id'),
                active=Count('id', filter=Q(status='admitted')),
                discharged=Count('id', filter=Q(status='discharged')),
                transferred=Count('id', filter=Q(status='transferred')),
                mediclaim_count=Count('id', filter=Q(has_mediclaim=True)),
                claim_pending=Count(
                    'id',
                    filter=Q(claim_status__in=[
                        'not_started',
                        'documents_pending',
                        'submitted',
                        'under_review',
                    ])
                ),
                claim_approved=Count('id', filter=Q(claim_status='approved')),
                claim_rejected=Count('id', filter=Q(claim_status='rejected')),
                claim_settled=Count('id', filter=Q(claim_status='settled')),
                avg_length_of_stay_days=Avg('los_days'),
            ).order_by('-admissions_count')
        )

        rows = self._enrich_doctor_rows(rows)

        return Response({
            'success': True,
            'date': str(date_from),
            'date_from': str(date_from),
            'date_to': str(date_to),
            'is_single_day': date_from == date_to,
            'data': rows,
        })


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


class IPDBillingViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    """ViewSet for IPD Billing management."""

    queryset = IPDBilling.objects.select_related('admission', 'admission__patient')
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

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Pass tenant_id, user_id, and admission instance to the serializer's create method
        serializer.save(
            tenant_id=request.tenant_id,
            billed_by_id=request.user_id,
            admission=admission
        )

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    @action(detail=True, methods=['post'])
    def add_bed_charges(self, request, pk=None):
        """Calculate and add bed charges to the bill."""
        billing = self.get_object()
        billing.add_bed_charges()

        serializer = self.get_serializer(billing)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def add_payment(self, request, pk=None):
        """Add a payment to the bill and log to the unified BillPayment ledger."""
        billing = self.get_object()
        amount = request.data.get('amount')
        payment_mode = request.data.get('payment_mode', 'cash')
        notes = request.data.get('notes', '')

        if not amount:
            return error_response("AMOUNT_REQUIRED", "Amount is required.", status=400)

        try:
            from decimal import Decimal
            amount = Decimal(str(amount))
            if amount <= 0:
                raise ValueError()
        except (ValueError, TypeError):
            return error_response("INVALID_AMOUNT", "Invalid amount.", status=400)

        billing.received_amount += amount
        billing.payment_mode = payment_mode
        billing.save()

        # Log to unified BillPayment ledger (non-blocking — failure won't rollback the payment)
        try:
            from apps.payments.models import BillPayment
            patient_name = ''
            encounter_number = ''
            try:
                patient_name = billing.admission.patient.full_name if billing.admission and billing.admission.patient else ''
                encounter_number = billing.admission.admission_id if billing.admission else ''
            except Exception:
                pass

            BillPayment.objects.create(
                tenant_id=request.tenant_id,
                bill_type='ipd',
                ipd_bill=billing,
                bill_number=billing.bill_number or str(billing.id),
                patient_name=patient_name,
                encounter_number=encounter_number,
                amount=amount,
                payment_mode=payment_mode,
                notes=notes,
                recorded_by_user_id=request.user_id,
            )
        except Exception:
            pass  # Never let ledger failure break the payment

        serializer = self.get_serializer(billing)
        return action_response("Payment recorded successfully.", data=serializer.data)

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
            # Use a clean queryset to avoid Django 5.2's strict aggregate-within-aggregate
            # check that fires when filter_queryset adds select_related or ordering
            # annotations that shadow the 'total_amount' model field.
            qs = IPDBilling.objects.filter(tenant_id=request.tenant_id)

            # Mirror filterset_fields manually so ?payment_status= and ?admission= still work
            payment_status = request.query_params.get('payment_status')
            if payment_status:
                qs = qs.filter(payment_status=payment_status)
            admission_id = request.query_params.get('admission')
            if admission_id:
                qs = qs.filter(admission_id=admission_id)

            # NOTE: IPDBilling.PAYMENT_STATUS_CHOICES is only
            # unpaid / partial / paid — there is no 'cancelled' or 'pending'
            # status on this model. 'pending_amount' previously filtered on
            # payment_status__in=['pending', 'partial'], but 'pending' never
            # matches any row, so it silently undercounted. 'cancelled_amount'
            # has no matching status and always resolves to 0 — kept in the
            # response shape for frontend (IPDBillStats) compatibility.
            agg = qs.aggregate(
                total_bills=Count('id'),
                total_amount=Sum('total_amount'),
                paid_amount=Sum('received_amount', filter=Q(payment_status='paid')),
                pending_amount=Sum('balance_amount', filter=Q(payment_status__in=['unpaid', 'partial'])),
                cancelled_amount=Sum('total_amount', filter=Q(payment_status='cancelled')),
            )
            for key in ('total_amount', 'paid_amount', 'pending_amount', 'cancelled_amount'):
                if agg[key] is None:
                    agg[key] = 0

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
        from django.db import transaction
        from django.contrib.contenttypes.models import ContentType
        from apps.diagnostics.models import (
            Requisition, DiagnosticOrder, MedicineOrder,
            ProcedureOrder, PackageOrder
        )
        from apps.panchakarma.models import PanchakarmaOrder

        billing = self.get_object()
        admission = billing.admission

        if admission.tenant_id != request.tenant_id:
            raise PermissionDenied("Access denied")

        created_items = []
        updated_orders = []

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
                    billing=billing,
                    item_name=order.investigation.name,
                    source='Lab' if order.investigation.category == 'laboratory' else 'Radiology',
                    quantity=1,
                    unit_price=order.price,
                    system_calculated_price=order.price,
                    origin_content_type=ContentType.objects.get_for_model(order),
                    origin_object_id=order.pk,
                    notes=f"Test: {order.investigation.code}"
                )
                created_items.append(item)
                order.bill_item_link = item
                order.save(update_fields=['bill_item_content_type', 'bill_item_object_id'])
                updated_orders.append(order)

            # Process MedicineOrders
            medicine_orders = MedicineOrder.objects.filter(
                tenant_id=request.tenant_id,
                requisition__in=requisitions,
                bill_item_content_type__isnull=True
            ).select_related('product', 'requisition')

            for order in medicine_orders:
                item = IPDBillItem.objects.create(
                    tenant_id=request.tenant_id,
                    billing=billing,
                    item_name=order.product.product_name,
                    source='Pharmacy',
                    quantity=order.quantity,
                    unit_price=order.price,
                    system_calculated_price=order.price,
                    origin_content_type=ContentType.objects.get_for_model(order),
                    origin_object_id=order.pk,
                    notes=f"Medicine - Qty: {order.quantity}"
                )
                created_items.append(item)
                order.bill_item_link = item
                order.save(update_fields=['bill_item_content_type', 'bill_item_object_id'])
                updated_orders.append(order)

            # Process ProcedureOrders
            procedure_orders = ProcedureOrder.objects.filter(
                tenant_id=request.tenant_id,
                requisition__in=requisitions,
                bill_item_content_type__isnull=True
            ).select_related('procedure', 'requisition')

            for order in procedure_orders:
                item = IPDBillItem.objects.create(
                    tenant_id=request.tenant_id,
                    billing=billing,
                    item_name=order.procedure.name,
                    source='Procedure',
                    quantity=order.quantity,
                    unit_price=order.price,
                    system_calculated_price=order.price,
                    origin_content_type=ContentType.objects.get_for_model(order),
                    origin_object_id=order.pk,
                    notes=f"Procedure - Qty: {order.quantity}"
                )
                created_items.append(item)
                order.bill_item_link = item
                order.save(update_fields=['bill_item_content_type', 'bill_item_object_id'])
                updated_orders.append(order)

            # Process PackageOrders
            package_orders = PackageOrder.objects.filter(
                tenant_id=request.tenant_id,
                requisition__in=requisitions,
                bill_item_content_type__isnull=True
            ).select_related('package', 'requisition')

            for order in package_orders:
                item = IPDBillItem.objects.create(
                    tenant_id=request.tenant_id,
                    billing=billing,
                    item_name=order.package.name,
                    source='Package',
                    quantity=order.quantity,
                    unit_price=order.price,
                    system_calculated_price=order.price,
                    origin_content_type=ContentType.objects.get_for_model(order),
                    origin_object_id=order.pk,
                    notes=f"Package - Qty: {order.quantity}"
                )
                created_items.append(item)
                order.bill_item_link = item
                order.save(update_fields=['bill_item_content_type', 'bill_item_object_id'])
                updated_orders.append(order)

            # Process PanchakarmaOrders
            panchakarma_orders = PanchakarmaOrder.objects.filter(
                tenant_id=request.tenant_id,
                admission=admission,
                is_billed=False
            ).select_related()
            for order in panchakarma_orders:
                order.is_billed = True
                updated_orders.append(order)

        return Response({"status": "ok"})


class IPDBillItemViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    """ViewSet for IPD bill line items."""

    from .models import IPDBillItem
    queryset = IPDBillItem.objects.all()
    permission_classes = [HMSPermission]
    hms_module = 'ipd'

    def get_serializer_class(self):
        from .serializers import IPDBillingSerializer
        return IPDBillingSerializer
