FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# The rasterio wheel bundles GDAL, but links against the system libexpat.so.1;
# python:3.12-slim does not include it. No other GDAL/PROJ system packages are needed.
RUN apt-get update \
    && apt-get install --yes --no-install-recommends libexpat1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt \
    && useradd --create-home --uid 10001 app
COPY --chown=app:app src ./src
USER app
EXPOSE 8000

# Only the frontend proxy can reach this service; /api is stripped by nginx.
CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--root-path", "/api", "--proxy-headers", "--forwarded-allow-ips", "*"]
