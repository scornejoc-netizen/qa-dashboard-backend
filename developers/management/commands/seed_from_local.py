"""
Sincroniza la DB con el fixture `developers/fixtures/local_data.json` de forma idempotente.

Comportamiento:
- Crea entidades que no existen (matcheando por clave natural).
- Actualiza entidades existentes con los datos del fixture.
- NO borra entidades de la DB que no estén en el fixture (es aditivo, no destructivo).
- Re-correrlo N veces siempre converge al estado del fixture.

Claves naturales:
- Developer: full_name
- Sprint: name
- Requirement: code
- TestExecution: (requirement, test_type)

Uso:
    python manage.py seed_from_local
    python manage.py seed_from_local --fixture ruta/a/otro.json
    python manage.py seed_from_local --dry-run
"""
import json
from pathlib import Path

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from developers.models import Developer, Sprint, Requirement, TestExecution


DEFAULT_FIXTURE = Path(apps.get_app_config('developers').path) / 'fixtures' / 'local_data.json'


class Command(BaseCommand):
    help = 'Sincroniza la DB con el fixture local_data.json (idempotente).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--fixture', type=str, default=str(DEFAULT_FIXTURE),
            help='Ruta al JSON. Default: developers/fixtures/local_data.json',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Lee y reporta qué pasaria, pero no guarda nada.',
        )

    def handle(self, *args, **options):
        path = Path(options['fixture'])
        dry_run = options['dry_run']

        if not path.exists():
            # No es un error fatal — si el fixture no existe, el seed simplemente no hace nada.
            # Esto permite que el build.sh corra este comando sin romper si el fixture no se commiteó.
            self.stdout.write(self.style.WARNING(
                f"Fixture no encontrado: {path}. Saltando seed (no es error)."
            ))
            return

        try:
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise CommandError(f"JSON invalido en {path}: {e}")

        self.stdout.write(self.style.NOTICE(f"\nFixture: {path}"))
        self.stdout.write(
            f"Contiene: {len(data.get('developers', []))} devs, "
            f"{len(data.get('sprints', []))} sprints, "
            f"{len(data.get('requirements', []))} reqs.\n"
        )

        stats = {
            'devs_created': 0, 'devs_updated': 0,
            'sprints_created': 0, 'sprints_updated': 0,
            'reqs_created': 0, 'reqs_updated': 0,
            'tests_created': 0, 'tests_updated': 0,
        }

        ctx = transaction.atomic() if not dry_run else _NoopContext()
        with ctx:
            # 1) Developers
            self.stdout.write("--- Developers ---")
            for d in data.get('developers', []):
                self._sync_developer(d, dry_run, stats)

            # 2) Sprints
            if data.get('sprints'):
                self.stdout.write("\n--- Sprints ---")
                for s in data['sprints']:
                    self._sync_sprint(s, dry_run, stats)

            # 3) Requirements (+ test_executions inline)
            self.stdout.write("\n--- Requirements ---")
            for r in data.get('requirements', []):
                self._sync_requirement(r, dry_run, stats)

            if dry_run:
                self.stdout.write(self.style.WARNING("\n[DRY-RUN] Nada se guardo.\n"))

        self._print_summary(stats, dry_run)

    # ---------- Sync helpers ----------

    def _sync_developer(self, d, dry_run, stats):
        full_name = d.get('full_name')
        if not full_name:
            return
        defaults = {
            'level': d.get('level', 'mid'),
            'email': d.get('email', '') or '',
            'github_username': d.get('github_username', '') or '',
            'active': d.get('active', True),
            'joined_at': d.get('joined_at'),
        }
        if dry_run:
            exists = Developer.objects.filter(full_name=full_name).exists()
            stats['devs_updated' if exists else 'devs_created'] += 1
            self.stdout.write(f"  [DRY] {'update' if exists else 'create'}: {full_name}")
            return
        obj, created = Developer.objects.update_or_create(full_name=full_name, defaults=defaults)
        stats['devs_created' if created else 'devs_updated'] += 1
        self.stdout.write(
            self.style.SUCCESS(f"  [+] dev creado: {full_name}") if created
            else f"  [~] dev actualizado: {full_name}"
        )

    def _sync_sprint(self, s, dry_run, stats):
        name = s.get('name')
        if not name:
            return
        defaults = {
            'start_date': s.get('start_date'),
            'end_date': s.get('end_date'),
            'notes': s.get('notes', '') or '',
        }
        if dry_run:
            exists = Sprint.objects.filter(name=name).exists()
            stats['sprints_updated' if exists else 'sprints_created'] += 1
            return
        obj, created = Sprint.objects.update_or_create(name=name, defaults=defaults)
        stats['sprints_created' if created else 'sprints_updated'] += 1

    def _sync_requirement(self, r, dry_run, stats):
        code = r.get('code')
        if not code:
            return

        defaults = {
            'title': r.get('title', ''),
            'description': r.get('description', '') or '',
            'type': r.get('type', 'feature'),
            'status': r.get('status', 'todo'),
            'space': r.get('space', '') or '',
            'created_at': r.get('created_at'),
            'planned_start_date': r.get('planned_start_date'),
            'planned_end_date': r.get('planned_end_date'),
            'started_at': r.get('started_at'),
            'delivered_at': r.get('delivered_at'),
            'closed_at': r.get('closed_at'),
            'qa_bounces': r.get('qa_bounces', 0),
            'production_bugs': r.get('production_bugs', 0),
            'is_documented': r.get('is_documented', False),
            'jira_url': r.get('jira_url', '') or '',
            'notes': r.get('notes', '') or '',
        }

        # Sprint por nombre, si existe
        sprint_name = r.get('sprint')
        if sprint_name:
            defaults['sprint'] = Sprint.objects.filter(name=sprint_name).first()

        if dry_run:
            exists = Requirement.objects.filter(code=code).exists()
            stats['reqs_updated' if exists else 'reqs_created'] += 1
            stats['tests_created'] += len(r.get('test_executions', []))
            return

        req, created = Requirement.objects.update_or_create(code=code, defaults=defaults)
        stats['reqs_created' if created else 'reqs_updated'] += 1

        # M2M developers — set() es idempotente: ajusta a la lista exacta.
        dev_names = r.get('developers') or []
        devs = list(Developer.objects.filter(full_name__in=dev_names))
        req.developers.set(devs)

        # Test executions
        for t in r.get('test_executions', []) or []:
            self._sync_test_execution(req, t, stats)

        self.stdout.write(
            self.style.SUCCESS(f"  [+] req creado: {code} ({len(devs)} dev(s))") if created
            else f"  [~] req actualizado: {code} ({len(devs)} dev(s))"
        )

    def _sync_test_execution(self, req, t, stats):
        test_type = t.get('test_type')
        if not test_type:
            return
        defaults = {
            'total': t.get('total', 0),
            'passed': t.get('passed', 0),
            'executed_at': t.get('executed_at'),
            'notes': t.get('notes', '') or '',
        }
        # executed_at es required en el modelo — si viene None, usar created_at del req como fallback
        if not defaults['executed_at']:
            defaults['executed_at'] = req.created_at

        obj, created = TestExecution.objects.update_or_create(
            requirement=req, test_type=test_type, defaults=defaults,
        )
        stats['tests_created' if created else 'tests_updated'] += 1

    def _print_summary(self, stats, dry_run):
        prefix = "[DRY-RUN] " if dry_run else ""
        self.stdout.write(self.style.NOTICE(f"\n{prefix}--- Resumen ---"))
        self.stdout.write(f"  Devs:     created={stats['devs_created']}, updated={stats['devs_updated']}")
        self.stdout.write(f"  Sprints:  created={stats['sprints_created']}, updated={stats['sprints_updated']}")
        self.stdout.write(f"  Reqs:     created={stats['reqs_created']}, updated={stats['reqs_updated']}")
        self.stdout.write(f"  Tests:    created={stats['tests_created']}, updated={stats['tests_updated']}")
        self.stdout.write(self.style.NOTICE("----------------\n"))


class _NoopContext:
    def __enter__(self): return self
    def __exit__(self, *args): return False
