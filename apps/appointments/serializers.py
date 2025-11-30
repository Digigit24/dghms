from rest_framework import serializers
from .models import Appointment, AppointmentType
from apps.patients.serializers import PatientProfileListSerializer
from apps.doctors.serializers import DoctorProfileListSerializer

class AppointmentTypeSerializer(serializers.ModelSerializer):
    """Serializer for AppointmentType"""
    # Make tenant_id optional - it will be auto-populated from request headers
    tenant_id = serializers.UUIDField(required=False)

    class Meta:
        model = AppointmentType
        fields = '__all__'

    def create(self, validated_data):
        """Custom create method - tenant_id is set by TenantViewSetMixin"""
        # Note: tenant_id is automatically set by TenantViewSetMixin.perform_create()
        return super().create(validated_data)

    def update(self, instance, validated_data):
        """Custom update method"""
        validated_data.pop('tenant_id', None)  # Don't allow tenant_id change
        return super().update(instance, validated_data)




class AppointmentListSerializer(serializers.ModelSerializer):
    """List view serializer for appointments"""
    patient = PatientProfileListSerializer(read_only=True)
    doctor = DoctorProfileListSerializer(read_only=True)
    appointment_type = serializers.StringRelatedField()
    
    status_display = serializers.CharField(
        source='get_status_display', 
        read_only=True
    )
    priority_display = serializers.CharField(
        source='get_priority_display', 
        read_only=True
    )
    
    
    class Meta:
        model = Appointment
        fields = [
            'id', 'appointment_id', 'patient', 'doctor', 
            'appointment_type', 'appointment_date', 'appointment_time', 
            'status', 'status_display', 'priority', 'priority_display',
            'consultation_fee', 'is_follow_up',
            'visit', 
           
            'check_in_time', 
            'created_at', 'updated_at'
        ]
        read_only_fields = ['check_in_time']
    

class AppointmentDetailSerializer(serializers.ModelSerializer):
    """Detail view serializer for appointments"""
    patient = PatientProfileListSerializer(read_only=True)
    doctor = DoctorProfileListSerializer(read_only=True)
    appointment_type = AppointmentTypeSerializer(read_only=True)  # Changed from StringRelatedField
    
    status_display = serializers.CharField(
        source='get_status_display', 
        read_only=True
    )
    priority_display = serializers.CharField(
        source='get_priority_display', 
        read_only=True
    )
    
    created_by_name = serializers.SerializerMethodField()
    cancelled_by_name = serializers.SerializerMethodField()
    approved_by_name = serializers.SerializerMethodField()
    visit_number = serializers.CharField(source='visit.visit_number', read_only=True)
    
    def get_created_by_name(self, obj):
        """Get created by name - placeholder since we don't have user model"""
        return f"User {obj.created_by_id}" if obj.created_by_id else None
    
    def get_cancelled_by_name(self, obj):
        """Get cancelled by name - placeholder since we don't have user model"""
        return f"User {obj.cancelled_by_id}" if obj.cancelled_by_id else None
    
    def get_approved_by_name(self, obj):
        """Get approved by name - placeholder since we don't have user model"""
        return f"User {obj.approved_by_id}" if obj.approved_by_id else None
    
    class Meta:
        model = Appointment
        fields = '__all__'  # Changed from 'exclude'
        read_only_fields = [
            'id', 'appointment_id', 
            'created_at', 'updated_at',
            'checked_in_at', 'actual_start_time', 
            'visit', 
            'visit_number', 
            'check_in_time',
            'actual_end_time', 'waiting_time_minutes',
            'cancelled_at', 'approved_at'
        ]


class AppointmentCreateUpdateSerializer(serializers.ModelSerializer):
    """Create/Update serializer for appointments"""
    patient_id = serializers.IntegerField(write_only=True)
    doctor_id = serializers.IntegerField(write_only=True)
    appointment_type_id = serializers.IntegerField(
        write_only=True,
        required=False,
        allow_null=True,
        help_text="Type of appointment (optional)"
    )
    original_appointment_id = serializers.IntegerField(
        write_only=True,
        required=False,
        allow_null=True
    )
    # Make tenant_id optional - it will be auto-populated from request headers
    tenant_id = serializers.UUIDField(required=False)

    class Meta:
        model = Appointment
        exclude = [
            'patient', 'doctor', 'appointment_type',
            'original_appointment',
            'created_by_id', 'cancelled_by_id', 'approved_by_id'
        ]
    
    def validate(self, attrs):
        """Perform additional validation"""
        # Validate patient
        try:
            from apps.patients.models import PatientProfile
            patient = PatientProfile.objects.get(id=attrs['patient_id'])
            attrs['patient'] = patient
        except PatientProfile.DoesNotExist:
            raise serializers.ValidationError({'patient_id': 'Invalid patient ID'})
        
        # Validate doctor
        try:
            from apps.doctors.models import DoctorProfile
            doctor = DoctorProfile.objects.get(id=attrs['doctor_id'])
            attrs['doctor'] = doctor
        except DoctorProfile.DoesNotExist:
            raise serializers.ValidationError({'doctor_id': 'Invalid doctor ID'})
        
        # Validate appointment type (optional)
        appointment_type_id = attrs.get('appointment_type_id')
        if appointment_type_id:
            try:
                appointment_type = AppointmentType.objects.get(id=appointment_type_id)
                attrs['appointment_type'] = appointment_type
            except AppointmentType.DoesNotExist:
                raise serializers.ValidationError({'appointment_type_id': 'Invalid appointment type ID'})
        else:
            attrs['appointment_type'] = None
        
        # Validate original appointment if follow-up
        if attrs.get('is_follow_up'):
            if not attrs.get('original_appointment_id'):
                raise serializers.ValidationError({
                    'original_appointment_id': 'Original appointment ID is required for follow-up'
                })
            try:
                original_appointment = Appointment.objects.get(id=attrs['original_appointment_id'])
                attrs['original_appointment'] = original_appointment
            except Appointment.DoesNotExist:
                raise serializers.ValidationError({
                    'original_appointment_id': 'Invalid original appointment ID'
                })
        
        return attrs
    
    def create(self, validated_data):
        """Custom create method to set creator"""
        request = self.context.get('request')

        # Remove write-only fields
        validated_data.pop('patient_id', None)
        validated_data.pop('doctor_id', None)
        validated_data.pop('appointment_type_id', None)
        validated_data.pop('original_appointment_id', None)

        # Set creator (user_id from JWT)
        if request and hasattr(request, 'user_id'):
            validated_data['created_by_id'] = request.user_id

        # Note: tenant_id is automatically set by TenantViewSetMixin.perform_create()
        return super().create(validated_data)
    
    def update(self, instance, validated_data):
        """Custom update method"""
        # Remove write-only fields and prevent tenant_id change
        validated_data.pop('patient_id', None)
        validated_data.pop('doctor_id', None)
        validated_data.pop('appointment_type_id', None)
        validated_data.pop('original_appointment_id', None)
        validated_data.pop('tenant_id', None)  # Don't allow tenant_id change

        return super().update(instance, validated_data)