from rest_framework import serializers


class RecentEncounterRowSerializer(serializers.Serializer):
    encounter_type = serializers.ChoiceField(choices=["opd", "ipd"])
    encounter_id = serializers.IntegerField()
    patient_id = serializers.IntegerField()
    patient_name = serializers.CharField()
    number = serializers.CharField()
    doctor_name = serializers.CharField(allow_blank=True)
    date = serializers.CharField(allow_null=True)
    status = serializers.CharField()
    pending_pharmacy_count = serializers.IntegerField(min_value=0)
    pending_lab_count = serializers.IntegerField(min_value=0)


class RecentEncountersDataSerializer(serializers.Serializer):
    results = RecentEncounterRowSerializer(many=True)
    count = serializers.IntegerField(min_value=0)
    page = serializers.IntegerField(min_value=1)
    page_size = serializers.IntegerField(min_value=1)


class RecentEncountersResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    data = RecentEncountersDataSerializer()
