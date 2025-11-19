from datetime import timezone
from rest_framework import serializers
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q

from .models import PaymentCategory, Transaction, AccountingPeriod


class PaymentCategorySerializer(serializers.ModelSerializer):
    """Serializer for Payment Categories"""
    class Meta:
        model = PaymentCategory
        fields = '__all__'


class TransactionRelatedObjectSerializer(serializers.Serializer):
    """
    Dynamic serializer for related objects in transactions
    """
    content_type = serializers.SerializerMethodField()
    object_details = serializers.SerializerMethodField()
    
    def get_content_type(self, obj):
        """Get content type name"""
        return obj.content_type.model if obj.content_type else None
    
    def get_object_details(self, obj):
        """
        Retrieve dynamic object details based on content type
        """
        if not obj.related_object:
            return None
        
        # Map different object types to their representations
        content_type_model = obj.content_type.model
        
        if content_type_model == 'order':
            return {
                'id': obj.related_object.id,
                'order_number': obj.related_object.order_number,
                'total_amount': str(obj.related_object.total_amount)
            }
        elif content_type_model == 'appointment':
            return {
                'id': obj.related_object.id,
                'appointment_id': obj.related_object.appointment_id,
                'doctor': str(obj.related_object.doctor)
            }
        
        # Add more content type mappings as needed
        return str(obj.related_object)


class TransactionSerializer(serializers.ModelSerializer):
    """Serializer for Financial Transactions"""
    category = PaymentCategorySerializer(read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=PaymentCategory.objects.all(),
        source='category',
        write_only=True
    )

    related_object_details = serializers.SerializerMethodField()

    class Meta:
        model = Transaction
        fields = [
            'id', 'transaction_number', 'amount',
            'category', 'category_id',
            'transaction_type', 'payment_method',
            'user_id',
            'description',
            'content_type', 'object_id', 'related_object_details',
            'is_reconciled', 'reconciled_at', 'reconciled_by_id',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'transaction_number',
            'created_at', 'updated_at',
            'reconciled_at', 'reconciled_by_id'
        ]
    
    def get_related_object_details(self, obj):
        """Get details of the related object"""
        if obj.content_type and obj.related_object:
            serializer = TransactionRelatedObjectSerializer(obj)
            return serializer.data
        return None
    
    def validate(self, attrs):
        """
        Additional validation for transactions
        """
        # Validate related object if content type is provided
        content_type = attrs.get('content_type')
        object_id = attrs.get('object_id')
        
        if content_type and object_id:
            try:
                related_object = content_type.get_object_for_this_type(pk=object_id)
                attrs['related_object'] = related_object
            except content_type.model_class().DoesNotExist:
                raise serializers.ValidationError({
                    'object_id': f'Invalid object ID for {content_type.model}'
                })
        
        return attrs
    
    def create(self, validated_data):
        """
        Custom create method to handle related objects
        """
        # Remove write-only fields
        request = self.context.get('request')
        
        # Set user from request if not provided
        if request and request.user and not validated_data.get('user'):
            validated_data['user'] = request.user
        
        return super().create(validated_data)


class AccountingPeriodSerializer(serializers.ModelSerializer):
    """Serializer for Accounting Periods"""

    class Meta:
        model = AccountingPeriod
        fields = [
            'id', 'name', 'start_date', 'end_date',
            'period_type', 'total_income', 'total_expenses',
            'net_profit', 'is_closed', 'closed_at',
            'closed_by_id'
        ]
        read_only_fields = [
            'total_income', 'total_expenses',
            'net_profit', 'closed_at', 'closed_by_id'
        ]
    
    def validate(self, attrs):
        """
        Validate accounting period dates
        """
        start_date = attrs.get('start_date')
        end_date = attrs.get('end_date')
        
        if start_date and end_date and start_date >= end_date:
            raise serializers.ValidationError({
                'end_date': 'End date must be after start date'
            })
        
        # Check for overlapping periods
        existing_periods = AccountingPeriod.objects.filter(
            Q(start_date__lte=attrs.get('end_date')) &
            Q(end_date__gte=attrs.get('start_date'))
        )
        
        if existing_periods.exists():
            raise serializers.ValidationError({
                'start_date': 'An accounting period already exists for this date range'
            })
        
        return attrs
    
    def create(self, validated_data):
        """
        Custom create method to set closed_by for closing an accounting period
        """
        request = self.context.get('request')
        
        # Set closed_by for closing an accounting period
        if validated_data.get('is_closed') and request:
            validated_data['closed_by'] = request.user
            validated_data['closed_at'] = timezone.now()
        
        # Calculate financial summary during creation
        period = AccountingPeriod.objects.create(**validated_data)
        period.calculate_financial_summary()
        
        return period