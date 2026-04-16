#!/usr/bin/env bash
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --noinput
python manage.py migrate --noinput
python manage.py seed_project
python manage.py import_metrics /opt/render/project/src/qa-metrics/integrav7 || echo "No local metrics to import"
