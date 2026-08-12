FROM python:3.12-slim-bookworm

# Separate verifier image (environment_mode = "separate"): grading now runs
# in its own container, isolated from the agent's. No mariadb-client here -
# unlike the old shared-verifier setup, this image never makes a live SQL
# connection; grade_process.py reads pre-collected ground truth from
# /logs/artifacts/ground_truth.tsv instead (dumped by a [[verifier.collect]]
# hook that runs inside the `mysql` service itself, after the agent's
# container is stopped - a channel the agent can't write to).
RUN pip install --no-cache-dir \
    openai==2.26.0 openpyxl==3.1.5 pydantic==2.9.2 requests==2.32.3 \
    numpy==2.1.3 pydicom==2.4.4 Pillow==11.0.0

WORKDIR /tests
