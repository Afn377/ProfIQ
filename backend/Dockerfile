FROM python:3.12.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

# Naive: copy everything first, then install.
COPY . .
RUN pip install --no-cache-dir pip==26.0.1 \
    && pip install --no-cache-dir --uploaded-prior-to 2026-03-21T00:00:00Z -r requirements.txt

ENV DJANGO_DEBUG=0
RUN python manage.py collectstatic --noinput

EXPOSE 8080
CMD exec gunicorn recommender.wsgi:application --bind 0.0.0.0:${PORT:-8080} --workers 2 --timeout 120
