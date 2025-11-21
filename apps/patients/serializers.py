from rest_framework import serializers
from django.db import transaction
from .models import PatientProfile, PatientVitals, PatientAllergy


class PatientVitalsSerializer(serializers.ModelSerializer):
    """Patient vitals serializer"""
    blood_pressure = serializers.ReadOnlyField()

    class Meta:
        model = PatientVitals
        fields = '__all__'
        read_only_fields = ['id', 'patient', 'recorded_by_user_id', 'recorded_at']


class PatientVitalsCreateUpdateSerializer(serializers.ModelSerializer):
    """Create/Update serializer for patient vitals"""

    class Meta:
        model = PatientVitals
        exclude = ['patient', 'recorded_by_user_id']
    
    def validate(self, attrs):
        """Validate vital signs"""
        # Temperature validation (35-43°C)
        if attrs.get('temperature'):
            temp = float(attrs['temperature'])
            if temp < 35 or temp > 43:
                raise serializers.ValidationError({
                    'temperature': 'Temperature must be between 35°C and 43°C'
                })
        
        # Blood pressure validation
        systolic = attrs.get('blood_pressure_systolic')
        diastolic = attrs.get('blood_pressure_diastolic')
        
        if systolic and diastolic:
            if systolic <= diastolic:
                raise serializers.ValidationError({
                    'blood_pressure_systolic': 'Systolic must be greater than diastolic'
                })
            if systolic < 70 or systolic > 250:
                raise serializers.ValidationError({
                    'blood_pressure_systolic': 'Systolic must be between 70 and 250 mmHg'
                })
            if diastolic < 40 or diastolic > 150:
                raise serializers.ValidationError({
                    'blood_pressure_diastolic': 'Diastolic must be between 40 and 150 mmHg'
                })
        
        # Heart rate validation (30-220 BPM)
        if attrs.get('heart_rate'):
            hr = attrs['heart_rate']
            if hr < 30 or hr > 220:
                raise serializers.ValidationError({
                    'heart_rate': 'Heart rate must be between 30 and 220 BPM'
                })
        
        # Oxygen saturation validation (70-100%)
        if attrs.get('oxygen_saturation'):
            spo2 = float(attrs['oxygen_saturation'])
            if spo2 < 70 or spo2 > 100:
                raise serializers.ValidationError({
                    'oxygen_saturation': 'Oxygen saturation must be between 70% and 100%'
                })
        
        return attrs


class PatientAllergySerializer(serializers.ModelSerializer):
    """Patient allergy serializer"""
    allergy_type_display = serializers.CharField(
        source='get_allergy_type_display',
        read_only=True
    )
    severity_display = serializers.CharField(
        source='get_severity_display',
        read_only=True
    )

    class Meta:
        model = PatientAllergy
        fields = '__all__'
        read_only_fields = ['id', 'patient', 'recorded_by_user_id', 'created_at', 'updated_at']


class PatientAllergyCreateUpdateSerializer(serializers.ModelSerializer):
    """Create/Update serializer for patient allergies"""

    class Meta:
        model = PatientAllergy
        exclude = ['patient', 'recorded_by_user_id']


class PatientProfileListSerializer(serializers.ModelSerializer):
    """List view serializer for patients - minimal fields"""
    full_name = serializers.ReadOnlyField()
    age = serializers.ReadOnlyField()
    is_insurance_valid = serializers.ReadOnlyField()
    
    class Meta:
        model = PatientProfile
        fields = [
            'id', 'patient_id', 'full_name', 'age', 'gender',
            'mobile_primary', 'email', 'blood_group',
            'city', 'status', 'registration_date',
            'last_visit_date', 'total_visits',
            'is_insurance_valid'
        ]


class PatientProfileDetailSerializer(serializers.ModelSerializer):
    """Detail view serializer for patients - all fields"""
    full_name = serializers.ReadOnlyField()
    full_address = serializers.ReadOnlyField()
    age = serializers.ReadOnlyField()
    bmi = serializers.ReadOnlyField()
    is_insurance_valid = serializers.ReadOnlyField()
    vitals = PatientVitalsSerializer(many=True, read_only=True)
    allergies = PatientAllergySerializer(many=True, read_only=True)

    class Meta:
        model = PatientProfile
        fields = '__all__'


class PatientProfileCreateUpdateSerializer(serializers.ModelSerializer):
    """Create/Update serializer for patients"""
    user_id = serializers.UUIDField(write_only=True, required=False, allow_null=True)
    # Make tenant_id optional - it will be auto-populated
    tenant_id = serializers.UUIDField(required=False)

    class Meta:
        model = PatientProfile
        exclude = ['patient_id', 'age', 'bmi', 'created_by_user_id']

    def validate_user_id(self, value):
        """Validate user_id format (UUID from SuperAdmin)"""
        if value is None:
            return value

        # Check if creating new profile and user_id already has a patient profile
        if self.instance is None:
            existing = PatientProfile.objects.filter(user_id=value).exists()
            if existing:
                raise serializers.ValidationError(
                    'User already has a patient profile'
                )

        return value

    def validate_date_of_birth(self, value):
        """Ensure date of birth is in the past"""
        import datetime
        if value > datetime.date.today():
            raise serializers.ValidationError(
                'Date of birth cannot be in the future'
            )

        # Calculate age
        age = datetime.date.today().year - value.year
        if age > 150:
            raise serializers.ValidationError(
                'Invalid date of birth - age would be over 150 years'
            )

        return value

    def validate_insurance_expiry_date(self, value):
        """Ensure insurance expiry date is in the future"""
        import datetime
        if value and value < datetime.date.today():
            raise serializers.ValidationError(
                'Insurance expiry date must be in the future'
            )
        return value

    def validate(self, attrs):
        """Cross-field validation"""
        # Auto-populate tenant_id from request if not provided
        request = self.context.get('request')
        if request and hasattr(request, 'tenant_id'):
            if 'tenant_id' not in attrs or attrs['tenant_id'] is None:
                attrs['tenant_id'] = request.tenant_id

        # Validate that tenant_id is now present
        if 'tenant_id' not in attrs or attrs['tenant_id'] is None:
            raise serializers.ValidationError({
                'tenant_id': 'Tenant ID is required. Please ensure you are authenticated.'
            })

        # If insurance provider is given, policy number is required
        if attrs.get('insurance_provider') and not attrs.get('insurance_policy_number'):
            raise serializers.ValidationError({
                'insurance_policy_number': 'Policy number is required when insurance provider is specified'
            })

        # Height and weight validation
        height = attrs.get('height')
        weight = attrs.get('weight')

        if height and (height < 30 or height > 300):
            raise serializers.ValidationError({
                'height': 'Height must be between 30 and 300 cm'
            })

        if weight and (weight < 1 or weight > 500):
            raise serializers.ValidationError({
                'weight': 'Weight must be between 1 and 500 kg'
            })

        return attrs

    def create(self, validated_data):
        """Create patient profile"""
        # Get current user ID from context
        request = self.context.get('request')
        created_by_user_id = None
        if request and hasattr(request, 'user_id'):
            created_by_user_id = request.user_id

        patient = PatientProfile.objects.create(
            created_by_user_id=created_by_user_id,
            **validated_data
        )

        return patient

    def update(self, instance, validated_data):
        """Update patient profile"""
        validated_data.pop('user_id', None)  # Don't allow user change
        validated_data.pop('tenant_id', None)  # Don't allow tenant_id change

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        return instance


class PatientStatisticsSerializer(serializers.Serializer):
    """Serializer for patient statistics"""
    total_patients = serializers.IntegerField()
    active_patients = serializers.IntegerField()
    inactive_patients = serializers.IntegerField()
    deceased_patients = serializers.IntegerField()
    patients_with_insurance = serializers.IntegerField()
    average_age = serializers.FloatField()
    total_visits = serializers.IntegerField()
    gender_distribution = serializers.DictField()
    blood_group_distribution = serializers.DictField()


# =============================================================================
# NEW: PATIENT REGISTRATION SERIALIZER
# =============================================================================

class PatientRegistrationSerializer(serializers.Serializer):
    """
    Serializer for patient registration.
    NOTE: User creation is handled by SuperAdmin, not here.
    - If user_id provided: Links patient to existing SuperAdmin user
    - If user_id is None: Creates walk-in patient profile only
    """
    # User ID from SuperAdmin (optional for walk-ins)
    user_id = serializers.UUIDField(required=False, allow_null=True)
    
    # Patient Profile fields (REQUIRED)
    first_name = serializers.CharField(max_length=100, required=True)
    last_name = serializers.CharField(max_length=100, required=True)
    middle_name = serializers.CharField(max_length=100, required=False, allow_blank=True)
    date_of_birth = serializers.DateField(required=True)
    gender = serializers.ChoiceField(
        choices=[('male', 'Male'), ('female', 'Female'), ('other', 'Other')],
        required=True
    )
    
    # Contact (REQUIRED)
    mobile_primary = serializers.CharField(max_length=15, required=True)
    mobile_secondary = serializers.CharField(max_length=15, required=False, allow_blank=True)
    
    # Address (REQUIRED)
    address_line1 = serializers.CharField(max_length=200, required=True)
    address_line2 = serializers.CharField(max_length=200, required=False, allow_blank=True)
    city = serializers.CharField(max_length=100, required=True)
    state = serializers.CharField(max_length=100, required=True)
    country = serializers.CharField(max_length=100, default='India')
    pincode = serializers.CharField(max_length=10, required=True)
    
    # Medical Info (OPTIONAL)
    blood_group = serializers.ChoiceField(
        choices=['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-'],
        required=False,
        allow_blank=True,
        allow_null=True
    )
    height = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, allow_null=True)
    weight = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, allow_null=True)
    
    # Social Info (OPTIONAL)
    marital_status = serializers.ChoiceField(
        choices=[('single', 'Single'), ('married', 'Married'), ('divorced', 'Divorced'), ('widowed', 'Widowed')],
        default='single',
        required=False
    )
    occupation = serializers.CharField(max_length=100, required=False, allow_blank=True)
    
    # Emergency Contact (REQUIRED)
    emergency_contact_name = serializers.CharField(max_length=100, required=True)
    emergency_contact_phone = serializers.CharField(max_length=15, required=True)
    emergency_contact_relation = serializers.CharField(max_length=50, required=True)
    
    # Insurance (OPTIONAL)
    insurance_provider = serializers.CharField(max_length=200, required=False, allow_blank=True)
    insurance_policy_number = serializers.CharField(max_length=100, required=False, allow_blank=True)
    insurance_expiry_date = serializers.DateField(required=False, allow_null=True)
    
    def validate_user_id(self, value):
        """Validate user_id (UUID from SuperAdmin)"""
        if value:
            # Check if user_id already has a patient profile
            if PatientProfile.objects.filter(user_id=value).exists():
                raise serializers.ValidationError('User already has a patient profile')
        return value
    
    def validate_mobile_primary(self, value):
        """Validate mobile number format"""
        import re
        pattern = r'^\+?1?\d{9,15}$'
        if not re.match(pattern, value):
            raise serializers.ValidationError(
                'Phone number must be in format: +999999999. Up to 15 digits allowed.'
            )
        return value
    
    def validate_date_of_birth(self, value):
        """Ensure date of birth is in the past"""
        import datetime
        if value > datetime.date.today():
            raise serializers.ValidationError('Date of birth cannot be in the future')
        
        # Calculate age
        age = datetime.date.today().year - value.year
        if age > 150:
            raise serializers.ValidationError('Invalid date of birth - age would be over 150 years')
        
        return value
    
    def validate(self, attrs):
        """Cross-field validation"""
        # Auto-populate tenant_id from request if not provided
        request = self.context.get('request')
        if request and hasattr(request, 'tenant_id'):
            if 'tenant_id' not in attrs or attrs.get('tenant_id') is None:
                attrs['tenant_id'] = request.tenant_id

        # Validate that tenant_id is now present
        if 'tenant_id' not in attrs or attrs['tenant_id'] is None:
            raise serializers.ValidationError({
                'tenant_id': 'Tenant ID is required. Please ensure you are authenticated.'
            })

        # Height and weight validation
        height = attrs.get('height')
        weight = attrs.get('weight')

        if height and (height < 30 or height > 300):
            raise serializers.ValidationError({
                'height': 'Height must be between 30 and 300 cm'
            })

        if weight and (weight < 1 or weight > 500):
            raise serializers.ValidationError({
                'weight': 'Weight must be between 1 and 500 kg'
            })

        # Insurance validation
        if attrs.get('insurance_provider') and not attrs.get('insurance_policy_number'):
            raise serializers.ValidationError({
                'insurance_policy_number': 'Policy number is required when insurance provider is specified'
            })

        # Insurance expiry date validation
        insurance_expiry = attrs.get('insurance_expiry_date')
        if insurance_expiry:
            import datetime
            if insurance_expiry < datetime.date.today():
                raise serializers.ValidationError({
                    'insurance_expiry_date': 'Insurance expiry date must be in the future'
                })

        return attrs

    @transaction.atomic
    def create(self, validated_data):
        """Create patient profile (user management is handled by SuperAdmin)"""
        # Get created_by from context
        request = self.context.get('request')
        created_by_user_id = None
        if request and hasattr(request, 'user_id'):
            created_by_user_id = request.user_id

        # Create patient profile
        patient = PatientProfile.objects.create(
            created_by_user_id=created_by_user_id,
            **validated_data
        )

        return patient