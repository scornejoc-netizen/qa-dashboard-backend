from django.db import models


class Project(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    repository_url = models.URLField(blank=True)
    framework = models.CharField(max_length=50, default='Angular')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class MetricSnapshot(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='snapshots')
    timestamp = models.DateTimeField(auto_now_add=True)
    source = models.CharField(max_length=50, choices=[
        ('jest', 'Jest'),
        ('eslint', 'ESLint'),
        ('qa-agent', 'QA Agent'),
        ('ci', 'CI Pipeline'),
        ('manual', 'Manual'),
    ])
    data_source = models.CharField(max_length=20, default='VERIFIED')
    raw_data = models.JSONField(default=dict)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.project.name} - {self.source} - {self.timestamp}"


class CoverageMetric(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='coverage_metrics')
    snapshot = models.ForeignKey(MetricSnapshot, on_delete=models.CASCADE, null=True, blank=True)
    feature = models.CharField(max_length=100)
    statements_pct = models.FloatField(default=0)
    branches_pct = models.FloatField(default=0)
    functions_pct = models.FloatField(default=0)
    lines_pct = models.FloatField(default=0)
    total_lines = models.IntegerField(default=0)
    covered_lines = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.project.name} - {self.feature} - {self.lines_pct}%"


class TestResult(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='test_results')
    snapshot = models.ForeignKey(MetricSnapshot, on_delete=models.CASCADE, null=True, blank=True)
    suite_name = models.CharField(max_length=200)
    feature = models.CharField(max_length=100, blank=True)
    total = models.IntegerField(default=0)
    passed = models.IntegerField(default=0)
    failed = models.IntegerField(default=0)
    skipped = models.IntegerField(default=0)
    duration_ms = models.FloatField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.suite_name} - {self.passed}/{self.total}"


class CIPipelineRun(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='pipeline_runs')
    run_id = models.CharField(max_length=100)
    branch = models.CharField(max_length=100)
    status = models.CharField(max_length=20, choices=[
        ('success', 'Success'),
        ('failure', 'Failure'),
        ('running', 'Running'),
        ('pending', 'Pending'),
    ])
    lint_status = models.CharField(max_length=20, default='pending')
    test_status = models.CharField(max_length=20, default='pending')
    build_status = models.CharField(max_length=20, default='pending')
    duration_seconds = models.IntegerField(default=0)
    commit_sha = models.CharField(max_length=40, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.project.name} - {self.branch} - {self.status}"


class Defect(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='defects')
    title = models.CharField(max_length=300)
    severity = models.CharField(max_length=20, choices=[
        ('critical', 'Critical'),
        ('high', 'High'),
        ('medium', 'Medium'),
        ('low', 'Low'),
    ])
    category = models.CharField(max_length=50)
    status = models.CharField(max_length=20, choices=[
        ('open', 'Open'),
        ('in_progress', 'In Progress'),
        ('resolved', 'Resolved'),
        ('closed', 'Closed'),
    ], default='open')
    file_path = models.CharField(max_length=500, blank=True)
    line_number = models.IntegerField(null=True, blank=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.severity}] {self.title}"


class TechnicalDebt(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='technical_debts')
    snapshot = models.ForeignKey(MetricSnapshot, on_delete=models.CASCADE, null=True, blank=True)
    code_smells = models.IntegerField(default=0)
    complexity_issues = models.IntegerField(default=0)
    duplication_pct = models.FloatField(default=0)
    security_issues = models.IntegerField(default=0)
    maintainability_rating = models.CharField(max_length=1, default='C')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.project.name} - Rating: {self.maintainability_rating}"


class SecurityFinding(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='security_findings')
    title = models.CharField(max_length=300)
    severity = models.CharField(max_length=20, choices=[
        ('critical', 'Critical'),
        ('high', 'High'),
        ('medium', 'Medium'),
        ('low', 'Low'),
        ('info', 'Info'),
    ])
    owasp_category = models.CharField(max_length=10, blank=True)
    file_path = models.CharField(max_length=500, blank=True)
    line_number = models.IntegerField(null=True, blank=True)
    description = models.TextField(blank=True)
    recommendation = models.TextField(blank=True)
    status = models.CharField(max_length=20, default='open')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['severity', '-created_at']

    def __str__(self):
        return f"[{self.owasp_category}] [{self.severity}] {self.title}"


class PerformanceBaseline(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='performance_baselines')
    metric_name = models.CharField(max_length=100)
    target_value = models.FloatField()
    unit = models.CharField(max_length=20, default='ms')
    test_type = models.CharField(max_length=50, choices=[
        ('smoke', 'Smoke'),
        ('load', 'Load'),
        ('stress', 'Stress'),
        ('spike', 'Spike'),
        ('web_vitals', 'Web Vitals'),
    ])
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.metric_name}: {self.target_value}{self.unit}"


class QualityGate(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='quality_gates')
    name = models.CharField(max_length=200)
    metric = models.CharField(max_length=100)
    operator = models.CharField(max_length=5, choices=[
        ('>=', '>='),
        ('<=', '<='),
        ('==', '=='),
        ('<', '<'),
        ('>', '>'),
    ])
    threshold = models.FloatField()
    current_value = models.FloatField(default=0)
    status = models.CharField(max_length=20, choices=[
        ('passed', 'Passed'),
        ('failed', 'Failed'),
        ('warning', 'Warning'),
    ], default='failed')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name}: {self.current_value} {self.operator} {self.threshold} [{self.status}]"
