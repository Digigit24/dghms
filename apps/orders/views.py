from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend

from django.db.models import Q, Sum, Avg, Count
from django.db import transaction as db_transaction
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.http import HttpResponse
from decimal import Decimal
import json

# OpenAPI/Swagger documentation
from drf_spectacular.utils import (
    extend_schema,
    extend_schema_view,
    OpenApiParameter,
    OpenApiResponse
)

from common.drf_auth import HMSPermission
from common.mixins import TenantViewSetMixin

from .models import Order, OrderItem, FeeType
from .serializers import (
    OrderCreateUpdateSerializer,
    OrderDetailSerializer,
    OrderListSerializer,
    FeeTypeSerializer,
    RazorpayOrderCreateSerializer,
    RazorpayPaymentVerifySerializer
)
from .razorpay_utils import RazorpayClient


# Fee Type Management
@extend_schema_view(
    list=extend_schema(
        summary="List Fee Types",
        description="Get list of available fee types",
        tags=['Fee Types']
    ),
    create=extend_schema(
        summary="Create Fee Type",
        description="Create a new fee type (Admin only)",
        tags=['Fee Types']
    ),
    retrieve=extend_schema(
        summary="Get Fee Type Details",
        description="Retrieve details of a specific fee type",
        tags=['Fee Types']
    )
)
class FeeTypeViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    """Fee Type Management"""
    queryset = FeeType.objects.all()
    serializer_class = FeeTypeSerializer
    permission_classes = [HMSPermission]
    hms_module = 'orders'

    action_permission_map = {
        'list': 'view_fee_types',
        'retrieve': 'view_fee_types',
        'create': 'manage_fee_types',
        'update': 'manage_fee_types',
        'partial_update': 'manage_fee_types',
        'destroy': 'manage_fee_types',
    }
    
    def list(self, request, *args, **kwargs):
        """List fee types with ability to filter"""
        queryset = self.filter_queryset(self.get_queryset())
        
        # Optional filtering
        category = request.query_params.get('category')
        if category:
            queryset = queryset.filter(category=category)
        
        serializer = self.get_serializer(queryset, many=True)
        return Response({
            'success': True,
            'data': serializer.data
        })


@extend_schema_view(
    list=extend_schema(
        summary="List Orders",
        description="Get list of orders with extensive filtering options",
        parameters=[
            OpenApiParameter(name='patient_id', type=int, description='Filter by patient'),
            OpenApiParameter(name='services_type', type=str, description='Filter by service type'),
            OpenApiParameter(name='status', type=str, description='Filter by order status'),
            OpenApiParameter(name='is_paid', type=bool, description='Filter by payment status'),
            OpenApiParameter(name='date_from', type=str, description='Orders from date (YYYY-MM-DD)'),
            OpenApiParameter(name='date_to', type=str, description='Orders to date (YYYY-MM-DD)'),
            OpenApiParameter(name='min_amount', type=float, description='Minimum total amount'),
            OpenApiParameter(name='max_amount', type=float, description='Maximum total amount'),
        ],
        tags=['Orders']
    ),
    create=extend_schema(
        summary="Create Order",
        description="Create a new order with multiple service items and fees",
        tags=['Orders']
    ),
    retrieve=extend_schema(
        summary="Get Order Details",
        description="Retrieve comprehensive details of a specific order",
        tags=['Orders']
    )
)
class OrderViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    """
    Comprehensive Order Management ViewSet
    Supports full CRUD operations and advanced order tracking
    """
    queryset = Order.objects.select_related(
        'patient', 'user'
    ).prefetch_related(
        'order_items', 'order_fee_details'
    )
    permission_classes = [HMSPermission]
    hms_module = 'orders'

    action_permission_map = {
        'list': 'view',
        'retrieve': 'view',
        'create': 'create',
        'update': 'edit',
        'partial_update': 'edit',
        'destroy': 'cancel',
        'statistics': 'view_reports',
    }

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = [
        'patient', 'services_type',
        'status', 'is_paid'
    ]
    search_fields = [
        'order_number',
        'patient__first_name',
        'patient__last_name',
        'patient__mobile_primary'
    ]
    ordering_fields = [
        'created_at', 'total_amount',
        'status', 'services_type'
    ]
    ordering = ['-created_at']

    def get_serializer_class(self):
        """Return appropriate serializer"""
        if self.action == 'list':
            return OrderListSerializer
        elif self.action in ['create', 'update', 'partial_update']:
            return OrderCreateUpdateSerializer
        return OrderDetailSerializer
    
    def get_queryset(self):
        """Custom queryset filtering"""
        queryset = super().get_queryset()

        # Users in patient/staff roles can only see specific orders
        user = self.request.user
        if user.is_authenticated:
            # Super admins can see all orders
            if hasattr(user, 'is_super_admin') and user.is_super_admin:
                pass  # No filtering
            # Patients can only see their own orders
            elif hasattr(user, 'is_patient') and user.is_patient:
                queryset = queryset.filter(patient__user=user)
            else:
                # Regular staff can see orders they created
                queryset = queryset.filter(user=user)
        
        # Additional query parameter filtering
        params = self.request.query_params
        
        # Date range filtering
        date_from = params.get('date_from')
        date_to = params.get('date_to')
        if date_from:
            queryset = queryset.filter(created_at__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(created_at__date__lte=date_to)
        
        # Amount range filtering
        min_amount = params.get('min_amount')
        max_amount = params.get('max_amount')
        if min_amount:
            queryset = queryset.filter(total_amount__gte=min_amount)
        if max_amount:
            queryset = queryset.filter(total_amount__lte=max_amount)
        
        return queryset
    
    @extend_schema(
        summary="Get Order Statistics",
        description="Retrieve comprehensive order statistics (Admin only)",
        responses={200: OpenApiResponse(description="Order statistics")},
        tags=['Orders']
    )
    @action(detail=False, methods=['GET'])
    def statistics(self, request):
        """Generate order-wide statistics"""
        # Permission already checked by HMSPermission (view_reports)

        # Aggregate statistics
        stats = Order.objects.aggregate(
            total_orders=Count('id'),
            total_revenue=Sum('total_amount'),
            avg_order_value=Avg('total_amount'),
            paid_orders=Count('id', filter=Q(is_paid=True)),
            unpaid_orders=Count('id', filter=Q(is_paid=False))
        )
        
        # Service type breakdown
        service_breakdown = Order.objects.values('services_type').annotate(
            count=Count('id'),
            total_revenue=Sum('total_amount')
        )
        
        # Status breakdown
        status_breakdown = Order.objects.values('status').annotate(
            count=Count('id'),
            total_revenue=Sum('total_amount')
        )
        
        return Response({
            'success': True,
            'data': {
                'overall_stats': {
                    'total_orders': stats['total_orders'],
                    'total_revenue': float(stats['total_revenue'] or 0),
                    'average_order_value': float(stats['avg_order_value'] or 0),
                    'paid_orders': stats['paid_orders'],
                    'unpaid_orders': stats['unpaid_orders']
                },
                'service_type_breakdown': list(service_breakdown),
                'status_breakdown': list(status_breakdown)
            }
        })
    
    @extend_schema(
        summary="Cancel Order",
        description="Soft cancel an existing order",
        tags=['Orders']
    )
    def destroy(self, request, *args, **kwargs):
        """Custom destroy to soft cancel order"""
        instance = self.get_object()
        
        # Only allow cancellation of pending orders
        if instance.status != 'pending':
            return Response({
                'success': False,
                'error': 'Only pending orders can be cancelled'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Update order status
        instance.status = 'cancelled'
        instance.save()
        
        serializer = self.get_serializer(instance)
        return Response({
            'success': True,
            'message': 'Order cancelled successfully',
            'data': serializer.data
        })

    @extend_schema(
        summary="Create Razorpay Order",
        description="Create order and Razorpay order_id for payment checkout",
        request=RazorpayOrderCreateSerializer,
        responses={201: OpenApiResponse(description="Order created with razorpay_order_id")},
        tags=['Orders - Razorpay']
    )
    @action(detail=False, methods=['POST'], url_path='razorpay/create')
    def razorpay_create_order(self, request):
        """
        Create DigiHMS Order + Razorpay Order
        Returns razorpay_order_id for frontend checkout
        """
        serializer = RazorpayOrderCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            with db_transaction.atomic():
                # 1. Create DigiHMS Order (status='pending')
                order_data = {
                    'tenant_id': request.tenant_id,
                    'patient': serializer.validated_data['patient_id'],
                    'services_type': serializer.validated_data['services_type'],
                    'status': 'pending',
                    'payment_method': 'razorpay',
                    'is_paid': False,
                    'notes': serializer.validated_data.get('notes', ''),
                    'created_by_user_id': request.user_id,
                }

                # Add appointment if provided
                if serializer.validated_data.get('appointment_id'):
                    order_data['appointment'] = serializer.validated_data['appointment_id']

                order = Order.objects.create(**order_data)

                # 2. Create Order Items using OrderCreateUpdateSerializer logic
                items_data = serializer.validated_data['items']
                order_create_serializer = OrderCreateUpdateSerializer()
                validated_items = order_create_serializer.validate_items(items_data)

                for item_data in validated_items:
                    OrderItem.objects.create(
                        tenant_id=request.tenant_id,
                        order=order,
                        content_type=item_data['content_type'],
                        object_id=item_data['object_id'],
                        quantity=item_data['quantity']
                    )

                # 3. Create Order Fees
                fees_data = serializer.validated_data.get('fees', [])
                if fees_data:
                    validated_fees = order_create_serializer.validate_fees(fees_data)
                    subtotal = sum(item.get_total_price() for item in order.order_items.all())

                    for fee_data in validated_fees:
                        from .models import OrderFee
                        fee_type = fee_data['fee_type']

                        # Calculate fee amount if percentage-based
                        if fee_type.is_percentage:
                            amount = subtotal * (fee_type.value / Decimal('100'))
                        else:
                            amount = fee_data.get('amount', fee_type.value)

                        OrderFee.objects.create(
                            tenant_id=request.tenant_id,
                            order=order,
                            fee_type=fee_type,
                            amount=amount
                        )

                # 4. Calculate totals
                order.calculate_totals()
                order.refresh_from_db()

                # 5. Create Razorpay Order
                razorpay_client = RazorpayClient(request.tenant_id)

                razorpay_order = razorpay_client.create_order(
                    amount=order.total_amount,
                    receipt=order.order_number,
                    notes={
                        'order_id': str(order.id),
                        'patient_id': str(order.patient.id),
                        'services_type': order.services_type,
                    }
                )

                # 6. Update Order with Razorpay details
                order.razorpay_order_id = razorpay_order['id']
                order.save(update_fields=['razorpay_order_id'])

                return Response({
                    'success': True,
                    'message': 'Order created successfully',
                    'data': {
                        'order_id': str(order.id),
                        'order_number': order.order_number,
                        'razorpay_order_id': razorpay_order['id'],
                        'razorpay_key_id': razorpay_client.get_public_key(),
                        'amount': float(order.total_amount),
                        'currency': razorpay_order['currency'],
                        'patient_name': order.patient.full_name,
                        'patient_email': order.patient.email,
                        'patient_mobile': order.patient.mobile_primary,
                    }
                }, status=status.HTTP_201_CREATED)

        except ValueError as e:
            # Razorpay not configured
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        summary="Verify Razorpay Payment",
        description="Verify payment signature and complete order",
        request=RazorpayPaymentVerifySerializer,
        responses={200: OpenApiResponse(description="Payment verified and order completed")},
        tags=['Orders - Razorpay']
    )
    @action(detail=False, methods=['POST'], url_path='razorpay/verify')
    def razorpay_verify_payment(self, request):
        """
        Verify Razorpay payment signature
        On success: Mark order as paid, create Visit+OPDBill if consultation
        """
        serializer = RazorpayPaymentVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            with db_transaction.atomic():
                # 1. Get Order
                order = Order.objects.select_for_update().get(
                    id=serializer.validated_data['order_id'],
                    tenant_id=request.tenant_id
                )

                # Check if already paid
                if order.is_paid:
                    return Response({
                        'success': False,
                        'error': 'Order already paid'
                    }, status=status.HTTP_400_BAD_REQUEST)

                # 2. Verify signature
                razorpay_client = RazorpayClient(request.tenant_id)

                is_valid = razorpay_client.verify_payment_signature(
                    razorpay_order_id=serializer.validated_data['razorpay_order_id'],
                    razorpay_payment_id=serializer.validated_data['razorpay_payment_id'],
                    razorpay_signature=serializer.validated_data['razorpay_signature']
                )

                if not is_valid:
                    return Response({
                        'success': False,
                        'error': 'Invalid payment signature'
                    }, status=status.HTTP_400_BAD_REQUEST)

                # 3. Update Order
                order.razorpay_payment_id = serializer.validated_data['razorpay_payment_id']
                order.razorpay_signature = serializer.validated_data['razorpay_signature']
                order.payment_verified = True
                order.is_paid = True
                order.status = 'completed'
                order.save()

                # 4. For consultation orders: Auto-create Visit + OPDBill
                response_data = {}
                if order.services_type == 'consultation' and order.appointment:
                    response_data = self._create_opd_bill_for_consultation(order, request)

                # 5. Return success (Transaction auto-created by signals)
                return Response({
                    'success': True,
                    'message': 'Payment verified successfully',
                    'data': {
                        'order_id': str(order.id),
                        'order_number': order.order_number,
                        'status': order.status,
                        'is_paid': order.is_paid,
                        **response_data
                    }
                })

        except Order.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Order not found'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)

    def _create_opd_bill_for_consultation(self, order, request):
        """
        Helper method to create Visit + OPDBill for consultation order

        Args:
            order: Order instance (consultation type with appointment)
            request: Request object

        Returns:
            dict: Created visit and bill details
        """
        from apps.opd.models import Visit, OPDBill

        appointment = order.appointment

        # 1. Create Visit
        visit = Visit.objects.create(
            tenant_id=order.tenant_id,
            patient=order.patient,
            doctor=appointment.doctor,
            appointment=appointment,
            visit_type='follow_up' if appointment.is_follow_up else 'new',
            status='waiting',
            payment_status='paid',
            total_amount=order.total_amount,
            paid_amount=order.total_amount,
            balance_amount=Decimal('0.00'),
            created_by_id=request.user_id
        )

        # 2. Create OPDBill
        opd_bill = OPDBill.objects.create(
            tenant_id=order.tenant_id,
            visit=visit,
            doctor=appointment.doctor,
            opd_type='consultation',
            charge_type='revisit' if appointment.is_follow_up else 'first_visit',
            total_amount=order.total_amount,
            discount_percent=Decimal('0.00'),
            discount_amount=Decimal('0.00'),
            payable_amount=order.total_amount,
            payment_mode='razorpay',
            received_amount=order.total_amount,
            balance_amount=Decimal('0.00'),
            payment_status='paid',
            billed_by_id=request.user_id,
            payment_details={
                'razorpay_order_id': order.razorpay_order_id,
                'razorpay_payment_id': order.razorpay_payment_id,
                'order_number': order.order_number,
            }
        )

        # 3. Update appointment status
        appointment.status = 'confirmed'
        appointment.save(update_fields=['status'])

        return {
            'visit_id': visit.id,
            'visit_number': visit.visit_number,
            'opd_bill_id': opd_bill.id,
            'bill_number': opd_bill.bill_number,
        }


@method_decorator(csrf_exempt, name='dispatch')
class RazorpayWebhookView(APIView):
    """
    Razorpay Webhook Handler
    Handles payment status updates from Razorpay
    Events: payment.authorized, payment.captured, payment.failed
    """
    permission_classes = []  # Public endpoint, authenticated by signature

    def post(self, request):
        """Handle Razorpay webhook events"""
        try:
            # 1. Get signature from headers
            signature = request.headers.get('X-Razorpay-Signature')
            if not signature:
                return HttpResponse('Signature missing', status=400)

            # 2. Get payload
            payload = request.body

            # 3. Parse event
            event_data = json.loads(payload)
            event_type = event_data.get('event')

            # 4. Get order from razorpay_order_id
            razorpay_order_id = event_data.get('payload', {}).get('payment', {}).get('entity', {}).get('order_id')

            if not razorpay_order_id:
                return HttpResponse('Order ID missing', status=400)

            order = Order.objects.get(razorpay_order_id=razorpay_order_id)

            # 5. Verify signature
            razorpay_client = RazorpayClient(order.tenant_id)
            if not razorpay_client.verify_webhook_signature(payload, signature):
                return HttpResponse('Invalid signature', status=400)

            # 6. Handle event types
            if event_type == 'payment.authorized':
                self._handle_payment_authorized(order, event_data)
            elif event_type == 'payment.failed':
                self._handle_payment_failed(order, event_data)
            elif event_type == 'payment.captured':
                self._handle_payment_captured(order, event_data)

            return HttpResponse('OK', status=200)

        except Order.DoesNotExist:
            return HttpResponse('Order not found', status=404)
        except Exception as e:
            # Log error
            print(f"Webhook error: {str(e)}")
            return HttpResponse(f'Error: {str(e)}', status=500)

    def _handle_payment_authorized(self, order, event_data):
        """Handle payment.authorized event"""
        payment = event_data['payload']['payment']['entity']

        # Update order (payment will be auto-captured if auto_capture=True)
        order.razorpay_payment_id = payment['id']
        order.payment_verified = True
        order.save(update_fields=['razorpay_payment_id', 'payment_verified'])

    def _handle_payment_captured(self, order, event_data):
        """Handle payment.captured event"""
        payment = event_data['payload']['payment']['entity']

        # Mark order as paid
        if not order.is_paid:
            order.is_paid = True
            order.status = 'completed'
            order.save(update_fields=['is_paid', 'status'])

    def _handle_payment_failed(self, order, event_data):
        """Handle payment.failed event"""
        payment = event_data['payload']['payment']['entity']

        error_description = payment.get('error_description', 'Payment failed')

        order.status = 'cancelled'
        order.payment_failed_reason = error_description
        order.save(update_fields=['status', 'payment_failed_reason'])