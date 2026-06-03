from rest_framework import serializers
from .models import Developer, Sprint, Requirement, TestExecution, UserStory


class UserStorySerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    time_deviation_days = serializers.IntegerField(read_only=True)

    class Meta:
        model = UserStory
        fields = [
            'id', 'code', 'title', 'description', 'status', 'status_display',
            'planned_start_date', 'planned_end_date',
            'started_at', 'delivered_at',
            'time_deviation_days', 'notes',
        ]


class TestExecutionSerializer(serializers.ModelSerializer):
    test_type_display = serializers.CharField(source='get_test_type_display', read_only=True)
    failed = serializers.IntegerField(read_only=True)
    pass_pct = serializers.FloatField(read_only=True)

    class Meta:
        model = TestExecution
        fields = [
            'id', 'test_type', 'test_type_display',
            'total', 'passed', 'failed', 'pass_pct',
            'executed_at', 'notes',
        ]


class RequirementListSerializer(serializers.ModelSerializer):
    developers = serializers.SerializerMethodField()
    type_display = serializers.CharField(source='get_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    cycle_time_days = serializers.IntegerField(read_only=True)
    time_deviation_days = serializers.IntegerField(read_only=True)
    weighted_quality = serializers.FloatField(read_only=True)

    class Meta:
        model = Requirement
        fields = [
            'id', 'code', 'title', 'space', 'developers',
            'type', 'type_display', 'status', 'status_display',
            'qa_bounces', 'production_bugs', 'is_documented',
            'cycle_time_days', 'time_deviation_days', 'weighted_quality',
            'created_at', 'planned_start_date', 'planned_end_date',
            'started_at', 'delivered_at',
        ]

    def get_developers(self, obj):
        return [
            {'id': d.id, 'full_name': d.full_name, 'level_display': d.get_level_display()}
            for d in obj.developers.all()
        ]


class RequirementDetailSerializer(RequirementListSerializer):
    test_executions = TestExecutionSerializer(many=True, read_only=True)
    user_stories = UserStorySerializer(many=True, read_only=True)

    class Meta(RequirementListSerializer.Meta):
        fields = RequirementListSerializer.Meta.fields + [
            'description', 'jira_url', 'notes',
            'closed_at',
            'user_stories',
            'test_executions',
        ]


class DeveloperSerializer(serializers.ModelSerializer):
    level_display = serializers.CharField(source='get_level_display', read_only=True)

    class Meta:
        model = Developer
        fields = ['id', 'full_name', 'level', 'level_display', 'email', 'github_username', 'active']
