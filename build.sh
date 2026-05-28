#!/usr/bin/env bash
# Build script para Render — corre en cada deploy.
set -o errexit

# Dependencias
pip install -r requirements.txt

# Archivos estáticos (Whitenoise los sirve en prod)
python manage.py collectstatic --noinput

# Migraciones — incluye developers (app del dashboard gerencial) y metrics (legacy IntegraV7)
python manage.py migrate --noinput

# Sincronización idempotente del fixture local (devs, sprints, requirements, tests).
# Si el fixture no existe en el repo, este comando salta silenciosamente sin fallar.
python manage.py seed_from_local

# Comandos opcionales del legacy IntegraV7 — NO bloquean el deploy si fallan.
# Si querés activar el dashboard IntegraV7 en prod, ejecutalos manualmente desde el Render Shell.
python manage.py seed_project 2>/dev/null || echo "seed_project no disponible o ya corrió — continuando."
python manage.py import_metrics /opt/render/project/src/qa-metrics/integrav7 2>/dev/null || echo "Sin métricas locales para importar — continuando."
