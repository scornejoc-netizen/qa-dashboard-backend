from rest_framework import serializers
from .models import (
    Project, MetricSnapshot, CoverageMetric, TestResult,
    CIPipelineRun, Defect, TechnicalDebt, SecurityFinding,
    PerformanceBaseline, QualityGate,
)


class CoverageMetricSerializer(serializers.ModelSerializer):
    class Meta:
        model = CoverageMetric
        fields = ['id', 'feature', 'statements_pct', 'branches_pct',
                  'functions_pct', 'lines_pct', 'total_lines', 'covered_lines']


class TestResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = TestResult
        fields = ['id', 'suite_name', 'feature', 'total', 'passed',
                  'failed', 'skipped', 'duration_ms']


class TechnicalDebtSerializer(serializers.ModelSerializer):
    class Meta:
        model = TechnicalDebt
        fields = ['id', 'code_smells', 'complexity_issues', 'duplication_pct',
                  'security_issues', 'maintainability_rating', 'created_at']


class SecurityFindingSerializer(serializers.ModelSerializer):
    class Meta:
        model = SecurityFinding
        fields = ['id', 'title', 'severity', 'owasp_category', 'file_path',
                  'line_number', 'description', 'recommendation', 'status']


class QualityGateSerializer(serializers.ModelSerializer):
    class Meta:
        model = QualityGate
        fields = ['id', 'name', 'metric', 'operator', 'threshold',
                  'current_value', 'status']


class PerformanceBaselineSerializer(serializers.ModelSerializer):
    class Meta:
        model = PerformanceBaseline
        fields = ['id', 'metric_name', 'target_value', 'unit', 'test_type']


class CIPipelineRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = CIPipelineRun
        fields = ['id', 'run_id', 'branch', 'status', 'lint_status',
                  'test_status', 'build_status', 'duration_seconds', 'commit_sha']


class ProjectListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = ['id', 'name', 'slug', 'description', 'framework', 'updated_at']


class DashboardSerializer(serializers.Serializer):
    project = ProjectListSerializer()
    kpis = serializers.DictField()
    coverage = CoverageMetricSerializer(many=True)
    test_results = TestResultSerializer(many=True)
    technical_debt = TechnicalDebtSerializer()
    security_findings = SecurityFindingSerializer(many=True)
    quality_gates = QualityGateSerializer(many=True)
    performance_baselines = PerformanceBaselineSerializer(many=True)
    pipeline = CIPipelineRunSerializer(allow_null=True)
