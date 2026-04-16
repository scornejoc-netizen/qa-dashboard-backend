from django.core.management.base import BaseCommand
from metrics.models import Project


class Command(BaseCommand):
    help = 'Crear proyecto IntegraV7 Interfaz'

    def add_arguments(self, parser):
        parser.add_argument('--name', type=str, default='IntegraV7 Interfaz')
        parser.add_argument('--slug', type=str, default='integrav7interfaz')

    def handle(self, *args, **options):
        project, created = Project.objects.update_or_create(
            slug=options['slug'],
            defaults={
                'name': options['name'],
                'description': 'Angular 20 - SSR - Standalone - Zoneless - Hexagonal Architecture',
                'framework': 'Angular 20',
            }
        )
        action = 'Creado' if created else 'Actualizado'
        self.stdout.write(self.style.SUCCESS(
            f'{action} proyecto: {project.name} (slug: {project.slug})'
        ))
