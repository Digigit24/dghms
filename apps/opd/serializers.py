# opd/serializers.py
from rest_framework import serializers
from django.db import transaction
from django.utils import timezone
from decimal import Decimal

from .models import (
    Visit, OPDBill, ProcedureMaster, ProcedurePackage,
    ProcedureBill, ProcedureBillItem, ClinicalNote,
    VisitFinding, VisitAttachment
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
        if request and request.user:
            validated_data['created_by'] = request.user
        
        return super().create(validated_data)


# ============================================================================
# OPD BILL SERIALIZERS
# ============================================================================

class OPDBillListSerializer(serializers.ModelSerializer):
    """Serializer for listing OPD bills"""
    
    patient_name = serializers.CharField(source='visit.patient.full_name', read_only=True)
    doctor_name = serializers.CharField(source='doctor.full_name', read_only=True)
    visit_number = serializers.CharField(source='visit.visit_number', read_only=True)
    
    class Meta:
        model = OPDBill
        fields = [
            'id', 'bill_number', 'visit', 'visit_number', 'patient_name',
            'doctor', 'doctor_name', 'bill_date', 'opd_type', 'charge_type',
            'total_amount', 'payable_amount', 'received_amount',
            'balance_amount', 'payment_status'
        ]
        read_only_fields = ['bill_number', 'bill_date']


class OPDBillDetailSerializer(serializers.ModelSerializer):
    """Detailed OPD bill serializer"""
    
    patient_name = serializers.CharField(source='visit.patient.full_name', read_only=True)
    doctor_name = serializers.CharField(source='doctor.full_name', read_only=True)
    visit_number = serializers.CharField(source='visit.visit_number', read_only=True)

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
            'visit', 'doctor', 'opd_type', 'opd_subtype', 'charge_type',
            'diagnosis', 'remarks', 'total_amount', 'discount_percent',
            'payment_mode', 'payment_details', 'received_amount'
        ]
    
    def validate_visit(self, value):
        """Validate that visit doesn't already have an OPD bill"""
        if self.instance is None:  # Only for creation
            if hasattr(value, 'opd_bill'):
                raise serializers.ValidationError(
                    "This visit already has an OPD bill"
                )
        return value
    
    def validate(self, data):
        """Validate bill data"""
        # Validate received amount doesn't exceed total
        total = data.get('total_amount', Decimal('0'))
        received = data.get('received_amount', Decimal('0'))
        
        if received > total:
            raise serializers.ValidationError({
                'received_amount': 'Received amount cannot exceed total amount'
            })
        
        return data
    
    def create(self, validated_data):
        """Create OPD bill with auto-calculations"""
        request = self.context.get('request')
        if request and request.user:
            validated_data['billed_by'] = request.user
        
        return super().create(validated_data)


# ============================================================================
# PROCEDURE MASTER SERIALIZERS
# ============================================================================

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


# ============================================================================
# PROCEDURE BILL ITEM SERIALIZERS
# ============================================================================

class ProcedureBillItemSerializer(serializers.ModelSerializer):
    """Serializer for procedure bill items"""
    
    procedure_name = serializers.CharField(source='procedure.name', read_only=True)
    
    class Meta:
        model = ProcedureBillItem
        fields = [
            'id', 'procedure', 'procedure_name', 'particular_name',
            'note', 'quantity', 'unit_charge', 'amount', 'item_order'
        ]
        read_only_fields = ['amount']
    
    def validate(self, data):
        """Ensure particular_name is set"""
        if 'procedure' in data and not data.get('particular_name'):
            data['particular_name'] = data['procedure'].name
        return data


# ============================================================================
# PROCEDURE BILL SERIALIZERS
# ============================================================================

class ProcedureBillListSerializer(serializers.ModelSerializer):
    """Serializer for listing procedure bills"""
    
    patient_name = serializers.CharField(source='visit.patient.full_name', read_only=True)
    doctor_name = serializers.CharField(source='doctor.full_name', read_only=True)
    visit_number = serializers.CharField(source='visit.visit_number', read_only=True)
    item_count = serializers.IntegerField(source='items.count', read_only=True)
    
    class Meta:
        model = ProcedureBill
        fields = [
            'id', 'bill_number', 'visit', 'visit_number', 'patient_name',
            'doctor', 'doctor_name', 'bill_date', 'bill_type',
            'item_count', 'total_amount', 'payable_amount',
            'payment_status'
        ]
        read_only_fields = ['bill_number', 'bill_date']


class ProcedureBillDetailSerializer(serializers.ModelSerializer):
    """Detailed procedure bill serializer with items"""
    
    patient_name = serializers.CharField(source='visit.patient.full_name', read_only=True)
    doctor_name = serializers.CharField(source='doctor.full_name', read_only=True)
    visit_number = serializers.CharField(source='visit.visit_number', read_only=True)
    items = ProcedureBillItemSerializer(many=True, read_only=True)

    class Meta:
        model = ProcedureBill
        fields = '__all__'
        read_only_fields = [
            'bill_number', 'bill_date', 'total_amount', 'payable_amount',
            'balance_amount', 'payment_status', 'created_at', 'updated_at'
        ]


class ProcedureBillCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating procedure bills with items"""
    
    items = ProcedureBillItemSerializer(many=True)
    
    class Meta:
        model = ProcedureBill
        fields = [
            'visit', 'doctor', 'bill_type', 'category',
            'discount_percent', 'payment_mode', 'payment_details',
            'received_amount', 'items'
        ]
    
    @transaction.atomic
    def create(self, validated_data):
        """Create procedure bill with items"""
        items_data = validated_data.pop('items', [])
        
        request = self.context.get('request')
        if request and request.user:
            validated_data['billed_by'] = request.user
        
        validated_data['total_amount'] = Decimal('0.00')
        validated_data['payable_amount'] = Decimal('0.00')
        
        # Create bill first
        bill = ProcedureBill.objects.create(**validated_data)
        
        # Create items
        for item_data in items_data:
            ProcedureBillItem.objects.create(
                procedure_bill=bill,
                **item_data
            )
        
        # Now recalculate totals after items are created
        bill.calculate_totals()
        bill.save()
        
        return bill
    
    @transaction.atomic
    def update(self, instance, validated_data):
        """Update procedure bill and items"""
        items_data = validated_data.pop('items', None)
        
        # Update bill fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        # Update items if provided
        if items_data is not None:
            # Delete existing items
            instance.items.all().delete()
            
            # Create new items
            for item_data in items_data:
                ProcedureBillItem.objects.create(
                    procedure_bill=instance,
                    **item_data
                )
        
        # Recalculate and save
        instance.calculate_totals()
        instance.save()
        
        return instance


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
        if request and request.user:
            validated_data['created_by'] = request.user
        
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
        if request and request.user:
            validated_data['recorded_by'] = request.user
        
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
        if request and request.user:
            validated_data['uploaded_by'] = request.user

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