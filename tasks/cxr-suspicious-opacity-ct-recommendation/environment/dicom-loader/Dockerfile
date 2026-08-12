FROM python:3.12-slim

RUN pip install --no-cache-dir requests==2.32.3

COPY dicom-loader/upload_dicom.py /upload_dicom.py
COPY dicom /dicom

CMD ["python", "/upload_dicom.py"]
