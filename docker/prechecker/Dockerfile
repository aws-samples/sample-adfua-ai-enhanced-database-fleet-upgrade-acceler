# ── Stage 1: base (Python + MySQL Shell) ─────────────────────────────────────
FROM public.ecr.aws/docker/library/python:3.9-slim AS base

# Install MySQL Shell directly from the official MySQL tarball.
# Avoids the MySQL APT repo whose signing key expired 2025-10-22.
RUN apt-get update && apt-get install -y --no-install-recommends \
        wget=1.21.3-1+b2 \
        libaio1t64=0.3.113-4 \
        libncurses6=6.4+20230625-2 \
        libssl3=3.0.14-1~deb12u2 \
        libkeyutils1=1.6.3-2 \
        python3=3.11.2-1+b1 \
    && wget -q https://dev.mysql.com/get/Downloads/MySQL-Shell/mysql-shell-8.0.40-linux-glibc2.28-x86-64bit.tar.gz \
    && tar -xzf mysql-shell-8.0.40-linux-glibc2.28-x86-64bit.tar.gz \
    && mv mysql-shell-8.0.40-linux-glibc2.28-x86-64bit /usr/local/mysql-shell \
    && ln -s /usr/local/mysql-shell/bin/mysqlsh /usr/local/bin/mysqlsh \
    && rm mysql-shell-8.0.40-linux-glibc2.28-x86-64bit.tar.gz \
    && wget -q -O /etc/ssl/certs/rds-global-bundle.pem https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem \
    && apt-get purge -y wget \
    && apt-get autoremove -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Path to the Amazon RDS global CA bundle for TLS certificate verification.
ENV RDS_CA_BUNDLE=/etc/ssl/certs/rds-global-bundle.pem

RUN mysqlsh --version

WORKDIR /app
ENV PYTHONUNBUFFERED=1

# ── Stage 2: app ──────────────────────────────────────────────────────────────
FROM base AS app

COPY code/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY code/ .

RUN mkdir -p logs precheck_report

# Create non-root user and set ownership
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser \
    && chown -R appuser:appuser /app

USER appuser

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import sys; sys.exit(0)" || exit 1

ENTRYPOINT ["python", "MySql_upgrade_prechecker.py"]
