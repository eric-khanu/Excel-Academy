#!/usr/bin/env bash
# Exit on error
set -o errexit

pip install -r requirements.txt

python manage.py collectstatic --no-input
python manage.py migrate

# Optional: create a superuser automatically
# python manage.py createsuperuser --no-input || true