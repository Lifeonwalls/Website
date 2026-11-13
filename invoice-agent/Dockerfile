FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright HOME=/home/app

WORKDIR /srv
COPY requirements.txt requirements-pdf.txt ./
RUN pip install -r requirements.txt -r requirements-pdf.txt \
 && playwright install --with-deps chromium \
 && useradd --create-home --uid 1000 app \
 && mkdir -p /srv/data /home/app/.claude && chown -R app:app /srv /home/app

COPY --chown=app:app app ./app
COPY --chown=app:app scripts ./scripts
USER app
EXPOSE 8000
HEALTHCHECK --interval=60s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
CMD ["python", "-m", "app", "serve"]
