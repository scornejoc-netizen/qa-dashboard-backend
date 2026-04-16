import json
import os
from django.core.management.base import BaseCommand
from metrics.models import (
    Project, CoverageMetric, TestResult, TechnicalDebt,
    SecurityFinding, QualityGate, PerformanceBaseline, CIPipelineRun,
)


class Command(BaseCommand):
    help = 'Importar metricas QA desde directorio de JSONs'

    def add_arguments(self, parser):
        parser.add_argument('path', type=str, help='Directorio con JSONs de metricas')
        parser.add_argument('--project', type=str, default='integrav7interfaz',
                            help='Slug del proyecto')

    def handle(self, *args, **options):
        directory = options['path']
        project_slug = options['project']

        if not os.path.isdir(directory):
            self.stderr.write(self.style.ERROR(f'Directorio no encontrado: {directory}'))
            return

        try:
            project = Project.objects.get(slug=project_slug)
        except Project.DoesNotExist:
            self.stderr.write(self.style.ERROR(
                f'Proyecto no encontrado: {project_slug}. Ejecuta seed_project primero.'
            ))
            return

        self.stdout.write(f'Importando metricas para {project.name} desde {directory}...')

        # Clear existing data
        project.coverage_metrics.all().delete()
        project.test_results.all().delete()
        project.technical_debts.all().delete()
        project.security_findings.all().delete()
        project.quality_gates.all().delete()
        project.performance_baselines.all().delete()
        project.pipeline_runs.all().delete()

        # Import each file
        self._import_jest(project, directory)
        self._import_strategy(project, directory)
        self._import_static(project, directory)
        self._import_security(project, directory)
        self._import_performance(project, directory)
        self._import_ci(project, directory)

        self.stdout.write(self.style.SUCCESS('Importacion completada.'))
        self._print_summary(project)

    def _load_json(self, directory, filename):
        filepath = os.path.join(directory, filename)
        if not os.path.exists(filepath):
            self.stdout.write(self.style.WARNING(f'  No encontrado: {filename}'))
            return None
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _import_jest(self, project, directory):
        data = self._load_json(directory, 'jest-results.json')
        if not data:
            return

        # Global coverage from coverage_real
        cov = data.get('coverage_real', data.get('coverage', {}))
        if cov:
            # Handle nested format: {"lines": {"pct": 11.68, "covered": 2983, "total": 25533}}
            def _get_pct(obj, key):
                val = obj.get(key, 0)
                if isinstance(val, dict):
                    return val.get('pct', 0)
                return val

            def _get_val(obj, key, field):
                val = obj.get(key, 0)
                if isinstance(val, dict):
                    return val.get(field, 0)
                return 0

            lines_pct = _get_pct(cov, 'lines') or _get_pct(cov, 'lines_pct')
            stmts_pct = _get_pct(cov, 'statements') or _get_pct(cov, 'statements_pct')
            branches_pct = _get_pct(cov, 'branches') or _get_pct(cov, 'branches_pct')
            functions_pct = _get_pct(cov, 'functions') or _get_pct(cov, 'functions_pct')
            total_lines = _get_val(cov, 'lines', 'total') or cov.get('total_lines', 1)
            covered_lines = _get_val(cov, 'lines', 'covered') or cov.get('covered_lines', 0)

            CoverageMetric.objects.create(
                project=project,
                feature='global',
                statements_pct=stmts_pct,
                branches_pct=branches_pct,
                functions_pct=functions_pct,
                lines_pct=lines_pct,
                total_lines=total_lines,
                covered_lines=covered_lines,
            )
            self.stdout.write(f'  Coverage global: {lines_pct}% lines')

        # Per-feature coverage (handle both dict and list formats)
        feat_count = 0
        artifacts = data.get('artifacts_by_feature', data.get('coverage_by_feature', {}))
        if isinstance(artifacts, dict):
            # Dict format: {"auth": {"total": 4, "tested": 4, "coverage_pct": 100}}
            for feature_name, feat_data in artifacts.items():
                CoverageMetric.objects.create(
                    project=project,
                    feature=feature_name,
                    lines_pct=feat_data.get('coverage_pct', 0),
                    statements_pct=feat_data.get('coverage_pct', 0),
                    total_lines=feat_data.get('total', 0),
                    covered_lines=feat_data.get('tested', feat_data.get('with_spec', 0)),
                )
                feat_count += 1
        elif isinstance(artifacts, list):
            for feat in artifacts:
                feature_name = feat.get('feature', feat.get('name', 'unknown'))
                CoverageMetric.objects.create(
                    project=project,
                    feature=feature_name,
                    lines_pct=feat.get('coverage_pct', feat.get('lines_pct', 0)),
                    statements_pct=feat.get('statements_pct', feat.get('coverage_pct', 0)),
                    total_lines=feat.get('total_artifacts', feat.get('total', 0)),
                    covered_lines=feat.get('with_spec', feat.get('tested', 0)),
                )
                feat_count += 1
        self.stdout.write(f'  Coverage por feature: {feat_count} features')

        # Test suites (REAL only)
        suite_count = 0
        total_tests = 0
        for suite in data.get('test_suites_detail', data.get('test_suites', [])):
            total = suite.get('tests', suite.get('total', 0))
            passed = suite.get('passed', total)
            if total > 0:
                TestResult.objects.create(
                    project=project,
                    suite_name=suite.get('name', suite.get('suite_name', 'Unknown')),
                    feature=suite.get('feature', ''),
                    total=total,
                    passed=passed,
                    failed=suite.get('failed', 0),
                    skipped=suite.get('skipped', 0),
                    duration_ms=suite.get('duration_ms', suite.get('time_ms', 0)),
                )
                suite_count += 1
                total_tests += total
        self.stdout.write(f'  Test suites: {suite_count}, Tests totales: {total_tests}')

    def _import_strategy(self, project, directory):
        data = self._load_json(directory, 'test-strategy.json')
        if not data:
            return

        gate_count = 0
        gates_raw = data.get('quality_gates', {})
        # Normalize: handle both dict and list formats
        if isinstance(gates_raw, dict):
            gates_list = []
            for gate_name, gate_data in gates_raw.items():
                if isinstance(gate_data, dict):
                    gates_list.append({
                        'name': gate_name.replace('_', ' ').title(),
                        'current_value': gate_data.get('current', 0),
                        'threshold': gate_data.get('threshold', 0),
                        'operator': '>=',
                    })
            gates_raw = gates_list

        for gate in gates_raw:
            name = gate.get('name', gate.get('gate', ''))
            current = gate.get('current_value', gate.get('current', 0))
            threshold = gate.get('threshold', gate.get('target', 0))
            operator = gate.get('operator', '>=')

            if isinstance(current, str):
                try:
                    current = float(current.replace('%', ''))
                except ValueError:
                    current = 0
            if isinstance(threshold, str):
                try:
                    threshold = float(threshold.replace('%', ''))
                except ValueError:
                    threshold = 0

            passed = self._evaluate_gate(current, operator, threshold)
            QualityGate.objects.create(
                project=project,
                name=name,
                metric=gate.get('metric', name),
                operator=operator,
                threshold=threshold,
                current_value=current,
                status='passed' if passed else 'failed',
            )
            gate_count += 1
        self.stdout.write(f'  Quality gates: {gate_count}')

    def _import_static(self, project, directory):
        data = self._load_json(directory, 'static-analysis.json')
        if not data:
            return

        summary = data.get('summary', {})
        TechnicalDebt.objects.create(
            project=project,
            code_smells=summary.get('code_smells', summary.get('total_code_smells', 0)),
            complexity_issues=summary.get('complexity_issues', summary.get('total_complexity_issues', 0)),
            duplication_pct=summary.get('duplication_pct', summary.get('duplication_percentage', 0)),
            security_issues=summary.get('security_issues', summary.get('total_security_issues', 0)),
            maintainability_rating=summary.get('maintainability_rating', 'C'),
        )
        self.stdout.write(
            f'  Deuda tecnica: {summary.get("code_smells", 0)} code smells, '
            f'rating {summary.get("maintainability_rating", "C")}'
        )

    def _import_security(self, project, directory):
        data = self._load_json(directory, 'security-report.json')
        if not data:
            return

        count = 0
        for finding in data.get('findings', data.get('vulnerabilities', [])):
            owasp = finding.get('owasp_category',
                             finding.get('category',
                             finding.get('owasp', '')))
            # Extract OWASP code from strings like "OWASP-A07 - ..."
            if owasp and '-' in owasp:
                owasp = owasp.split(' - ')[0].replace('OWASP-', '')
            SecurityFinding.objects.create(
                project=project,
                title=finding.get('title', finding.get('name', '')),
                severity=finding.get('severity', 'medium').lower(),
                owasp_category=owasp[:10] if owasp else '',
                file_path=finding.get('file_path', finding.get('file', '')),
                line_number=finding.get('line_number', finding.get('line', None)),
                description=finding.get('description', '')[:500],
                recommendation=finding.get('recommendation', finding.get('fix', ''))[:500],
                status=finding.get('status', 'open'),
            )
            count += 1
        self.stdout.write(f'  Hallazgos de seguridad: {count}')

    def _import_performance(self, project, directory):
        data = self._load_json(directory, 'performance-baseline.json')
        if not data:
            return

        count = 0

        # Import web_vitals_targets (dict format)
        web_vitals = data.get('web_vitals_targets', {})
        if isinstance(web_vitals, dict):
            for metric_name, metric_data in web_vitals.items():
                if isinstance(metric_data, dict):
                    good_val = metric_data.get('good', '0')
                    # Parse value from strings like "<2500ms"
                    import re
                    nums = re.findall(r'[\d.]+', str(good_val))
                    target = float(nums[0]) if nums else 0
                    unit = 'ms' if 'ms' in str(good_val) else ''
                    PerformanceBaseline.objects.create(
                        project=project,
                        metric_name=metric_name,
                        target_value=target,
                        unit=unit or 'ms',
                        test_type='web_vitals',
                    )
                    count += 1

        # Import scripts summary
        for script in data.get('scripts', []):
            PerformanceBaseline.objects.create(
                project=project,
                metric_name=script.get('name', 'unknown'),
                target_value=script.get('vus', script.get('vus_peak', script.get('vus_max', 0))),
                unit='VUs',
                test_type=script.get('type', 'load'),
            )
            count += 1

        # Also handle flat baselines array format
        for baseline in data.get('baselines', data.get('thresholds', [])):
            if isinstance(baseline, dict):
                PerformanceBaseline.objects.create(
                    project=project,
                    metric_name=baseline.get('metric_name', baseline.get('metric', baseline.get('name', ''))),
                    target_value=baseline.get('target_value', baseline.get('target', baseline.get('threshold', 0))),
                    unit=baseline.get('unit', 'ms'),
                    test_type=baseline.get('test_type', baseline.get('type', 'web_vitals')),
                )
                count += 1

        self.stdout.write(f'  Performance baselines: {count}')

    def _import_ci(self, project, directory):
        data = self._load_json(directory, 'ci-pipeline-status.json')
        if not data:
            return

        pipeline = data.get('pipeline', data)
        summary = data.get('summary', {})
        status = pipeline.get('status', summary.get('status', 'success')).lower()
        if status == 'configured':
            status = 'success'
        CIPipelineRun.objects.create(
            project=project,
            run_id=pipeline.get('run_id', 'local-1'),
            branch=pipeline.get('branch', 'dev'),
            status=status,
            lint_status=pipeline.get('lint_status', 'success'),
            test_status=pipeline.get('test_status', 'success'),
            build_status=pipeline.get('build_status', 'success'),
            duration_seconds=pipeline.get('duration_seconds', pipeline.get('duration', 0)),
            commit_sha=pipeline.get('commit_sha', pipeline.get('commit', '')),
        )
        self.stdout.write('  Pipeline CI importado')

    def _print_summary(self, project):
        self.stdout.write('\n--- RESUMEN ---')
        self.stdout.write(f'Coverage: {CoverageMetric.objects.filter(project=project).count()} registros')
        self.stdout.write(f'Test Results: {TestResult.objects.filter(project=project).count()} suites')
        self.stdout.write(f'Technical Debt: {TechnicalDebt.objects.filter(project=project).count()} registros')
        self.stdout.write(f'Security Findings: {SecurityFinding.objects.filter(project=project).count()} hallazgos')
        self.stdout.write(f'Quality Gates: {QualityGate.objects.filter(project=project).count()} gates')
        self.stdout.write(f'Performance Baselines: {PerformanceBaseline.objects.filter(project=project).count()} baselines')
        self.stdout.write(f'Pipeline Runs: {CIPipelineRun.objects.filter(project=project).count()} runs')

    @staticmethod
    def _evaluate_gate(current, operator, threshold):
        if operator == '>=':
            return current >= threshold
        elif operator == '<=':
            return current <= threshold
        elif operator == '==':
            return current == threshold
        elif operator == '>':
            return current > threshold
        elif operator == '<':
            return current < threshold
        return False
