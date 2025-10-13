# syntax=docker/dockerfile:1
FROM python:3.11-slim

# --- Sécurité & perfs ---
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100 \
    # Gunicorn par défaut : ajuste si besoin (workers = 2*CPU+1 en général)
    GUNICORN_CMD_ARGS="--workers=3 --threads=2 --timeout=30 --graceful-timeout=30 --bind=0.0.0.0:8000 --access-logfile=-" \
    PORT=8000

WORKDIR /app

# Dépendances système minimales (build puis clean)
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential curl ca-certificates wget \
 && rm -rf /var/lib/apt/lists/*

# Dépendances Python
COPY requirements.txt .
RUN pip install --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt \
 && pip install --no-cache-dir gunicorn

# Code
COPY . .

# Script d'entrée
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Utilisateur non-root
RUN useradd -u 10001 -m appuser \
 && mkdir -p /data \
 && chown -R appuser:appuser /app /data \
 && chmod 755 /data
USER appuser

# Healthcheck (prévois une route /health qui renvoie 200)
HEALTHCHECK --interval=30s --timeout=3s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health').read()"

EXPOSE 8000

# Point d'entrée avec script de vérification des permissions
ENTRYPOINT ["/entrypoint.sh"]

# Lancement via Gunicorn (remplace 'wsgi:app' si ton module diffère)
# Exemple : FLASK_APP==wsgi.py contenant "app"
CMD ["gunicorn", "wsgi:app"]
