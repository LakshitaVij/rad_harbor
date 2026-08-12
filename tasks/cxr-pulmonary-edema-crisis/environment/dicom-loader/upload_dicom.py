"""
upload_dicom.py

One-shot: waits for Orthanc to actually answer HTTP requests (its image has
no curl/wget, so no docker-native healthcheck works - poll over HTTP from
here instead), then uploads every real DICOM file bundled under /dicom
(this task's single patient's real history, copied from
dicom_by_visit/<patient_id>/ - same files/mechanism as
load_dicom_into_orthanc.py, scoped to just this task's patient). Exits 0
on success so `main` (which depends on this completing) can start.
"""

import sys
import time
from pathlib import Path

import requests

ORTHANC_URL = "http://orthanc:8042"
DICOM_ROOT = Path("/dicom")
READY_TIMEOUT_SEC = 120


def wait_for_orthanc() -> None:
    deadline = time.time() + READY_TIMEOUT_SEC
    while time.time() < deadline:
        try:
            if requests.get(f"{ORTHANC_URL}/system", timeout=5).ok:
                return
        except requests.RequestException:
            pass
        time.sleep(2)
    sys.exit(f"orthanc did not become ready within {READY_TIMEOUT_SEC}s")


def main() -> None:
    wait_for_orthanc()

    files = sorted(DICOM_ROOT.rglob("*.dcm"))
    print(f"Found {len(files)} DICOM files to upload.")

    ok, failed = 0, 0
    for f in files:
        data = f.read_bytes()
        resp = requests.post(f"{ORTHANC_URL}/instances", data=data, headers={"Content-Type": "application/dicom"})
        if resp.status_code in (200, 201):
            ok += 1
        else:
            failed += 1
            print(f"  FAILED ({resp.status_code}): {f} - {resp.text[:200]}")

    print(f"Done. {ok} uploaded OK, {failed} failed.")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
