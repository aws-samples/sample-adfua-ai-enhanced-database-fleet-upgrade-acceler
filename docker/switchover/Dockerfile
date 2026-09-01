FROM public.ecr.aws/docker/library/python:3.9-slim

WORKDIR /app

# Download the Amazon RDS global CA bundle for TLS certificate verification.
RUN apt-get update && apt-get install -y --no-install-recommends wget ca-certificates \
    && wget -q -O /etc/ssl/certs/rds-global-bundle.pem https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem \
    && apt-get purge -y wget \
    && apt-get autoremove -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*
ENV RDS_CA_BUNDLE=/etc/ssl/certs/rds-global-bundle.pem

COPY code/requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY code/ .

RUN mkdir -p logs

ENV PYTHONUNBUFFERED=1

# Create non-root user and set ownership
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser \
    && chown -R appuser:appuser /app

USER appuser

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import sys; sys.exit(0)" || exit 1

ENTRYPOINT ["python", "main_switchover.py"]
