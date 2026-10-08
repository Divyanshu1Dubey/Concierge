web: python backend/manage.py migrate --noinput && python backend/manage.py seed_raleigh && gunicorn --chdir backend config.wsgi:application --bind 0.0.0.0:$PORT
