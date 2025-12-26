from rest_framework import serializers
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from decimal import Decimal

from .models import Order, OrderItem, OrderFee, FeeType
from apps.patients.models import PatientProfile
from apps.appointments.models import Appointment


class FeeTypeSerializer(serializers.ModelSerializer):
    """Serializer for Fee Types"""
    class Meta:
        model = FeeType
        fields = '__all__'


class OrderFeeSerializer(serializers.ModelSerializer):
    """Serializer for Order Fees"""
    fee_type = FeeTypeSerializer(read_only=True)
    fee_type_id = serializers.PrimaryKeyRelatedField(
        queryset=FeeType.objects.all(), 
        source='fee_type', 
        write_only=True
    )

    class Meta:
        model = OrderFee
        fields = ['fee_type', 'fee_type_id', 'amount']


class OrderItemSerializer(serializers.ModelSerializer):
    """
    Serializer for Order Items with dynamic service information
    """
    service_type = serializers.SerializerMethodField()
    service_details = serializers.SerializerMethodField()
    total_price = serializers.SerializerMethodField()
    
    class Meta:
        model = OrderItem
        fields = [
            'id', 
            'service_type', 
            'service_details',
            'quantity', 
            'total_price'
        ]
    
    def get_service_type(self, obj):
        """Get the content type of the service"""
        return obj.content_type.model
    
    def get_service_details(self, obj):
        """
        Retrieve dynamic service details based on content type
        """
        service = obj.service
        
        if obj.content_type.model == 'appointment':
            return {
                'id': service.id,
                'appointment_id': service.appointment_id,
                'doctor_name': f"{service.doctor.user.first_name} {service.doctor.user.last_name}",
                'appointment_type': service.appointment_type.name,
                'consultation_fee': str(service.consultation_fee)
            }
        
        return {}
    
    def get_total_price(self, obj):
        """Calculate total price dynamically"""
        return obj.get_total_price()


class OrderCreateUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for Order Creation and Update
    Allows adding multiple service items and fees
    """
    patient_id = serializers.PrimaryKeyRelatedField(
        queryset=PatientProfile.objects.all(), 
        source='patient'
    )
    
    # Polymorphic service items
    items = serializers.ListField(
        child=serializers.DictField(),
        write_only=True,
        required=False
    )
    
    # Fees
    fees = serializers.ListField(
        child=serializers.DictField(),
        write_only=True,
        required=False
    )
    
    class Meta:
        model = Order
        fields = [
            'id', 'order_number', 'patient_id', 
            'services_type', 'status', 
            'payment_method', 'is_paid',
            'notes', 'items', 'fees',
            'subtotal', 'total_fees', 'total_amount'
        ]
        read_only_fields = [
            'id', 'order_number', 
            'subtotal', 'total_fees', 'total_amount'
        ]
    
    def validate_items(self, items):
        """
        Validate service items before order creation
        Checks:
        - Service exists
        - Proper content type
        - Quantity 
        """
        validated_items = []
        
        if not items:
            raise ValidationError("At least one service item is required")
        
        for item in items:
            # Required fields validation
            required_fields = ['service_id', 'content_type', 'quantity']
            for field in required_fields:
                if field not in item:
                    raise ValidationError(f"Missing {field} in service item")
            
            try:
                # Validate content type
                content_type = ContentType.objects.get(model=item['content_type'])
                model_class = content_type.model_class()
                
                # Check service existence
                service = model_class.objects.get(id=item['service_id'])
                
                validated_items.append({
                    'content_type': content_type,
                    'object_id': service.id,
                    'service': service,
                    'quantity': item['quantity']
                })
            
            except (ContentType.DoesNotExist, model_class.DoesNotExist):
                raise ValidationError(f"Invalid service: {item}")
        
        return validated_items
    
    def validate_fees(self, fees):
        """
        Validate fees before order creation
        """
        validated_fees = []
        
        if fees:
            for fee_data in fees:
                # Required fields
                if 'fee_type_id' not in fee_data:
                    raise ValidationError("Fee type ID is required")
                
                try:
                    fee_type = FeeType.objects.get(id=fee_data['fee_type_id'])
                    
                    # If it's a percentage-based fee, calculate the amount
                    amount = fee_data.get('amount')
                    if fee_type.is_percentage and amount is None:
                        # Will be calculated during order creation
                        amount = None
                    
                    validated_fees.append({
                        'fee_type': fee_type,
                        'amount': amount
                    })
                
                except FeeType.DoesNotExist:
                    raise ValidationError(f"Invalid fee type: {fee_data['fee_type_id']}")
        
        return validated_fees
    
    def validate(self, attrs):
        """
        Cross-field validation
        """
        # Validate patient
        patient_id = self.initial_data.get('patient_id')
        
        # Validate patient exists
        try:
            patient = PatientProfile.objects.get(id=patient_id)
            attrs['patient'] = patient
        except PatientProfile.DoesNotExist:
            raise ValidationError({'patient_id': 'Invalid patient ID'})
        
        # Validate payment details
        if attrs.get('is_paid') and not attrs.get('payment_method'):
            raise ValidationError({
                'payment_method': 'Payment method is required for paid orders'
            })
        
        return attrs
    
    def create(self, validated_data):
        """
        Custom create method to handle polymorphic order items and fees
        """
        # Remove write-only fields
        items_data = validated_data.pop('items', [])
        fees_data = validated_data.pop('fees', [])
        
        # Create order
        order = Order.objects.create(**validated_data)
        
        # Create order items
        for item_data in items_data:
            OrderItem.objects.create(
                order=order,
                content_type=item_data['content_type'],
                object_id=item_data['object_id'],
                quantity=item_data['quantity']
            )
        
        # Create order fees
        subtotal = sum(
            item.get_total_price() 
            for item in order.order_items.all()
        )
        
        for fee_data in fees_data:
            fee_type = fee_data['fee_type']
            
            # Calculate fee amount if percentage-based
            if fee_type.is_percentage:
                amount = subtotal * (fee_type.value / Decimal('100'))
            else:
                amount = fee_data.get('amount', fee_type.value)
            
            OrderFee.objects.create(
                order=order,
                fee_type=fee_type,
                amount=amount
            )
        
        # Calculate totals
        order.calculate_totals()
        
        return order
    
    def update(self, instance, validated_data):
        """
        Custom update method
        """
        # Remove write-only fields
        items_data = validated_data.pop('items', [])
        fees_data = validated_data.pop('fees', [])
        
        # Update order base fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        # Update or create order items
        if items_data:
            # Clear existing items
            instance.order_items.all().delete()
            
            # Create new items
            for item_data in items_data:
                OrderItem.objects.create(
                    order=instance,
                    content_type=item_data['content_type'],
                    object_id=item_data['object_id'],
                    quantity=item_data['quantity']
                )
        
        # Update or create fees
        if fees_data:
            # Clear existing fees
            instance.order_fee_details.all().delete()
            
            # Calculate subtotal
            subtotal = sum(
                item.get_total_price() 
                for item in instance.order_items.all()
            )
            
            # Create new fees
            for fee_data in fees_data:
                fee_type = fee_data['fee_type']
                
                # Calculate fee amount if percentage-based
                if fee_type.is_percentage:
                    amount = subtotal * (fee_type.value / Decimal('100'))
                else:
                    amount = fee_data.get('amount', fee_type.value)
                
                OrderFee.objects.create(
                    order=instance,
                    fee_type=fee_type,
                    amount=amount
                )
        
        # Save and recalculate totals
        instance.save()
        instance.calculate_totals()
        
        return instance


class OrderDetailSerializer(serializers.ModelSerializer):
    """
    Comprehensive Order Details Serializer
    Includes items, fees, and related information
    """
    patient = serializers.StringRelatedField()
    order_items = OrderItemSerializer(many=True, read_only=True)
    order_fees = OrderFeeSerializer(
        source='order_fee_details', 
        many=True, 
        read_only=True
    )
    
    class Meta:
        model = Order
        fields = [
            'id', 'order_number', 'patient', 
            'services_type', 'status', 
            'payment_method', 'is_paid',
            'subtotal', 'total_fees', 'total_amount', 
            'notes', 'created_at', 'updated_at',
            'order_items', 'order_fees'
        ]
        read_only_fields = [
            'id', 'order_number', 
            'subtotal', 'total_fees', 'total_amount',
            'created_at', 'updated_at'
        ]


class OrderListSerializer(serializers.ModelSerializer):
    """
    Simplified Order List Serializer
    Provides overview information for listings
    """
    patient_name = serializers.SerializerMethodField()
    
    class Meta:
        model = Order
        fields = [
            'id', 'order_number', 'patient_name', 
            'services_type', 'status', 
            'payment_method', 'is_paid',
            'total_amount', 'created_at'
        ]
    
    def get_patient_name(self, obj):
        return obj.patient.full_name if obj.patient else 'Unknown'


class RazorpayOrderCreateSerializer(serializers.Serializer):
    """
    Serializer for creating Razorpay order
    Step 1: Frontend calls this to get razorpay_order_id for checkout
    """
    patient_id = serializers.PrimaryKeyRelatedField(
        queryset=PatientProfile.objects.all(),
        help_text="Patient ID for this order"
    )
    services_type = serializers.ChoiceField(
        choices=Order.SERVICE_TYPE_CHOICES,
        help_text="Type of service (consultation, diagnostic, etc.)"
    )
    appointment_id = serializers.PrimaryKeyRelatedField(
        queryset=Appointment.objects.all(),
        required=False,
        allow_null=True,
        help_text="Required for consultation orders"
    )
    items = serializers.ListField(
        child=serializers.DictField(),
        help_text="Service items (same format as Order creation)"
    )
    fees = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        help_text="Additional fees (optional)"
    )
    notes = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Order notes"
    )

    def validate(self, attrs):
        """
        Validate that appointment_id is provided for consultation orders
        """
        if attrs.get('services_type') == 'consultation':
            if not attrs.get('appointment_id'):
                raise serializers.ValidationError({
                    'appointment_id': 'Required for consultation orders'
                })
        return attrs


class RazorpayPaymentVerifySerializer(serializers.Serializer):
    """
    Serializer for verifying Razorpay payment
    Step 2: Frontend calls this after payment success with payment details
    """
    order_id = serializers.UUIDField(
        help_text="DigiHMS Order UUID"
    )
    razorpay_order_id = serializers.CharField(
        max_length=255,
        help_text="Razorpay order ID"
    )
    razorpay_payment_id = serializers.CharField(
        max_length=255,
        help_text="Razorpay payment ID"
    )
    razorpay_signature = serializers.CharField(
        max_length=255,
        help_text="Razorpay payment signature for verification"
    )