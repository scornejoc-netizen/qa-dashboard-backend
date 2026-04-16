web: python manage.py migrate --noinput && python manage.py seed_project && gunicorn config.wsgi --bind 0.0.0.0:$PORT
