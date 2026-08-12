FROM python:3.12-slim-bookworm

# mariadb-client: grade_process.py (verifier, runs in this same container in
# Harbor's default shared-verifier mode) queries the `mysql` compose service
# directly over the network instead of via host-side `docker compose exec`.
RUN apt-get update && apt-get install -y --no-install-recommends mariadb-client && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    playwright==1.54.0 openai==2.26.0 openpyxl==3.1.5 pydantic==2.9.2 requests==2.32.3 \
    numpy==2.1.3 pydicom==2.4.4 Pillow==11.0.0 && \
    playwright install --with-deps chromium

WORKDIR /solution
