FROM python:3.12.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

# Install deps first. This layer only rebuilds when requirements.txt changes,
# so a one-line code edit doesnt reinstall torch.
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-postgres.txt ./
# Linux pip defaults to the CUDA build of torch, gigabytes of GPU libraries
# Cloud Run can never use. Take torch from the CPU index first so the
# requirement below is already satisfied. --no-deps and --uploaded-prior-to
# keep every package, torch's own dependencies included, to releases that
# existed on 2026-03-21.
RUN pip install --no-cache-dir pip==26.0.1 \
    && pip install --no-cache-dir --no-deps torch==2.10.0 --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir --uploaded-prior-to 2026-03-21T00:00:00Z -r requirements.txt -r requirements-postgres.txt

# Now the source, which changes on every commit.
COPY . .

ENV DJANGO_DEBUG=0 USE_POSTGRES=1
RUN python manage.py collectstatic --noinput

EXPOSE 8080
CMD ["sh", "-c", "exec gunicorn recommender.wsgi:application --bind 0.0.0.0:${PORT:-8080} --workers 2 --timeout 120"]
