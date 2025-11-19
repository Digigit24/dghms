from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend

from django.db.models import Q, Sum, Count
from django.utils import timezone

# OpenAPI/Swagger documentation
from drf_spectacular.utils import (
    extend_schema,
    extend_schema_view,
    OpenApiParameter,
    OpenApiResponse
)

from common.drf_auth import HMSPermission

from .models import PaymentCategory, Transaction, AccountingPeriod
from .serializers import (
    PaymentCategorySerializer,
    TransactionSerializer,
    AccountingPeriodSerializer
)


@extend_schema_view(
    list=extend_schema(
        summary="List Payment Categories",
        description="Get list of payment categories",
        tags=['Payment Categories']
    ),
    create=extend_schema(
        summary="Create Payment Category",
        description="Create a new payment category (Admin only)",
        tags=['Payment Categories']
    ),
    retrieve=extend_schema(
        summary="Get Payment Category Details",
        description="Retrieve details of a specific payment category",
        tags=['Payment Categories']
    )
)
class PaymentCategoryViewSet(viewsets.ModelViewSet):
    """Payment Category Management"""
    queryset = PaymentCategory.objects.all()
    serializer_class = PaymentCategorySerializer
    permission_classes = [HMSPermission]
    hms_module = 'payments'

    action_permission_map = {
        'list': 'view_categories',
        'retrieve': 'view_categories',
        'create': 'manage_categories',
        'update': 'manage_categories',
        'partial_update': 'manage_categories',
        'destroy': 'manage_categories',
    }

    filter_backends = [filters.SearchFilter]
    search_fields = ['name', 'description']
    
    def list(self, request, *args, **kwargs):
        """List categories with optional filtering"""
        queryset = self.filter_queryset(self.get_queryset())
        
        # Optional filtering by category type
        category_type = request.query_params.get('category_type')
        if category_type:
            queryset = queryset.filter(category_type=category_type)
        
        serializer = self.get_serializer(queryset, many=True)
        return Response({
            'success': True,
            'data': serializer.data
        })


@extend_schema_view(
    list=extend_schema(
        summary="List Transactions",
        description="Get list of financial transactions with extensive filtering",
        parameters=[
            OpenApiParameter(name='transaction_type', type=str, description='Filter by transaction type'),
            OpenApiParameter(name='payment_method', type=str, description='Filter by payment method'),
            OpenApiParameter(name='category', type=str, description='Filter by payment category'),
            OpenApiParameter(name='date_from', type=str, description='Transactions from date (YYYY-MM-DD)'),
            OpenApiParameter(name='date_to', type=str, description='Transactions to date (YYYY-MM-DD)'),
            OpenApiParameter(name='min_amount', type=float, description='Minimum transaction amount'),
            OpenApiParameter(name='max_amount', type=float, description='Maximum transaction amount'),
            OpenApiParameter(name='is_reconciled', type=bool, description='Filter by reconciliation status'),
        ],
        tags=['Transactions']
    ),
    create=extend_schema(
        summary="Create Transaction",
        description="Record a new financial transaction",
        tags=['Transactions']
    ),
    retrieve=extend_schema(
        summary="Get Transaction Details",
        description="Retrieve details of a specific transaction",
        tags=['Transactions']
    )
)
class TransactionViewSet(viewsets.ModelViewSet):
    """
    Comprehensive Financial Transaction Management
    """
    queryset = Transaction.objects.select_related(
        'category', 'user', 'reconciled_by'
    )
    serializer_class = TransactionSerializer
    permission_classes = [HMSPermission]
    hms_module = 'payments'

    action_permission_map = {
        'list': 'view_transactions',
        'retrieve': 'view_transactions',
        'create': 'create_transaction',
        'update': 'edit_transaction',
        'partial_update': 'edit_transaction',
        'destroy': 'delete_transaction',
        'statistics': 'view_reports',
        'reconcile': 'reconcile_transactions',
    }

    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter
    ]
    filterset_fields = [
        'transaction_type',
        'payment_method',
        'category',
        'is_reconciled'
    ]
    search_fields = [
        'transaction_number',
        'description',
        'user__first_name',
        'user__last_name'
    ]
    ordering_fields = [
        'created_at',
        'amount',
        'transaction_type'
    ]
    ordering = ['-created_at']
    
    def get_queryset(self):
        """Custom queryset filtering"""
        queryset = super().get_queryset()

        # Users can only see their own transactions
        # unless they are super admins
        user = self.request.user
        if user.is_authenticated:
            # Super admins can see all transactions
            if not (hasattr(user, 'is_super_admin') and user.is_super_admin):
                # Regular users only see their own
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
            queryset = queryset.filter(amount__gte=min_amount)
        if max_amount:
            queryset = queryset.filter(amount__lte=max_amount)
        
        return queryset
    
    @extend_schema(
        summary="Get Transaction Statistics",
        description="Retrieve comprehensive transaction statistics (Admin only)",
        responses={200: OpenApiResponse(description="Transaction statistics")},
        tags=['Transactions']
    )
    @action(detail=False, methods=['GET'])
    def statistics(self, request):
        """Generate transaction-wide statistics"""
        # Permission already checked by HMSPermission (view_reports)

        # Aggregate statistics
        stats = Transaction.objects.aggregate(
            total_transactions=Count('id'),
            total_amount=Sum('amount'),
            total_payments=Sum('amount', filter=Q(transaction_type='payment')),
            total_expenses=Sum('amount', filter=Q(transaction_type='expense')),
            total_refunds=Sum('amount', filter=Q(transaction_type='refund'))
        )
        
        # Payment method breakdown
        payment_method_breakdown = Transaction.objects.values('payment_method').annotate(
            count=Count('id'),
            total_amount=Sum('amount')
        )
        
        # Transaction type breakdown
        transaction_type_breakdown = Transaction.objects.values('transaction_type').annotate(
            count=Count('id'),
            total_amount=Sum('amount')
        )
        
        return Response({
            'success': True,
            'data': {
                'overall_stats': {
                    'total_transactions': stats['total_transactions'],
                    'total_amount': float(stats['total_amount'] or 0),
                    'total_payments': float(stats['total_payments'] or 0),
                    'total_expenses': float(stats['total_expenses'] or 0),
                    'total_refunds': float(stats['total_refunds'] or 0)
                },
                'payment_method_breakdown': list(payment_method_breakdown),
                'transaction_type_breakdown': list(transaction_type_breakdown)
            }
        })
    
    @extend_schema(
        summary="Reconcile Transaction",
        description="Mark a transaction as reconciled (Admin only)",
        responses={
            200: TransactionSerializer,
            403: OpenApiResponse(description="Permission denied")
        },
        tags=['Transactions']
    )
    @action(detail=True, methods=['POST'])
    def reconcile(self, request, pk=None):
        """Mark a transaction as reconciled"""
        # Permission already checked by HMSPermission (reconcile_transactions)

        transaction = self.get_object()
        
        # Check if already reconciled
        if transaction.is_reconciled:
            return Response({
                'success': False,
                'error': 'Transaction is already reconciled'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Mark as reconciled
        transaction.is_reconciled = True
        transaction.reconciled_at = timezone.now()
        transaction.reconciled_by = request.user
        transaction.save()
        
        serializer = self.get_serializer(transaction)
        return Response({
            'success': True,
            'message': 'Transaction reconciled successfully',
            'data': serializer.data
        })


@extend_schema_view(
    list=extend_schema(
        summary="List Accounting Periods",
        description="Get list of accounting periods with filtering",
        parameters=[
            OpenApiParameter(name='period_type', type=str, description='Filter by period type'),
            OpenApiParameter(name='is_closed', type=bool, description='Filter by closed status'),
            OpenApiParameter(name='date_from', type=str, description='Periods starting from (YYYY-MM-DD)'),
            OpenApiParameter(name='date_to', type=str, description='Periods ending by (YYYY-MM-DD)'),
        ],
        tags=['Accounting Periods']
    ),
    create=extend_schema(
        summary="Create Accounting Period",
        description="Create a new accounting period (Admin only)",
        tags=['Accounting Periods']
    ),
    retrieve=extend_schema(
        summary="Get Accounting Period Details",
        description="Retrieve details of a specific accounting period",
        tags=['Accounting Periods']
    )
)
class AccountingPeriodViewSet(viewsets.ModelViewSet):
    """
    Accounting Period Management
    Supports CRUD operations and financial reporting
    """
    queryset = AccountingPeriod.objects.all()
    serializer_class = AccountingPeriodSerializer
    permission_classes = [HMSPermission]
    hms_module = 'payments'

    action_permission_map = {
        'list': 'view_periods',
        'retrieve': 'view_periods',
        'create': 'manage_periods',
        'update': 'manage_periods',
        'partial_update': 'manage_periods',
        'destroy': 'manage_periods',
        'recalculate': 'manage_periods',
        'close': 'close_periods',
    }

    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter
    ]
    filterset_fields = [
        'period_type',
        'is_closed'
    ]
    search_fields = ['name']
    ordering_fields = [
        'start_date',
        'end_date',
        'total_income',
        'total_expenses'
    ]
    ordering = ['-start_date']
    
    def get_queryset(self):
        """Custom queryset filtering"""
        queryset = super().get_queryset()
        
        # Additional query parameter filtering
        params = self.request.query_params
        
        # Date range filtering
        date_from = params.get('date_from')
        date_to = params.get('date_to')
        if date_from:
            queryset = queryset.filter(start_date__gte=date_from)
        if date_to:
            queryset = queryset.filter(end_date__lte=date_to)
        
        return queryset
    
    @extend_schema(
        summary="Recalculate Financial Summary",
        description="Force recalculation of financial summary for an accounting period (Admin only)",
        responses={
            200: AccountingPeriodSerializer,
            403: OpenApiResponse(description="Permission denied")
        },
        tags=['Accounting Periods']
    )
    @action(detail=True, methods=['POST'])
    def recalculate(self, request, pk=None):
        """Force recalculation of financial summary"""
        # Permission already checked by HMSPermission (manage_periods)

        accounting_period = self.get_object()
        
        # Recalculate financial summary
        summary = accounting_period.calculate_financial_summary()
        
        serializer = self.get_serializer(accounting_period)
        return Response({
            'success': True,
            'message': 'Financial summary recalculated successfully',
            'data': serializer.data,
            'summary': summary
        })
    
    @extend_schema(
        summary="Close Accounting Period",
        description="Close an accounting period and lock its financial data (Admin only)",
        responses={
            200: AccountingPeriodSerializer,
            403: OpenApiResponse(description="Permission denied")
        },
        tags=['Accounting Periods']
    )
    @action(detail=True, methods=['POST'])
    def close(self, request, pk=None):
        """Close the accounting period"""
        # Permission already checked by HMSPermission (close_periods)

        accounting_period = self.get_object()
        
        # Check if already closed
        if accounting_period.is_closed:
            return Response({
                'success': False,
                'error': 'Accounting period is already closed'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Close the period
        accounting_period.is_closed = True
        accounting_period.closed_at = timezone.now()
        accounting_period.closed_by = request.user
        
        # Recalculate financial summary before closing
        accounting_period.calculate_financial_summary()
        accounting_period.save()
        
        serializer = self.get_serializer(accounting_period)
        return Response({
            'success': True,
            'message': 'Accounting period closed successfully',
            'data': serializer.data
        })