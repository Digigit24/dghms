# opd/serializers.py
from rest_framework import serializers
from django.db import transaction, models
from django.utils import timezone
from decimal import Decimal

from .models import (
    Visit, OPDBill, OPDBillItem, ProcedureMaster, ProcedurePackage,
  ClinicalNote,
    VisitFinding, VisitAttachment,
    ClinicalNoteTemplateGroup, ClinicalNoteTemplate,
    ClinicalNoteTemplateField, ClinicalNoteTemplateFieldOption,
    ClinicalNoteTemplateResponse, ClinicalNoteTemplateFieldResponse,
    ClinicalNoteResponseTemplate
)
from apps.patients.models import PatientProfile
from apps.doctors.models import DoctorProfile
from apps.appointments.models import Appointment


# ============================================================================
# VISIT SERIALIZERS
# ============================================================================

class VisitListSerializer(serializers.ModelSerializer):
    """Serializer for listing visits (lightweight)"""
    
    patient_name = serializers.CharField(source='patient.full_name', read_only=True)
    patient_id = serializers.CharField(source='patient.patient_id', read_only=True)
    doctor_name = serializers.CharField(source='doctor.full_name', read_only=True)
    waiting_time = serializers.SerializerMethodField()
    
    class Meta:
        model = Visit
        fields = [
            'id', 'visit_number', 'patient', 'patient_name', 'patient_id',
            'doctor', 'doctor_name', 'visit_date', 'visit_type', 'status',
            'queue_position', 'payment_status', 'total_amount', 'balance_amount',
            'waiting_time', 'entry_time', 'is_follow_up'
        ]
        read_only_fields = ['visit_number', 'visit_date', 'entry_time']
    
    def get_waiting_time(self, obj):
        """Get waiting time in minutes"""
        return obj.calculate_waiting_time()


class VisitDetailSerializer(serializers.ModelSerializer):
    """Detailed visit serializer with all relationships"""
    
    patient_name = serializers.CharField(source='patient.full_name', read_only=True)
    patient_details = serializers.SerializerMethodField()
    doctor_name = serializers.CharField(source='doctor.full_name', read_only=True)
    doctor_details = serializers.SerializerMethodField()
    referred_by_name = serializers.CharField(source='referred_by.full_name', read_only=True)
    waiting_time = serializers.SerializerMethodField()
    has_opd_bill = serializers.SerializerMethodField()
    has_clinical_note = serializers.SerializerMethodField()
    
    class Meta:
        model = Visit
        fields = '__all__'
        read_only_fields = [
            'visit_number', 'visit_date', 'entry_time', 
            'created_at', 'updated_at'
        ]
    
    def get_patient_details(self, obj):
        """Get essential patient details"""
        return {
            'patient_id': obj.patient.patient_id,
            'full_name': obj.patient.full_name,
            'age': obj.patient.age,
            'gender': obj.patient.gender,
            'blood_group': obj.patient.blood_group,
            'mobile': obj.patient.mobile_primary,
        }
    
    def get_doctor_details(self, obj):
        """Get essential doctor details"""
        if obj.doctor:
            return {
                'id': obj.doctor.id,
                'full_name': obj.doctor.full_name,
                'specialties': [s.name for s in obj.doctor.specialties.all()],
                'consultation_fee': str(obj.doctor.consultation_fee),
                'follow_up_fee': str(obj.doctor.follow_up_fee),
            }
        return None
    
    def get_waiting_time(self, obj):
        """Get waiting time"""
        return obj.calculate_waiting_time()
    
    def get_has_opd_bill(self, obj):
        """Check if visit has OPD bill"""
        return hasattr(obj, 'opd_bill')
    
    def get_has_clinical_note(self, obj):
        """Check if visit has clinical note"""
        return hasattr(obj, 'clinical_note')


class VisitCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating visits"""
    
    class Meta:
        model = Visit
        fields = [
            'patient', 'doctor', 'appointment', 'visit_type',
            'is_follow_up', 'referred_by', 'status', 'queue_position'
        ]
    
    def validate(self, data):
        """Validate visit data"""
        # Validate follow-up without original appointment
        if data.get('is_follow_up') and not data.get('appointment'):
            raise serializers.ValidationError({
                'appointment': 'Follow-up visits should be linked to an appointment'
            })
        
        return data
    
    def create(self, validated_data):
        """Create visit with auto-generated visit number"""
        request = self.context.get('request')

        # Add tenant_id from request context
        if request and hasattr(request, 'tenant_id'):
            validated_data['tenant_id'] = request.tenant_id

        # Add created_by_id from request context
        if request and hasattr(request, 'user_id'):
            validated_data['created_by_id'] = request.user_id

        return super().create(validated_data)


# ============================================================================
# OPD BILL SERIALIZERS
# ============================================================================

class OPDBillItemSerializer(serializers.ModelSerializer):
    """Serializer for OPD Bill Items."""

    class Meta:
        model = OPDBillItem
        fields = [
            'id', 'bill', 'item_name', 'source',
            'quantity', 'system_calculated_price', 'unit_price',
            'total_price', 'is_price_overridden', 'notes',
            'origin_content_type', 'origin_object_id'
        ]
        read_only_fields = [
            'total_price', 'system_calculated_price', 'is_price_overridden'
        ]


class OPDBillListSerializer(serializers.ModelSerializer):
    """Serializer for listing OPD bills"""
    
    patient_name = serializers.CharField(source='visit.patient.full_name', read_only=True)
    doctor_name = serializers.CharField(source='doctor.full_name', read_only=True)
    visit_number = serializers.CharField(source='visit.visit_number', read_only=True)
    items = OPDBillItemSerializer(many=True, read_only=True)
    
    class Meta:
        model = OPDBill
        fields = [
            'id', 'bill_number', 'visit', 'visit_number', 'patient_name',
            'doctor', 'doctor_name', 'bill_date', 'opd_type', 'charge_type',
            'total_amount', 'payable_amount', 'received_amount',
            'balance_amount', 'payment_status', 'items'
        ]
        read_only_fields = ['bill_number', 'bill_date']


class OPDBillDetailSerializer(serializers.ModelSerializer):
    """Detailed OPD bill serializer"""
    
    patient_name = serializers.CharField(source='visit.patient.full_name', read_only=True)
    doctor_name = serializers.CharField(source='doctor.full_name', read_only=True)
    visit_number = serializers.CharField(source='visit.visit_number', read_only=True)
    items = OPDBillItemSerializer(many=True, read_only=True)

    class Meta:
        model = OPDBill
        fields = '__all__'
        read_only_fields = [
            'bill_number', 'bill_date', 'payable_amount', 
            'balance_amount', 'payment_status', 'created_at', 'updated_at'
        ]


class OPDBillCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating OPD bills"""
    
    class Meta:
        model = OPDBill
        fields = [
            'id', 'visit', 'doctor', 'opd_type', 'opd_subtype', 'charge_type',
            'diagnosis', 'remarks', 'total_amount', 'discount_percent',
            'payment_mode', 'payment_details', 'received_amount'
        ]
        read_only_fields = ['id']
    
    def validate(self, data):
        """Validate bill data"""
        # Validate received amount doesn't exceed payable amount
        if self.instance:
            # For updates, calculate payable amount from instance + updates
            total = self.instance.total_amount

            # Check if discount is being changed
            if 'discount_percent' in data and data['discount_percent'] > Decimal('0'):
                discount_amount = (total * data['discount_percent'] / Decimal('100.00')).quantize(Decimal('0.01'))
            elif 'discount_amount' in data:
                discount_amount = data['discount_amount']
            else:
                discount_amount = self.instance.discount_amount

            payable_amount = total - discount_amount
            received = data.get('received_amount', self.instance.received_amount)

            if received > payable_amount:
                raise serializers.ValidationError({
                    'received_amount': f'Received amount cannot exceed payable amount ({payable_amount})'
                })
        else:
            # For creates, skip this validation since total will be calculated from items
            # The model's save() method will handle this
            pass

        return data
    
    def create(self, validated_data):
        """Create OPD bill with auto-calculations"""
        request = self.context.get('request')

        # Add tenant_id from request context
        if request and hasattr(request, 'tenant_id'):
            validated_data['tenant_id'] = request.tenant_id

        # Add billed_by_id from request context
        if request and hasattr(request, 'user_id'):
            validated_data['billed_by_id'] = request.user_id

        return super().create(validated_data)

class ProcedureMasterListSerializer(serializers.ModelSerializer):

    """Serializer for listing procedure masters"""
    
    class Meta:
        model = ProcedureMaster
        fields = [
            'id', 'name', 'code', 'category', 'default_charge', 'is_active'
        ]


class ProcedureMasterDetailSerializer(serializers.ModelSerializer):

    """Detailed procedure master serializer"""
    
    class Meta:
        model = ProcedureMaster
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at']


class ProcedureMasterCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating procedure masters"""

    class Meta:
        model = ProcedureMaster
        fields = [
            'name', 'code', 'category', 'description',
            'default_charge', 'is_active'
        ]

    def validate_code(self, value):
        """Validate unique code"""
        if self.instance is None:  # Only for creation
            if ProcedureMaster.objects.filter(code=value).exists():
                raise serializers.ValidationError("Procedure code already exists")
        return value

    def create(self, validated_data):
        """Create procedure master with tenant_id"""
        request = self.context.get('request')

        # Add tenant_id from request context
        if request and hasattr(request, 'tenant_id'):
            validated_data['tenant_id'] = request.tenant_id

        return super().create(validated_data)


# ============================================================================
# PROCEDURE PACKAGE SERIALIZERS
# ============================================================================

class ProcedurePackageListSerializer(serializers.ModelSerializer):
    """Serializer for listing procedure packages"""
    
    procedure_count = serializers.IntegerField(
        source='procedures.count', 
        read_only=True
    )
    savings = serializers.DecimalField(
        source='savings_amount',
        max_digits=10,
        decimal_places=2,
        read_only=True
    )
    
    class Meta:
        model = ProcedurePackage
        fields = [
            'id', 'name', 'code', 'procedure_count', 'total_charge',
            'discounted_charge', 'savings', 'is_active'
        ]


class ProcedurePackageDetailSerializer(serializers.ModelSerializer):
    """Detailed procedure package serializer"""
    
    procedures = ProcedureMasterListSerializer(many=True, read_only=True)
    discount_percent = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        read_only=True
    )
    savings_amount = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        read_only=True
    )
    
    class Meta:
        model = ProcedurePackage
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at']


class ProcedurePackageCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating procedure packages"""

    class Meta:
        model = ProcedurePackage
        fields = [
            'name', 'code', 'procedures', 'total_charge',
            'discounted_charge', 'is_active'
        ]

    def validate(self, data):
        """Validate package data"""
        total = data.get('total_charge', Decimal('0'))
        discounted = data.get('discounted_charge', Decimal('0'))

        if discounted > total:
            raise serializers.ValidationError({
                'discounted_charge': 'Discounted charge cannot exceed total charge'
            })

        return data

    def create(self, validated_data):
        """Create procedure package with tenant_id"""
        request = self.context.get('request')

        # Add tenant_id from request context
        if request and hasattr(request, 'tenant_id'):
            validated_data['tenant_id'] = request.tenant_id

        return super().create(validated_data)


# ============================================================================
# PROCEDURE BILL ITEM SERIALIZERS (DEPRECATED)
# ============================================================================

# class ProcedureBillItemSerializer(serializers.ModelSerializer):
#     """Serializer for procedure bill items"""
    
#     procedure_name = serializers.CharField(source='procedure.name', read_only=True)
    
#     class Meta:
#         model = ProcedureBillItem
#         fields = [
#             'id', 'procedure', 'procedure_name', 'particular_name',
#             'note', 'quantity', 'unit_charge', 'amount', 'item_order'
#         ]
#         read_only_fields = ['amount']
    
#     def validate(self, data):
#         """Ensure particular_name is set"""
#         if 'procedure' in data and not data.get('particular_name'):
#             data['particular_name'] = data['procedure'].name
#         return data


# ============================================================================
# OPD BILL ITEM SERIALIZERS (Unified Billing)
# ============================================================================

# This is the old OPDBillItemSerializer, replaced by the one at the top
# class OPDBillItemSerializer(serializers.ModelSerializer):
#     """Serializer for OPD Bill Items with manual price override support."""

#     # Computed field showing if price matches system calculation
#     actual_price = serializers.DecimalField(
#         source='unit_price',
#         max_digits=10,
#         decimal_places=2,
#         read_only=True,
#         help_text="The actual price (same as unit_price, for frontend clarity)"
#     )

#     class Meta:
#         model = OPDBillItem
#         fields = [
#             'id', 'tenant_id', 'visit', 'item_name', 'source',
#             'quantity', 'system_calculated_price', 'unit_price', 'actual_price',
#             'total_price', 'is_price_overridden', 'notes',
#             'origin_content_type', 'origin_object_id',
#             'created_at', 'updated_at'
#         ]
#         read_only_fields = [
#             'tenant_id', 'total_price', 'system_calculated_price',
#             'is_price_overridden', 'created_at', 'updated_at'
#         ]

#     def validate(self, attrs):
#         """Validate bill item data."""
#         # If unit_price is being set manually and differs from system price
#         if 'unit_price' in attrs and 'system_calculated_price' in self.initial_data:
#             system_price = attrs.get('system_calculated_price')
#             unit_price = attrs.get('unit_price')
#             if system_price and unit_price != system_price:
#                 attrs['is_price_overridden'] = True

#         return attrs


# ============================================================================
# PROCEDURE BILL SERIALIZERS (DEPRECATED)
# ============================================================================

# class ProcedureBillListSerializer(serializers.ModelSerializer):
#     """Serializer for listing procedure bills"""
    
#     patient_name = serializers.CharField(source='visit.patient.full_name', read_only=True)
#     doctor_name = serializers.CharField(source='doctor.full_name', read_only=True)
#     visit_number = serializers.CharField(source='visit.visit_number', read_only=True)
#     item_count = serializers.IntegerField(source='items.count', read_only=True)
    
#     class Meta:
#         model = ProcedureBill
#         fields = [
#             'id', 'bill_number', 'visit', 'visit_number', 'patient_name',
#             'doctor', 'doctor_name', 'bill_date', 'bill_type',
#             'item_count', 'total_amount', 'payable_amount',
#             'payment_status'
#         ]
#         read_only_fields = ['bill_number', 'bill_date']


# class ProcedureBillDetailSerializer(serializers.ModelSerializer):
#     """Detailed procedure bill serializer with items"""
    
#     patient_name = serializers.CharField(source='visit.patient.full_name', read_only=True)
#     doctor_name = serializers.CharField(source='doctor.full_name', read_only=True)
#     visit_number = serializers.CharField(source='visit.visit_number', read_only=True)
#     items = ProcedureBillItemSerializer(many=True, read_only=True)

#     class Meta:
#         model = ProcedureBill
#         fields = '__all__'
#         read_only_fields = [
#             'bill_number', 'bill_date', 'total_amount', 'payable_amount',
#             'balance_amount', 'payment_status', 'created_at', 'updated_at'
#         ]


# class ProcedureBillCreateUpdateSerializer(serializers.ModelSerializer):
#     """Serializer for creating/updating procedure bills with items"""
    
#     items = ProcedureBillItemSerializer(many=True)
    
#     class Meta:
#         model = ProcedureBill
#         fields = [
#             'visit', 'doctor', 'bill_type', 'category',
#             'discount_percent', 'payment_mode', 'payment_details',
#             'received_amount', 'items'
#         ]
    
#     @transaction.atomic
#     def create(self, validated_data):
#         """Create procedure bill with items"""
#         items_data = validated_data.pop('items', [])

#         request = self.context.get('request')

#         # Add tenant_id from request context
#         if request and hasattr(request, 'tenant_id'):
#             validated_data['tenant_id'] = request.tenant_id

#         # Add billed_by_id from request context
#         if request and hasattr(request, 'user_id'):
#             validated_data['billed_by_id'] = request.user_id

#         validated_data['total_amount'] = Decimal('0.00')
#         validated_data['payable_amount'] = Decimal('0.00')

#         # Create bill first
#         bill = ProcedureBill.objects.create(**validated_data)

#         # Create items
#         for item_data in items_data:
#             # Add tenant_id to each item
#             item_data['tenant_id'] = validated_data['tenant_id']
#             ProcedureBillItem.objects.create(
#                 procedure_bill=bill,
#                 **item_data
#             )

#         # Now recalculate totals after items are created
#         bill.calculate_totals()
#         bill.save()

#         return bill
    
#     @transaction.atomic
#     def update(self, instance, validated_data):
#         """Update procedure bill and items"""
#         items_data = validated_data.pop('items', None)
        
#         # Update bill fields
#         for attr, value in validated_data.items():
#             setattr(instance, attr, value)
        
#         # Update items if provided
#         if items_data is not None:
#             # Delete existing items
#             instance.items.all().delete()
            
#             # Create new items
#             for item_data in items_data:
#                 ProcedureBillItem.objects.create(
#                     procedure_bill=instance,
#                     **item_data
#                 )
        
#         # Recalculate and save
#         instance.calculate_totals()
#         instance.save()
        
#         return instance


# ============================================================================
# CLINICAL NOTE SERIALIZERS
# ============================================================================

class ClinicalNoteListSerializer(serializers.ModelSerializer):
    """Serializer for listing clinical notes"""
    
    visit_number = serializers.CharField(source='visit.visit_number', read_only=True)
    patient_name = serializers.CharField(source='visit.patient.full_name', read_only=True)
    diagnosis_short = serializers.SerializerMethodField()
    
    class Meta:
        model = ClinicalNote
        fields = [
            'id', 'visit', 'visit_number', 'patient_name', 'note_date',
            'diagnosis_short', 'next_followup_date'
        ]
    
    def get_diagnosis_short(self, obj):
        """Return truncated diagnosis"""
        if obj.diagnosis:
            return obj.diagnosis[:100] + ('...' if len(obj.diagnosis) > 100 else '')
        return None


class ClinicalNoteDetailSerializer(serializers.ModelSerializer):
    """Detailed clinical note serializer"""
    
    visit_number = serializers.CharField(source='visit.visit_number', read_only=True)
    patient_name = serializers.CharField(source='visit.patient.full_name', read_only=True)
    referred_doctor_name = serializers.CharField(source='referred_doctor.full_name', read_only=True)

    class Meta:
        model = ClinicalNote
        fields = '__all__'
        read_only_fields = ['note_date', 'created_at', 'updated_at']


class ClinicalNoteCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating clinical notes"""
    
    class Meta:
        model = ClinicalNote
        fields = [
            'visit', 'ehr_number', 'present_complaints', 'observation',
            'diagnosis', 'investigation', 'treatment_plan',
            'medicines_prescribed', 'doctor_advice',
            'suggested_surgery_name', 'suggested_surgery_reason',
            'referred_doctor', 'next_followup_date'
        ]
    
    def validate_visit(self, value):
        """Validate that visit doesn't already have a clinical note"""
        if self.instance is None:  # Only for creation
            if hasattr(value, 'clinical_note'):
                raise serializers.ValidationError(
                    "This visit already has a clinical note"
                )
        return value
    
    def create(self, validated_data):
        """Create clinical note"""
        request = self.context.get('request')

        # Add tenant_id from request context
        if request and hasattr(request, 'tenant_id'):
            validated_data['tenant_id'] = request.tenant_id

        # Add created_by_id from request context
        if request and hasattr(request, 'user_id'):
            validated_data['created_by_id'] = request.user_id

        return super().create(validated_data)


# ============================================================================
# VISIT FINDING SERIALIZERS
# ============================================================================

class VisitFindingListSerializer(serializers.ModelSerializer):
    """Serializer for listing visit findings"""
    
    visit_number = serializers.CharField(source='visit.visit_number', read_only=True)
    patient_name = serializers.CharField(source='visit.patient.full_name', read_only=True)
    blood_pressure = serializers.CharField(read_only=True)
    bmi_category = serializers.CharField(read_only=True)
    
    class Meta:
        model = VisitFinding
        fields = [
            'id', 'visit', 'visit_number', 'patient_name', 'finding_date',
            'finding_type', 'temperature', 'pulse', 'blood_pressure',
            'weight', 'height', 'bmi', 'bmi_category', 'spo2'
        ]
        read_only_fields = ['bmi', 'finding_date']


class VisitFindingDetailSerializer(serializers.ModelSerializer):
    """Detailed visit finding serializer"""
    
    visit_number = serializers.CharField(source='visit.visit_number', read_only=True)
    patient_name = serializers.CharField(source='visit.patient.full_name', read_only=True)
    blood_pressure = serializers.CharField(read_only=True)
    bmi_category = serializers.CharField(read_only=True)

    class Meta:
        model = VisitFinding
        fields = '__all__'
        read_only_fields = [
            'bmi', 'finding_date', 'created_at', 'updated_at'
        ]


class VisitFindingCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating visit findings"""
    
    class Meta:
        model = VisitFinding
        fields = [
            'visit', 'finding_type', 'temperature', 'pulse',
            'bp_systolic', 'bp_diastolic', 'weight', 'height',
            'spo2', 'respiratory_rate', 'tongue', 'throat',
            'cns', 'rs', 'cvs', 'pa'
        ]
    
    def create(self, validated_data):
        """Create finding"""
        request = self.context.get('request')

        # Add tenant_id from request context
        if request and hasattr(request, 'tenant_id'):
            validated_data['tenant_id'] = request.tenant_id

        # Add recorded_by_id from request context
        if request and hasattr(request, 'user_id'):
            validated_data['recorded_by_id'] = request.user_id

        return super().create(validated_data)


# ============================================================================
# VISIT ATTACHMENT SERIALIZERS
# ============================================================================

class VisitAttachmentListSerializer(serializers.ModelSerializer):
    """Serializer for listing visit attachments"""
    
    visit_number = serializers.CharField(source='visit.visit_number', read_only=True)
    file_size = serializers.SerializerMethodField()
    file_extension = serializers.SerializerMethodField()
    
    class Meta:
        model = VisitAttachment
        fields = [
            'id', 'visit', 'visit_number', 'file_name', 'file_type',
            'file_size', 'file_extension', 'uploaded_at'
        ]
    
    def get_file_size(self, obj):
        """Get file size"""
        return obj.get_file_size()
    
    def get_file_extension(self, obj):
        """Get file extension"""
        return obj.get_file_extension()


class VisitAttachmentDetailSerializer(serializers.ModelSerializer):
    """Detailed visit attachment serializer"""
    
    visit_number = serializers.CharField(source='visit.visit_number', read_only=True)
    file_size = serializers.SerializerMethodField()
    file_extension = serializers.SerializerMethodField()

    class Meta:
        model = VisitAttachment
        fields = '__all__'
        read_only_fields = ['uploaded_at']
    
    def get_file_size(self, obj):
        """Get file size"""
        return obj.get_file_size()
    
    def get_file_extension(self, obj):
        """Get file extension"""
        return obj.get_file_extension()


class VisitAttachmentCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating visit attachments"""
    
    class Meta:
        model = VisitAttachment
        fields = ['visit', 'file', 'file_type', 'description']
    
    def create(self, validated_data):
        """Create attachment"""
        request = self.context.get('request')

        # Add tenant_id from request context
        if request and hasattr(request, 'tenant_id'):
            validated_data['tenant_id'] = request.tenant_id

        # Add uploaded_by_id from request context
        if request and hasattr(request, 'user_id'):
            validated_data['uploaded_by_id'] = request.user_id

        return super().create(validated_data)


# ============================================================================
# STATISTICS SERIALIZERS
# ============================================================================

class OPDBillStatisticsSerializer(serializers.Serializer):
    """Serializer for OPD bill statistics"""

    total_bills = serializers.IntegerField()
    total_revenue = serializers.DecimalField(max_digits=12, decimal_places=2)
    paid_revenue = serializers.DecimalField(max_digits=12, decimal_places=2)
    pending_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_discount = serializers.DecimalField(max_digits=12, decimal_places=2)

    # Payment status breakdown
    bills_paid = serializers.IntegerField()
    bills_partial = serializers.IntegerField()
    bills_unpaid = serializers.IntegerField()

    # OPD type breakdown
    by_opd_type = serializers.ListField()

    # Payment mode breakdown
    by_payment_mode = serializers.ListField()

    # Average bill amount
    average_bill_amount = serializers.DecimalField(max_digits=10, decimal_places=2)


# ============================================================================
# CLINICAL NOTE TEMPLATE GROUP SERIALIZERS
# ============================================================================

class ClinicalNoteTemplateGroupListSerializer(serializers.ModelSerializer):
    """Serializer for listing template groups"""

    template_count = serializers.IntegerField(
        source='templates.count',
        read_only=True
    )

    class Meta:
        model = ClinicalNoteTemplateGroup
        fields = [
            'id', 'name', 'template_count',
            'is_active', 'display_order'
        ]


class ClinicalNoteTemplateGroupDetailSerializer(serializers.ModelSerializer):
    """Detailed template group serializer"""

    template_count = serializers.IntegerField(
        source='templates.count',
        read_only=True
    )

    class Meta:
        model = ClinicalNoteTemplateGroup
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at']


class ClinicalNoteTemplateGroupCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating template groups"""

    class Meta:
        model = ClinicalNoteTemplateGroup
        fields = ['name', 'description', 'is_active', 'display_order']

    def create(self, validated_data):
        """Create template group with tenant_id"""
        request = self.context.get('request')

        # Add tenant_id from request context
        if request and hasattr(request, 'tenant_id'):
            validated_data['tenant_id'] = request.tenant_id

        return super().create(validated_data)


# ============================================================================
# CLINICAL NOTE TEMPLATE FIELD OPTION SERIALIZERS
# ============================================================================

class ClinicalNoteTemplateFieldOptionSerializer(serializers.ModelSerializer):
    """Serializer for template field options"""

    class Meta:
        model = ClinicalNoteTemplateFieldOption
        fields = [
            'id', 'option_value', 'option_label',
            'display_order'
        ]


# ============================================================================
# CLINICAL NOTE TEMPLATE FIELD SERIALIZERS
# ============================================================================

class ClinicalNoteTemplateFieldListSerializer(serializers.ModelSerializer):
    """Serializer for listing template fields"""

    option_count = serializers.IntegerField(
        source='options.count',
        read_only=True
    )

    class Meta:
        model = ClinicalNoteTemplateField
        fields = [
            'id', 'field_label', 'field_name', 'field_type', 'is_required',
            'option_count', 'display_order', 'is_active'
        ]


class ClinicalNoteTemplateFieldDetailSerializer(serializers.ModelSerializer):
    """Detailed template field serializer with options"""

    options = ClinicalNoteTemplateFieldOptionSerializer(many=True, read_only=True)

    class Meta:
        model = ClinicalNoteTemplateField
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at']


class ClinicalNoteTemplateFieldCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating template fields"""

    options = ClinicalNoteTemplateFieldOptionSerializer(many=True, required=False)

    class Meta:
        model = ClinicalNoteTemplateField
        fields = [
            'template', 'field_label', 'field_name', 'field_type', 'is_required',
            'placeholder', 'help_text', 'default_value',
            'min_value', 'max_value', 'min_length', 'max_length',
            'display_order', 'column_width', 'show_condition', 'is_active', 'options'
        ]

    def validate(self, data):
        """Validate field data"""
        field_type = data.get('field_type')
        options = data.get('options', [])

        # Validate that select/multiselect/radio/checkbox fields have options
        if field_type in ['select', 'multiselect', 'radio', 'checkbox']:
            if not options and not self.instance:
                raise serializers.ValidationError({
                    'options': f'{field_type} field type requires at least one option'
                })

        return data

    @transaction.atomic
    def create(self, validated_data):
        """Create template field with options"""
        options_data = validated_data.pop('options', [])

        request = self.context.get('request')

        # Add tenant_id from request context
        if request and hasattr(request, 'tenant_id'):
            validated_data['tenant_id'] = request.tenant_id

        # Create field
        field = ClinicalNoteTemplateField.objects.create(**validated_data)

        # Create options
        for option_data in options_data:
            ClinicalNoteTemplateFieldOption.objects.create(
                field=field,
                tenant_id=validated_data['tenant_id'],
                **option_data
            )

        return field

    @transaction.atomic
    def update(self, instance, validated_data):
        """Update template field and options"""
        options_data = validated_data.pop('options', None)

        # Update field fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # Update options if provided
        if options_data is not None:
            # Delete existing options
            instance.options.all().delete()

            # Create new options
            for option_data in options_data:
                ClinicalNoteTemplateFieldOption.objects.create(
                    field=instance,
                    tenant_id=instance.tenant_id,
                    **option_data
                )

        return instance


# ============================================================================
# CLINICAL NOTE TEMPLATE SERIALIZERS
# ============================================================================

class ClinicalNoteTemplateListSerializer(serializers.ModelSerializer):
    """Serializer for listing templates"""

    group_name = serializers.CharField(source='group.name', read_only=True, allow_null=True)
    field_count = serializers.IntegerField(
        source='fields.count',
        read_only=True
    )

    class Meta:
        model = ClinicalNoteTemplate
        fields = [
            'id', 'name', 'code', 'group', 'group_name',
            'field_count', 'is_active', 'display_order'
        ]


class ClinicalNoteTemplateDetailSerializer(serializers.ModelSerializer):
    """Detailed template serializer with fields"""

    group_name = serializers.CharField(source='group.name', read_only=True, allow_null=True)
    fields = ClinicalNoteTemplateFieldDetailSerializer(many=True, read_only=True)

    class Meta:
        model = ClinicalNoteTemplate
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at']


class ClinicalNoteTemplateCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating templates"""

    fields = ClinicalNoteTemplateFieldCreateUpdateSerializer(many=True, required=False)

    class Meta:
        model = ClinicalNoteTemplate
        fields = [
            'name', 'code', 'group', 'description',
            'is_active', 'display_order', 'fields'
        ]

    def validate_code(self, value):
        """Validate unique code within tenant"""
        request = self.context.get('request')
        if request and hasattr(request, 'tenant_id'):
            queryset = ClinicalNoteTemplate.objects.filter(
                tenant_id=request.tenant_id,
                code=value
            )
            if self.instance:
                queryset = queryset.exclude(id=self.instance.id)
            if queryset.exists():
                raise serializers.ValidationError("Template code already exists")
        return value

    @transaction.atomic
    def create(self, validated_data):
        """Create template with fields"""
        fields_data = validated_data.pop('fields', [])

        request = self.context.get('request')

        # Add tenant_id from request context
        if request and hasattr(request, 'tenant_id'):
            validated_data['tenant_id'] = request.tenant_id

        # Create template
        template = ClinicalNoteTemplate.objects.create(**validated_data)

        # Create fields
        for field_data in fields_data:
            options_data = field_data.pop('options', [])

            field = ClinicalNoteTemplateField.objects.create(
                template=template,
                tenant_id=validated_data['tenant_id'],
                **field_data
            )

            # Create options for this field
            for option_data in options_data:
                ClinicalNoteTemplateFieldOption.objects.create(
                    field=field,
                    tenant_id=validated_data['tenant_id'],
                    **option_data
                )

        return template

    @transaction.atomic
    def update(self, instance, validated_data):
        """Update template and fields"""
        fields_data = validated_data.pop('fields', None)

        # Update template fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # Update fields if provided
        if fields_data is not None:
            # Delete existing fields (cascade will delete options)
            instance.fields.all().delete()

            # Create new fields
            for field_data in fields_data:
                options_data = field_data.pop('options', [])

                field = ClinicalNoteTemplateField.objects.create(
                    template=instance,
                    tenant_id=instance.tenant_id,
                    **field_data
                )

                # Create options for this field
                for option_data in options_data:
                    ClinicalNoteTemplateFieldOption.objects.create(
                        field=field,
                        tenant_id=instance.tenant_id,
                        **option_data
                    )

        return instance


# ============================================================================
# CLINICAL NOTE TEMPLATE FIELD RESPONSE SERIALIZERS
# ============================================================================

class ClinicalNoteTemplateFieldResponseSerializer(serializers.ModelSerializer):
    """Serializer for template field responses"""

    field_label = serializers.CharField(source='field.field_label', read_only=True)
    field_type = serializers.CharField(source='field.field_type', read_only=True)
    display_value = serializers.SerializerMethodField()

    class Meta:
        model = ClinicalNoteTemplateFieldResponse
        fields = [
            'id', 'field', 'field_label', 'field_type',
            'value_text', 'value_number', 'value_boolean',
            'value_date', 'value_datetime', 'value_time', 'value_json',
            'full_canvas_json', 'canvas_thumbnail', 'canvas_version_history',
            'display_value'
        ]

    def get_display_value(self, obj):
        """Get display value for the field"""
        return obj.get_display_value()


class ClinicalNoteTemplateFieldResponseCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating field responses"""

    class Meta:
        model = ClinicalNoteTemplateFieldResponse
        fields = [
            'field', 'value_text', 'value_number',
            'value_boolean', 'value_date', 'value_datetime', 'value_time',
            'value_json', 'full_canvas_json'
        ]


# ============================================================================
# CLINICAL NOTE TEMPLATE RESPONSE SERIALIZERS
# ============================================================================

class ClinicalNoteTemplateResponseListSerializer(serializers.ModelSerializer):
    """Serializer for listing template responses"""

    template_name = serializers.CharField(source='template.name', read_only=True)
    encounter_display = serializers.SerializerMethodField()
    encounter_type = serializers.SerializerMethodField()
    field_response_count = serializers.IntegerField(
        source='field_responses.count',
        read_only=True
    )

    class Meta:
        model = ClinicalNoteTemplateResponse
        fields = [
            'id', 'content_type', 'object_id', 'encounter_type', 'encounter_display',
            'template', 'template_name', 'response_date',
            'field_response_count', 'status',
            'response_sequence', 'is_reviewed', 'original_assigned_doctor_id',
            'doctor_switched_reason', 'canvas_data',
            'filled_by_id', 'reviewed_by_id', 'reviewed_at'
        ]
        read_only_fields = ['response_date', 'response_sequence', 'content_type', 'object_id']

    def get_encounter_display(self, obj):
        """Get display string for the encounter."""
        if obj.encounter:
            if hasattr(obj.encounter, 'visit_number'):
                return f"OPD Visit: {obj.encounter.visit_number}"
            elif hasattr(obj.encounter, 'admission_id'):
                return f"IPD Admission: {obj.encounter.admission_id}"
        return "No Encounter"

    def get_encounter_type(self, obj):
        """Get the type of encounter."""
        if obj.content_type:
            return obj.content_type.model
        return None


class ClinicalNoteTemplateResponseDetailSerializer(serializers.ModelSerializer):
    """Detailed template response serializer with field responses"""

    template_name = serializers.CharField(source='template.name', read_only=True)
    encounter_display = serializers.SerializerMethodField()
    encounter_type = serializers.SerializerMethodField()
    field_responses = ClinicalNoteTemplateFieldResponseSerializer(many=True, read_only=True)
    summary = serializers.SerializerMethodField()

    class Meta:
        model = ClinicalNoteTemplateResponse
        fields = '__all__'
        read_only_fields = [
            'response_date', 'created_at', 'updated_at', 'response_sequence',
            'filled_by_id', 'reviewed_by_id', 'reviewed_at',
            'content_type', 'object_id', 'tenant_id'
        ]

    def get_summary(self, obj):
        """Get generated summary"""
        return obj.generate_summary()

    def get_encounter_display(self, obj):
        """Get display string for the encounter."""
        if obj.encounter:
            if hasattr(obj.encounter, 'visit_number'):
                return f"OPD Visit: {obj.encounter.visit_number}"
            elif hasattr(obj.encounter, 'admission_id'):
                return f"IPD Admission: {obj.encounter.admission_id}"
        return "No Encounter"

    def get_encounter_type(self, obj):
        """Get the type of encounter."""
        if obj.content_type:
            return obj.content_type.model
        return None


class ClinicalNoteTemplateResponseCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating template responses"""

    field_responses = ClinicalNoteTemplateFieldResponseCreateUpdateSerializer(many=True, required=False)

    # Fields for setting encounter via encounter_type and encounter_id
    encounter_type_name = serializers.CharField(write_only=True, required=False)
    encounter_id = serializers.IntegerField(write_only=True, required=False)

    class Meta:
        model = ClinicalNoteTemplateResponse
        fields = [
            'encounter_type_name', 'encounter_id', 'template', 'status', 'field_responses',
            'original_assigned_doctor_id', 'doctor_switched_reason',
            'canvas_data', 'response_sequence'
        ]
        read_only_fields = ['response_sequence']

    def validate(self, data):
        """Validate response data"""
        # If doctor_switched_reason is provided, original_assigned_doctor_id should also be provided
        if data.get('doctor_switched_reason') and not data.get('original_assigned_doctor_id'):
            raise serializers.ValidationError({
                'original_assigned_doctor_id': 'Required when doctor_switched_reason is provided'
            })

        # Validate encounter fields
        if 'encounter_type_name' in data and 'encounter_id' not in data:
            raise serializers.ValidationError({
                'encounter_id': 'Required when encounter_type_name is provided'
            })
        if 'encounter_id' in data and 'encounter_type_name' not in data:
            raise serializers.ValidationError({
                'encounter_type_name': 'Required when encounter_id is provided'
            })

        return data

    @transaction.atomic
    def create(self, validated_data):
        """Create template response with field responses and auto-sequence logic"""
        from django.contrib.contenttypes.models import ContentType

        field_responses_data = validated_data.pop('field_responses', [])
        encounter_type_name = validated_data.pop('encounter_type_name', None)
        encounter_id = validated_data.pop('encounter_id', None)

        request = self.context.get('request')

        # Add tenant_id from request context
        if request and hasattr(request, 'tenant_id'):
            validated_data['tenant_id'] = request.tenant_id

        # Add filled_by_id from request context
        if request and hasattr(request, 'user_id'):
            validated_data['filled_by_id'] = request.user_id

        # Set content_type and object_id from encounter fields
        if encounter_type_name and encounter_id:
            if encounter_type_name.lower() == 'opd':
                content_type = ContentType.objects.get(app_label='opd', model='visit')
            elif encounter_type_name.lower() == 'ipd':
                content_type = ContentType.objects.get(app_label='ipd', model='admission')
            else:
                raise serializers.ValidationError({
                    'encounter_type_name': f'Invalid encounter type: {encounter_type_name}. Must be "opd" or "ipd".'
                })

            validated_data['content_type'] = content_type
            validated_data['object_id'] = encounter_id

        # Auto-calculate response_sequence if not provided
        # This is additional logic at serializer level (model also has it)
        if 'response_sequence' not in validated_data or not validated_data.get('response_sequence'):
            max_seq = ClinicalNoteTemplateResponse.objects.filter(
                content_type=validated_data['content_type'],
                object_id=validated_data['object_id'],
                template=validated_data['template']
            ).aggregate(models.Max('response_sequence'))['response_sequence__max']
            validated_data['response_sequence'] = (max_seq or 0) + 1

        # Create response (model save() will also calculate sequence if needed)
        response = ClinicalNoteTemplateResponse.objects.create(**validated_data)

        # Create field responses
        for field_response_data in field_responses_data:
            ClinicalNoteTemplateFieldResponse.objects.create(
                response=response,
                tenant_id=validated_data['tenant_id'],
                **field_response_data
            )

        return response

    @transaction.atomic
    def update(self, instance, validated_data):
        """Update template response and field responses"""
        field_responses_data = validated_data.pop('field_responses', None)

        # Update response fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # Update field responses if provided
        if field_responses_data is not None:
            # Delete existing field responses
            instance.field_responses.all().delete()

            # Create new field responses
            for field_response_data in field_responses_data:
                # Check if there is any value data before creating
                value_fields = [
                    'value_text', 'value_number', 'value_boolean',
                    'value_date', 'value_datetime', 'value_time', 'value_json', 'full_canvas_json'
                ]
                has_value = any(field in field_response_data and field_response_data[field] is not None for field in value_fields)

                if has_value:
                    ClinicalNoteTemplateFieldResponse.objects.create(
                        response=instance,
                        tenant_id=instance.tenant_id,
                        **field_response_data
                    )

        return instance


# ============================================================================
# CLINICAL NOTE RESPONSE TEMPLATE SERIALIZERS (Copy-Paste Templates)
# ============================================================================

class ClinicalNoteResponseTemplateListSerializer(serializers.ModelSerializer):
    """Serializer for listing copy-paste response templates"""

    class Meta:
        model = ClinicalNoteResponseTemplate
        fields = [
            'id', 'name', 'description', 'usage_count',
            'is_active', 'created_by_id', 'created_at', 'updated_at'
        ]
        read_only_fields = ['usage_count', 'created_at', 'updated_at']


class ClinicalNoteResponseTemplateDetailSerializer(serializers.ModelSerializer):
    """Detailed copy-paste response template serializer"""

    source_response_details = serializers.SerializerMethodField()

    class Meta:
        model = ClinicalNoteResponseTemplate
        fields = '__all__'
        read_only_fields = ['usage_count', 'created_at', 'updated_at', 'created_by_id']

    def get_source_response_details(self, obj):
        """Get details of the source response"""
        if obj.source_response:
            return {
                'id': obj.source_response.id,
                'visit_id': obj.source_response.visit_id,
                'visit_number': obj.source_response.visit.visit_number,
                'template_id': obj.source_response.template_id,
                'template_name': obj.source_response.template.name,
                'response_date': obj.source_response.response_date,
            }
        return None


class ClinicalNoteResponseTemplateCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating copy-paste response templates"""

    class Meta:
        model = ClinicalNoteResponseTemplate
        fields = [
            'name', 'description', 'source_response',
            'template_field_values', 'is_active'
        ]

    def validate_name(self, value):
        """Validate that template name is unique for this user"""
        request = self.context.get('request')
        if request and hasattr(request, 'user_id') and hasattr(request, 'tenant_id'):
            queryset = ClinicalNoteResponseTemplate.objects.filter(
                tenant_id=request.tenant_id,
                created_by_id=request.user_id,
                name=value
            )
            if self.instance:
                queryset = queryset.exclude(id=self.instance.id)
            if queryset.exists():
                raise serializers.ValidationError(
                    "You already have a template with this name"
                )
        return value

    def create(self, validated_data):
        """Create response template with tenant_id and created_by_id"""
        request = self.context.get('request')

        # Add tenant_id from request context
        if request and hasattr(request, 'tenant_id'):
            validated_data['tenant_id'] = request.tenant_id

        # Add created_by_id from request context
        if request and hasattr(request, 'user_id'):
            validated_data['created_by_id'] = request.user_id

        return super().create(validated_data)
