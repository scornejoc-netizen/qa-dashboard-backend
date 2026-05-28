"""
Exporta toda la data de la app developers a un JSON estructurado que
puede ser commiteado al repo y aplicado en producción con `seed_from_local`.

Uso:
    python manage.py export_local_data
    python manage.py export_local_data --output otra_ruta.json

Flujo recomendado para sincronizar con producción:
    1. Modificas / agregas datos en tu admin local.
    2. python manage.py export_local_data
    3. git add developers/fixtures/local_data.json
    4. git commit -m "data: actualizar fixture de devs y requerimientos"
    5. git push
    6. Render redeploya y corre seed_from_local automáticamente.
"""
import json
from pathlib import Path

from django.apps import apps
from django.core.management.base import BaseCommand

from developers.models import Developer, Sprint, Requirement


DEFAULT_OUTPUT = Path(apps.get_app_config('developers').path) / 'fixtures' / 'local_data.json'


def _date_str(d):
    return d.isoformat() if d else None


class Command(BaseCommand):
    help = 'Exporta la data de developers a un JSON para sincronizar con producción.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--output', type=str, default=str(DEFAULT_OUTPUT),
            help='Ruta del JSON de salida. Default: developers/fixtures/local_data.json',
        )

    def handle(self, *args, **options):
        path = Path(options['output'])
        path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            'developers': [
                {
                    'full_name': d.full_name,
                    'level': d.level,
                    'email': d.email,
                    'github_username': d.github_username,
                    'active': d.active,
                    'joined_at': _date_str(d.joined_at),
                }
                for d in Developer.objects.all().order_by('full_name')
            ],
            'sprints': [
                {
                    'name': s.name,
                    'start_date': _date_str(s.start_date),
                    'end_date': _date_str(s.end_date),
                    'notes': s.notes,
                }
                for s in Sprint.objects.all().order_by('start_date')
            ],
            'requirements': [
                {
                    'code': r.code,
                    'title': r.title,
                    'description': r.description,
                    'type': r.type,
                    'status': r.status,
                    'space': r.space,
                    'developers': [d.full_name for d in r.developers.all()],
                    'sprint': r.sprint.name if r.sprint else None,
                    'created_at': _date_str(r.created_at),
                    'planned_start_date': _date_str(r.planned_start_date),
                    'planned_end_date': _date_str(r.planned_end_date),
                    'started_at': _date_str(r.started_at),
                    'delivered_at': _date_str(r.delivered_at),
                    'closed_at': _date_str(r.closed_at),
                    'qa_bounces': r.qa_bounces,
                    'production_bugs': r.production_bugs,
                    'is_documented': r.is_documented,
                    'jira_url': r.jira_url,
                    'notes': r.notes,
                    'test_executions': [
                        {
                            'test_type': t.test_type,
                            'total': t.total,
                            'passed': t.passed,
                            'executed_at': _date_str(t.executed_at),
                            'notes': t.notes,
                        }
                        for t in r.test_executions.all().order_by('test_type')
                    ],
                }
                for r in Requirement.objects.all().order_by('code')
            ],
        }

        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        total_tests = sum(len(r['test_executions']) for r in data['requirements'])
        self.stdout.write(self.style.SUCCESS(f"\nExportado a {path}"))
        self.stdout.write(
            f"  {len(data['developers'])} devs · "
            f"{len(data['sprints'])} sprints · "
            f"{len(data['requirements'])} reqs · "
            f"{total_tests} test_executions\n"
        )
