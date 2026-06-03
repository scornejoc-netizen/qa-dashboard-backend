"""
Crea un superusuario desde variables de entorno si no existe (idempotente).

Pensado para entornos donde no hay Shell interactiva (ej: Render Free):
configurás las env vars en el panel del hosting y el build se encarga.

Variables de entorno leídas:
    DJANGO_SUPERUSER_USERNAME   (obligatoria)
    DJANGO_SUPERUSER_PASSWORD   (obligatoria)
    DJANGO_SUPERUSER_EMAIL      (opcional)

Comportamiento:
- Si faltan las obligatorias → skip silencioso (no rompe el build).
- Si el usuario ya existe → skip silencioso (no toca el password — el dueño
  puede cambiarlo desde el admin sin que el siguiente deploy lo sobreescriba).
- Si no existe → lo crea con esas credenciales.

Recomendación post-creación: borrá las env vars del panel del hosting una vez
te hayas logueado, para que la contraseña no quede en plain text en la consola
del proveedor. Si necesitás resetearla, la cambiás desde el admin de Django.
"""
import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Crea un superusuario desde env vars si no existe (idempotente).'

    def handle(self, *args, **options):
        username = os.environ.get('DJANGO_SUPERUSER_USERNAME')
        password = os.environ.get('DJANGO_SUPERUSER_PASSWORD')
        email = os.environ.get('DJANGO_SUPERUSER_EMAIL', '') or ''

        if not username or not password:
            self.stdout.write(self.style.NOTICE(
                'ensure_superuser: faltan DJANGO_SUPERUSER_USERNAME/PASSWORD — skip.'
            ))
            return

        User = get_user_model()
        if User.objects.filter(username=username).exists():
            self.stdout.write(self.style.NOTICE(
                f"ensure_superuser: el usuario '{username}' ya existe — skip "
                "(no se modifica password)."
            ))
            return

        User.objects.create_superuser(username=username, email=email, password=password)
        self.stdout.write(self.style.SUCCESS(
            f"ensure_superuser: superusuario '{username}' creado correctamente."
        ))
