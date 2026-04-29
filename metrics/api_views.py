import os
import json
from django.conf import settings
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.db.models import Sum, Q
from django.utils import timezone
from .models import (
    Project, CoverageMetric, TestResult, TechnicalDebt,
    SecurityFinding, QualityGate, PerformanceBaseline, CIPipelineRun,
)
from .serializers import (
    ProjectListSerializer, CoverageMetricSerializer, TestResultSerializer,
    TechnicalDebtSerializer, SecurityFindingSerializer, QualityGateSerializer,
    PerformanceBaselineSerializer, CIPipelineRunSerializer,
)


@api_view(['GET'])
def project_list(request):
    projects = Project.objects.all()
    serializer = ProjectListSerializer(projects, many=True)
    return Response(serializer.data)


# ATC-specific focus data (verified manually by counting files per layer)
# Source: find src/app/features/atencionCliente -path "*/<layer>/*.ts" ! -name "*.spec.ts"
ATC_LAYER_INVENTORY = {
    'useCases': {
        'total': 83, 'tested': 83,
        'label': 'Casos de uso',
        'desc': 'Logica de negocio pura (buscar, crear, cerrar actividades)',
    },
    'facades': {
        'total': 27, 'tested': 27,
        'label': 'Facades',
        'desc': 'Orquestadores que coordinan casos de uso y estados',
    },
    'states': {
        'total': 32, 'tested': 32,
        'label': 'Estados',
        'desc': 'Gestion de estado con signals (Angular 20)',
    },
    'mappers': {
        'total': 44, 'tested': 44,
        'label': 'Mappers',
        'desc': 'Conversion entre DTOs del backend y entidades del frontend',
    },
    'entities': {
        'total': 61, 'tested': 60,
        'label': 'Entidades',
        'desc': 'Clases de dominio del negocio',
    },
    'adapters': {
        'total': 28, 'tested': 28,
        'label': 'Adaptadores',
        'desc': 'Implementacion HTTP de los puertos (consumen la API)',
    },
    'components': {
        'total': 53, 'tested': 52,
        'label': 'Componentes UI',
        'desc': 'Componentes visuales de Angular',
    },
    'pages': {
        'total': 3, 'tested': 3,
        'label': 'Paginas',
        'desc': 'Paginas principales del modulo (home, detail)',
    },
    'services_pres': {
        'total': 1, 'tested': 1,
        'label': 'Servicios de presentacion',
        'desc': 'Servicios transversales del modulo',
    },
    'dtos': {
        'total': 68, 'tested': 68,
        'label': 'DTOs',
        'desc': 'Contratos de datos con el backend (interfaces)',
    },
    'ports': {
        'total': 29, 'tested': 29,
        'label': 'Puertos',
        'desc': 'Interfaces abstractas de la arquitectura hexagonal',
    },
    'services_app': {
        'total': 1, 'tested': 1,
        'label': 'Servicios de aplicacion',
        'desc': 'Servicios SignalR de tiempo real',
    },
    'enums': {
        'total': 2, 'tested': 2,
        'label': 'Enumeraciones',
        'desc': 'Valores constantes del dominio',
    },
}

ATC_FEATURE_KEY = 'atencionCliente'
ATC_COVERAGE_LINES = 46.12
ATC_COVERAGE_STATEMENTS = 46.16
ATC_COVERAGE_BRANCHES = 19.08
ATC_COVERAGE_FUNCTIONS = 35.09
ATC_TOTAL_LINES = 13677
ATC_COVERED_LINES = 6309


@api_view(['GET'])
def project_focus_atc(request, slug):
    """Retorna metricas especificas del modulo atencionCliente (ATC)."""
    try:
        project = Project.objects.get(slug=slug)
    except Project.DoesNotExist:
        return Response({'error': 'Proyecto no encontrado'}, status=404)

    # Build layers with percentages
    layers = []
    total_files = 0
    tested_files = 0
    for key, data in ATC_LAYER_INVENTORY.items():
        total = data['total']
        tested = data['tested']
        pct = round((tested / total * 100), 1) if total > 0 else 0
        total_files += total
        tested_files += tested
        layers.append({
            'key': key,
            'label': data['label'],
            'description': data['desc'],
            'total': total,
            'tested': tested,
            'pct': pct,
            'status': 'complete' if pct >= 90 else 'partial' if pct > 0 else 'pending',
        })

    # Sort: completed first, then partial, then pending
    layers.sort(key=lambda x: (x['status'] != 'complete', x['status'] != 'partial', -x['pct']))

    # Count tests that belong to ATC from TestResult
    atc_test_results = TestResult.objects.filter(project=project, feature=ATC_FEATURE_KEY)
    atc_tests_total = atc_test_results.aggregate(total=Sum('total'))['total'] or 0
    atc_tests_passed = atc_test_results.aggregate(passed=Sum('passed'))['passed'] or 0

    # Count security findings that reference atencionCliente
    atc_security = SecurityFinding.objects.filter(
        project=project, file_path__icontains='atencionCliente'
    )
    atc_security_summary = {
        'total': atc_security.count(),
        'critical': atc_security.filter(severity='critical').count(),
        'high': atc_security.filter(severity='high').count(),
        'medium': atc_security.filter(severity='medium').count(),
        'low': atc_security.filter(severity='low').count(),
    }

    return Response({
        'feature': ATC_FEATURE_KEY,
        'display_name': 'Atencion al Cliente',
        'description': 'Modulo nucleo del producto - la agenda del asesor ATC',
        'inventory': {
            'total_files': total_files,
            'tested_files': tested_files,
            'pct_files_tested': round((tested_files / total_files * 100), 1) if total_files > 0 else 0,
            'untested_files': total_files - tested_files,
        },
        'coverage': {
            'lines_pct': ATC_COVERAGE_LINES,
            'statements_pct': ATC_COVERAGE_STATEMENTS,
            'branches_pct': ATC_COVERAGE_BRANCHES,
            'functions_pct': ATC_COVERAGE_FUNCTIONS,
            'total_lines': ATC_TOTAL_LINES,
            'covered_lines': ATC_COVERED_LINES,
            'source': 'Jest --coverage sobre src/app/features/atencionCliente',
        },
        'tests': {
            'total': atc_tests_total,
            'passed': atc_tests_passed,
            'pass_rate': round((atc_tests_passed / atc_tests_total * 100), 1) if atc_tests_total > 0 else 0,
        },
        'layers': layers,
        'security': atc_security_summary,
        'progress': {
            'before': 7,
            'after': tested_files,
            'delta': tested_files - 7,
        },
    })


@api_view(['GET'])
def project_dashboard(request, slug):
    try:
        project = Project.objects.get(slug=slug)
    except Project.DoesNotExist:
        return Response({'error': 'Proyecto no encontrado'}, status=404)

    # Coverage: global (total_lines > 0) and per-feature
    coverage_global = CoverageMetric.objects.filter(
        project=project, feature='global', total_lines__gt=0
    ).first()

    coverage_by_feature = CoverageMetric.objects.filter(
        project=project
    ).exclude(feature='global').exclude(total_lines=0)

    # Test results: only REAL tests (passed > 0 or failed > 0)
    test_results = TestResult.objects.filter(
        project=project
    ).filter(Q(passed__gt=0) | Q(failed__gt=0))

    total_tests_real = test_results.aggregate(
        total=Sum('total'),
        passed=Sum('passed'),
        failed=Sum('failed'),
        skipped=Sum('skipped'),
    )

    # Technical debt (latest)
    tech_debt = TechnicalDebt.objects.filter(project=project).first()

    # Security findings
    security_findings = SecurityFinding.objects.filter(project=project)
    security_by_severity = {
        'critical': security_findings.filter(severity='critical').count(),
        'high': security_findings.filter(severity='high').count(),
        'medium': security_findings.filter(severity='medium').count(),
        'low': security_findings.filter(severity='low').count(),
    }

    # Quality gates
    quality_gates = QualityGate.objects.filter(project=project)

    # Performance baselines
    perf_baselines = PerformanceBaseline.objects.filter(project=project)

    # Latest pipeline run
    latest_pipeline = CIPipelineRun.objects.filter(project=project).first()

    # Calculate KPIs
    total_real = total_tests_real['total'] or 0
    passed_real = total_tests_real['passed'] or 0
    failed_real = total_tests_real['failed'] or 0
    test_pass_rate = round((passed_real / total_real * 100), 2) if total_real > 0 else 0

    coverage_lines = coverage_global.lines_pct if coverage_global else 0
    coverage_statements = coverage_global.statements_pct if coverage_global else 0
    coverage_branches = coverage_global.branches_pct if coverage_global else 0

    gates_passed = quality_gates.filter(status='passed').count()
    gates_total = quality_gates.count()

    kpis = {
        'total_tests_real': total_real,
        'total_tests_planned': max(1500, total_real),
        'tests_passed': passed_real,
        'tests_failed': failed_real,
        'test_pass_rate': test_pass_rate,
        'coverage_lines': coverage_lines,
        'coverage_statements': coverage_statements,
        'coverage_branches': coverage_branches,
        'security_findings_total': security_findings.count(),
        'security_critical': security_by_severity['critical'],
        'security_high': security_by_severity['high'],
        'code_smells': tech_debt.code_smells if tech_debt else 0,
        'complexity_issues': tech_debt.complexity_issues if tech_debt else 0,
        'duplication_pct': tech_debt.duplication_pct if tech_debt else 0,
        'maintainability_rating': tech_debt.maintainability_rating if tech_debt else 'N/A',
        'quality_gates_passed': gates_passed,
        'quality_gates_total': gates_total,
        'pipeline_status': latest_pipeline.status if latest_pipeline else 'N/A',
    }

    data = {
        'project': ProjectListSerializer(project).data,
        'kpis': kpis,
        'coverage': CoverageMetricSerializer(coverage_by_feature, many=True).data,
        'coverage_global': CoverageMetricSerializer(coverage_global).data if coverage_global else None,
        'test_results': TestResultSerializer(test_results, many=True).data,
        'technical_debt': TechnicalDebtSerializer(tech_debt).data if tech_debt else None,
        'security_findings': SecurityFindingSerializer(security_findings, many=True).data,
        'security_summary': security_by_severity,
        'quality_gates': QualityGateSerializer(quality_gates, many=True).data,
        'performance_baselines': PerformanceBaselineSerializer(perf_baselines, many=True).data,
        'pipeline': CIPipelineRunSerializer(latest_pipeline).data if latest_pipeline else None,
    }

    return Response(data)


def _verify_webhook_token(request):
    """Verify X-QA-Token header matches configured secret."""
    token = request.headers.get('X-QA-Token', '')
    expected = getattr(settings, 'QA_WEBHOOK_TOKEN', os.environ.get('QA_WEBHOOK_TOKEN', ''))
    if not expected:
        return True  # No token configured = open (dev mode)
    return token == expected


@api_view(['POST'])
def webhook_github(request):
    """
    Webhook que recibe metricas del CI (GitHub Actions).
    Payload esperado:
    {
      "project_slug": "integrav7interfaz",
      "commit": "abc123",
      "branch": "dev",
      "coverage": { "statements": 14.14, "branches": 1.54, "functions": 2.56, "lines": 12.52,
                     "total_lines": 27461, "covered_lines": 3439 },
      "test_results": { "suites": 34, "tests": 251, "passed": 251, "failed": 0, "duration_ms": 57000 },
      "test_suites": [ { "name": "...", "feature": "...", "tests": N, "passed": N, "failed": 0 } ],
      "pipeline": { "status": "success", "lint": "success", "test": "success", "build": "success",
                     "duration_seconds": 120 }
    }
    """
    if not _verify_webhook_token(request):
        return Response({'error': 'Token invalido'}, status=403)

    data = request.data
    slug = data.get('project_slug', 'integrav7interfaz')

    try:
        project = Project.objects.get(slug=slug)
    except Project.DoesNotExist:
        project = Project.objects.create(
            name=slug.replace('-', ' ').title(),
            slug=slug,
            description='Creado automaticamente via webhook',
        )

    imported = {}

    # --- Coverage ---
    cov = data.get('coverage', {})
    if cov:
        # Update or create global coverage
        CoverageMetric.objects.filter(project=project, feature='global').delete()
        CoverageMetric.objects.create(
            project=project,
            feature='global',
            statements_pct=cov.get('statements', 0),
            branches_pct=cov.get('branches', 0),
            functions_pct=cov.get('functions', 0),
            lines_pct=cov.get('lines', 0),
            total_lines=cov.get('total_lines', 1),
            covered_lines=cov.get('covered_lines', 0),
        )
        imported['coverage'] = True

    # --- Test results ---
    test_data = data.get('test_results', {})
    suites = data.get('test_suites', [])
    if suites:
        # Replace all test results
        TestResult.objects.filter(project=project).delete()
        for suite in suites:
            TestResult.objects.create(
                project=project,
                suite_name=suite.get('name', 'Unknown'),
                feature=suite.get('feature', ''),
                total=suite.get('tests', 0),
                passed=suite.get('passed', 0),
                failed=suite.get('failed', 0),
                skipped=suite.get('skipped', 0),
                duration_ms=suite.get('duration_ms', 0),
            )
        imported['test_suites'] = len(suites)
    elif test_data:
        # Simple summary without suite details
        TestResult.objects.filter(project=project).delete()
        TestResult.objects.create(
            project=project,
            suite_name='CI Run',
            feature='all',
            total=test_data.get('tests', 0),
            passed=test_data.get('passed', 0),
            failed=test_data.get('failed', 0),
            duration_ms=test_data.get('duration_ms', 0),
        )
        imported['test_results'] = True

    # --- Pipeline run ---
    pipeline = data.get('pipeline', {})
    if pipeline:
        CIPipelineRun.objects.create(
            project=project,
            run_id=data.get('run_id', f"gh-{data.get('commit', 'unknown')[:7]}"),
            branch=data.get('branch', 'dev'),
            status=pipeline.get('status', 'success'),
            lint_status=pipeline.get('lint', 'success'),
            test_status=pipeline.get('test', 'success'),
            build_status=pipeline.get('build', 'pending'),
            duration_seconds=pipeline.get('duration_seconds', 0),
            commit_sha=data.get('commit', ''),
        )
        imported['pipeline'] = True

    # --- Update quality gates based on fresh coverage ---
    if cov:
        _update_quality_gates(project, cov, test_data)
        imported['quality_gates'] = True

    # Touch project timestamp
    project.save()

    return Response({
        'status': 'ok',
        'project': slug,
        'imported': imported,
        'timestamp': timezone.now().isoformat(),
    })


def _update_quality_gates(project, coverage, test_data):
    """Update quality gate current values with fresh data."""
    gate_updates = {
        'Line Coverage': coverage.get('lines', 0),
        'Cobertura De Lineas': coverage.get('lines', 0),
        'Statement Coverage': coverage.get('statements', 0),
        'Cobertura De Sentencias': coverage.get('statements', 0),
        'Branch Coverage': coverage.get('branches', 0),
        'Cobertura De Ramas': coverage.get('branches', 0),
        'Test Pass Rate': 100 if test_data.get('failed', 0) == 0 else
            round(test_data.get('passed', 0) / max(test_data.get('tests', 1), 1) * 100, 2),
        'Tasa De Exito De Pruebas': 100 if test_data.get('failed', 0) == 0 else
            round(test_data.get('passed', 0) / max(test_data.get('tests', 1), 1) * 100, 2),
    }

    for gate in QualityGate.objects.filter(project=project):
        new_val = gate_updates.get(gate.name)
        if new_val is not None:
            gate.current_value = new_val
            gate.status = 'passed' if _eval_gate(new_val, gate.operator, gate.threshold) else 'failed'
            gate.save()


def _eval_gate(current, operator, threshold):
    ops = {'>=': lambda a, b: a >= b, '<=': lambda a, b: a <= b,
           '==': lambda a, b: a == b, '>': lambda a, b: a > b, '<': lambda a, b: a < b}
    return ops.get(operator, lambda a, b: False)(current, threshold)


@api_view(['POST'])
def project_refresh(request, slug):
    """
    Re-importar metricas desde directorio local o desde JSON upload.
    POST body: { "path": "/ruta/a/qa-metrics/integrav7" }
    O: multipart con archivos JSON
    """
    try:
        project = Project.objects.get(slug=slug)
    except Project.DoesNotExist:
        return Response({'error': 'Proyecto no encontrado'}, status=404)

    metrics_path = request.data.get('path', '')

    # Default path for local dev
    if not metrics_path:
        default_paths = [
            os.path.join(settings.BASE_DIR, '..', 'qa-metrics', 'integrav7'),
            'D:/PROYECTOS/qa-metrics/integrav7',
        ]
        for p in default_paths:
            if os.path.isdir(p):
                metrics_path = p
                break

    if not metrics_path or not os.path.isdir(metrics_path):
        return Response({
            'error': 'No se encontro directorio de metricas. Enviar {"path": "/ruta/..."}'
        }, status=400)

    # Use management command logic
    from django.core.management import call_command
    from io import StringIO
    out = StringIO()
    call_command('import_metrics', metrics_path, '--project', slug, stdout=out)

    project.save()  # touch updated_at

    return Response({
        'status': 'ok',
        'project': slug,
        'output': out.getvalue(),
        'timestamp': timezone.now().isoformat(),
    })
