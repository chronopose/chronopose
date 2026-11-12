# Образ сервера chronopose. По умолчанию без нейросети (синтетика, слияние, события, API).
# С камерой: docker build --build-arg VISION=1 -t chronopose .
FROM python:3.11-slim
ARG VISION=0
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
COPY requirements.txt requirements-vision.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
 && if [ "$VISION" = "1" ]; then pip install --no-cache-dir -r requirements-vision.txt; fi
COPY src ./src
COPY web ./web
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/api/health')"
CMD ["sh", "-c", "python -m src.app ${APP_ARGS:---synthetic} --port 8000"]
