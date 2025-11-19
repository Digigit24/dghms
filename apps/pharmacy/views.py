from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend

from common.drf_auth import HMSPermission, IsAuthenticated
from common.mixins import TenantViewSetMixin
from django.db.models import Q, Sum, Count, F
from django.utils import timezone
from datetime import timedelta

from .models import (
    ProductCategory,
    PharmacyProduct,
    Cart,
    CartItem,
    PharmacyOrder,
    PharmacyOrderItem
)
from .serializers import (
    ProductCategorySerializer,
    PharmacyProductSerializer,
    CartSerializer,
    CartItemSerializer,
    PharmacyOrderSerializer
)


class ProductCategoryViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    """
    Product Category Management
    Uses JWT-based HMS permissions from the auth backend.
    """
    queryset = ProductCategory.objects.all()
    serializer_class = ProductCategorySerializer
    permission_classes = [HMSPermission]
    hms_module = 'pharmacy'

    action_permission_map = {
        'list': 'view_categories',
        'retrieve': 'view_categories',
        'create': 'manage_categories',
        'update': 'manage_categories',
        'partial_update': 'manage_categories',
        'destroy': 'manage_categories',
    }
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'type', 'description']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']

    def get_queryset(self):
        """Filter active categories by default"""
        queryset = self.queryset
        
        # Option to include inactive categories
        include_inactive = self.request.query_params.get('include_inactive', 'false')
        if include_inactive.lower() != 'true':
            queryset = queryset.filter(is_active=True)
        
        return queryset

    def destroy(self, request, *args, **kwargs):
        """Soft delete - mark as inactive instead of deleting"""
        instance = self.get_object()
        instance.is_active = False
        instance.save()
        return Response({
            'success': True,
            'message': 'Category deactivated successfully'
        }, status=status.HTTP_200_OK)


class PharmacyProductViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    """Pharmacy Product Management"""
    queryset = PharmacyProduct.objects.select_related('category')
    serializer_class = PharmacyProductSerializer
    permission_classes = [HMSPermission]
    hms_module = 'pharmacy'

    action_permission_map = {
        'list': 'view_products',
        'retrieve': 'view_products',
        'create': 'create_product',
        'update': 'edit_product',
        'partial_update': 'edit_product',
        'destroy': 'delete_product',
        'low_stock': 'view_products',
        'expiring_soon': 'view_products',
    }
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter
    ]
    filterset_fields = ['category', 'company', 'is_active']
    search_fields = ['product_name', 'company', 'batch_no']
    ordering_fields = ['product_name', 'mrp', 'selling_price', 'quantity', 'created_at']
    ordering = ['-created_at']

    def get_queryset(self):
        """Filter and annotate products"""
        queryset = self.queryset
        
        # Filter active products by default
        include_inactive = self.request.query_params.get('include_inactive', 'false')
        if include_inactive.lower() != 'true':
            queryset = queryset.filter(is_active=True)
        
        # Additional filtering options
        category_name = self.request.query_params.get('category_name')
        in_stock = self.request.query_params.get('in_stock')
        low_stock = self.request.query_params.get('low_stock')
        
        if category_name:
            queryset = queryset.filter(category__name__icontains=category_name)
        
        if in_stock == 'true':
            queryset = queryset.filter(quantity__gt=0)
        elif in_stock == 'false':
            queryset = queryset.filter(quantity=0)
        
        if low_stock == 'true':
            queryset = queryset.filter(quantity__lte=F('minimum_stock_level'))
        
        return queryset

    @action(detail=False, methods=['get'])
    def low_stock(self, request):
        """Get low stock products"""
        queryset = self.get_queryset()
        low_stock_products = queryset.filter(
            quantity__lte=F('minimum_stock_level'),
            is_active=True
        ).order_by('quantity')
        
        serializer = self.get_serializer(low_stock_products, many=True)
        return Response({
            'success': True,
            'count': low_stock_products.count(),
            'data': serializer.data
        })

    @action(detail=False, methods=['get'])
    def near_expiry(self, request):
        """Get products near expiry (within 90 days by default)"""
        days = int(request.query_params.get('days', 90))
        queryset = self.get_queryset()
        threshold_date = timezone.now().date() + timedelta(days=days)
        
        near_expiry = queryset.filter(
            expiry_date__lte=threshold_date,
            expiry_date__gte=timezone.now().date(),
            is_active=True
        ).order_by('expiry_date')
        
        serializer = self.get_serializer(near_expiry, many=True)
        return Response({
            'success': True,
            'count': near_expiry.count(),
            'threshold_days': days,
            'data': serializer.data
        })

    @action(detail=False, methods=['get'])
    def expired(self, request):
        """Get expired products"""
        queryset = self.get_queryset()
        expired_products = queryset.filter(
            expiry_date__lt=timezone.now().date()
        ).order_by('expiry_date')
        
        serializer = self.get_serializer(expired_products, many=True)
        return Response({
            'success': True,
            'count': expired_products.count(),
            'data': serializer.data
        })

    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """Get pharmacy product statistics"""
        queryset = self.get_queryset()
        
        stats = {
            'total_products': queryset.count(),
            'active_products': queryset.filter(is_active=True).count(),
            'inactive_products': queryset.filter(is_active=False).count(),
            'in_stock_products': queryset.filter(quantity__gt=0, is_active=True).count(),
            'out_of_stock_products': queryset.filter(quantity=0, is_active=True).count(),
            'low_stock_products': queryset.filter(
                quantity__lte=F('minimum_stock_level'),
                quantity__gt=0,
                is_active=True
            ).count(),
            'near_expiry_products': queryset.filter(
                expiry_date__lte=timezone.now().date() + timedelta(days=90),
                expiry_date__gte=timezone.now().date(),
                is_active=True
            ).count(),
            'expired_products': queryset.filter(
                expiry_date__lt=timezone.now().date()
            ).count(),
            'categories': ProductCategory.objects.filter(is_active=True).count(),
        }
        
        return Response({
            'success': True,
            'data': stats
        })


class CartViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    """
    Cart Management
    Uses JWT-based HMS permissions from the auth backend.
    """
    queryset = Cart.objects.prefetch_related('cart_items__product')
    serializer_class = CartSerializer
    permission_classes = [HMSPermission]
    hms_module = 'pharmacy'

    action_permission_map = {
        'list': 'view_cart',
        'retrieve': 'view_cart',
        'create': 'view_cart',
        'update': 'view_cart',
        'partial_update': 'view_cart',
        'destroy': 'view_cart',
        'add_item': 'view_cart',
        'remove_item': 'view_cart',
        'clear': 'view_cart',
        'checkout': 'create_order',
    }

    def get_queryset(self):
        """Only access current user's cart"""
        return self.queryset.filter(user=self.request.user)

    def list(self, request):
        """Get or create user's cart"""
        cart, created = Cart.objects.get_or_create(user=request.user)
        serializer = self.get_serializer(cart)
        return Response({
            'success': True,
            'data': serializer.data
        })

    @action(detail=False, methods=['post'])
    def add_item(self, request):
        """Add item to cart"""
        cart, _ = Cart.objects.get_or_create(user=request.user)
        product_id = request.data.get('product_id')
        quantity = int(request.data.get('quantity', 1))

        # Validate input
        if not product_id:
            return Response({
                'success': False,
                'error': 'Product ID is required'
            }, status=status.HTTP_400_BAD_REQUEST)

        if quantity <= 0:
            return Response({
                'success': False,
                'error': 'Quantity must be greater than 0'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Get product
        try:
            product = PharmacyProduct.objects.get(id=product_id, is_active=True)
        except PharmacyProduct.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Product not found or inactive'
            }, status=status.HTTP_404_NOT_FOUND)

        # Check stock availability
        if product.quantity < quantity:
            return Response({
                'success': False,
                'error': f'Insufficient stock. Available: {product.quantity}'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Add or update cart item
        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            defaults={
                'quantity': quantity,
                'price_at_time': product.selling_price
            }
        )

        if not created:
            # Check if new total quantity exceeds stock
            new_quantity = cart_item.quantity + quantity
            if product.quantity < new_quantity:
                return Response({
                    'success': False,
                    'error': f'Insufficient stock. Available: {product.quantity}, In cart: {cart_item.quantity}'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            cart_item.quantity = new_quantity
            cart_item.price_at_time = product.selling_price  # Update to current price
            cart_item.save()

        serializer = CartSerializer(cart)
        return Response({
            'success': True,
            'message': 'Item added to cart successfully',
            'data': serializer.data
        }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    @action(detail=False, methods=['post'])
    def update_item(self, request):
        """Update cart item quantity"""
        cart = Cart.objects.get(user=request.user)
        cart_item_id = request.data.get('cart_item_id')
        quantity = int(request.data.get('quantity', 1))

        if quantity <= 0:
            return Response({
                'success': False,
                'error': 'Quantity must be greater than 0'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            cart_item = CartItem.objects.get(id=cart_item_id, cart=cart)
        except CartItem.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Cart item not found'
            }, status=status.HTTP_404_NOT_FOUND)

        # Check stock availability
        if cart_item.product.quantity < quantity:
            return Response({
                'success': False,
                'error': f'Insufficient stock. Available: {cart_item.product.quantity}'
            }, status=status.HTTP_400_BAD_REQUEST)

        cart_item.quantity = quantity
        cart_item.save()

        serializer = CartSerializer(cart)
        return Response({
            'success': True,
            'message': 'Cart item updated successfully',
            'data': serializer.data
        })

    @action(detail=False, methods=['post'])
    def remove_item(self, request):
        """Remove item from cart"""
        cart = Cart.objects.get(user=request.user)
        cart_item_id = request.data.get('cart_item_id')

        try:
            cart_item = CartItem.objects.get(id=cart_item_id, cart=cart)
            cart_item.delete()
        except CartItem.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Cart item not found'
            }, status=status.HTTP_404_NOT_FOUND)

        serializer = CartSerializer(cart)
        return Response({
            'success': True,
            'message': 'Item removed from cart successfully',
            'data': serializer.data
        })

    @action(detail=False, methods=['post'])
    def clear(self, request):
        """Clear all items from cart"""
        cart, _ = Cart.objects.get_or_create(user=request.user)
        cart.cart_items.all().delete()

        serializer = CartSerializer(cart)
        return Response({
            'success': True,
            'message': 'Cart cleared successfully',
            'data': serializer.data
        })


class PharmacyOrderViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    """
    Pharmacy Order Management
    Uses JWT-based HMS permissions from the auth backend.
    """
    queryset = PharmacyOrder.objects.prefetch_related('order_items__product')
    serializer_class = PharmacyOrderSerializer
    permission_classes = [HMSPermission]
    hms_module = 'pharmacy'

    action_permission_map = {
        'list': 'view_orders',
        'retrieve': 'view_orders',
        'create': 'create_order',
        'update': 'edit_order',
        'partial_update': 'edit_order',
        'destroy': 'edit_order',
        'cancel': 'edit_order',
        'stats': 'view_orders',
    }
    filter_backends = [
        DjangoFilterBackend,
        filters.OrderingFilter
    ]
    filterset_fields = ['status', 'payment_status']
    ordering_fields = ['created_at', 'total_amount', 'updated_at']
    ordering = ['-created_at']

    def get_queryset(self):
        """Only access current user's orders"""
        return self.queryset.filter(user=self.request.user)

    def create(self, request):
        """Create order from cart"""
        try:
            cart = Cart.objects.get(user=request.user)
        except Cart.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Cart not found'
            }, status=status.HTTP_404_NOT_FOUND)

        # Validate cart
        if cart.total_items == 0:
            return Response({
                'success': False,
                'error': 'Cart is empty'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Validate addresses
        shipping_address = request.data.get('shipping_address', '').strip()
        billing_address = request.data.get('billing_address', '').strip()

        if not shipping_address:
            return Response({
                'success': False,
                'error': 'Shipping address is required'
            }, status=status.HTTP_400_BAD_REQUEST)

        if not billing_address:
            return Response({
                'success': False,
                'error': 'Billing address is required'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Validate stock for all items before creating order
        for cart_item in cart.cart_items.all():
            product = cart_item.product
            if not product.is_active:
                return Response({
                    'success': False,
                    'error': f'Product {product.product_name} is no longer available'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            if product.quantity < cart_item.quantity:
                return Response({
                    'success': False,
                    'error': f'Insufficient stock for {product.product_name}. Available: {product.quantity}'
                }, status=status.HTTP_400_BAD_REQUEST)

        # Create order
        order = PharmacyOrder.objects.create(
            user=request.user,
            total_amount=cart.total_amount,
            shipping_address=shipping_address,
            billing_address=billing_address
        )

        # Convert cart items to order items and update inventory
        for cart_item in cart.cart_items.all():
            # Create order item
            PharmacyOrderItem.objects.create(
                order=order,
                product=cart_item.product,
                quantity=cart_item.quantity,
                price_at_time=cart_item.price_at_time
            )

            # Update product inventory
            product = cart_item.product
            product.quantity -= cart_item.quantity
            product.save()

        # Clear cart
        cart.cart_items.all().delete()

        serializer = self.get_serializer(order)
        return Response({
            'success': True,
            'message': 'Order created successfully',
            'data': serializer.data
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel an order"""
        order = self.get_object()

        # Only allow cancellation if order is pending or processing
        if order.status not in ['pending', 'processing']:
            return Response({
                'success': False,
                'error': f'Cannot cancel order with status: {order.get_status_display()}'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Restore inventory
        for order_item in order.order_items.all():
            product = order_item.product
            product.quantity += order_item.quantity
            product.save()

        # Update order status
        order.status = 'cancelled'
        order.save()

        serializer = self.get_serializer(order)
        return Response({
            'success': True,
            'message': 'Order cancelled successfully',
            'data': serializer.data
        })

    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """Get order statistics for current user"""
        queryset = self.get_queryset()
        
        stats = {
            'total_orders': queryset.count(),
            'pending_orders': queryset.filter(status='pending').count(),
            'processing_orders': queryset.filter(status='processing').count(),
            'shipped_orders': queryset.filter(status='shipped').count(),
            'delivered_orders': queryset.filter(status='delivered').count(),
            'cancelled_orders': queryset.filter(status='cancelled').count(),
            'total_spent': queryset.filter(
                payment_status='paid'
            ).aggregate(total=Sum('total_amount'))['total'] or 0,
        }
        
        return Response({
            'success': True,
            'data': stats
        })