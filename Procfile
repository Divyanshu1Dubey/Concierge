web: python backend/manage.py migrate --noinput && gunicorn --chdir backend config.wsgi:application --bind 0.0.0.0:$PORT
