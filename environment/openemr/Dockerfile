FROM openemr/openemr:8.3.0

RUN apk add --no-cache patch

WORKDIR /var/www/localhost/htdocs/openemr

COPY xray_viewer_form.patch xray-viewer-open-label.patch xray_dashboard_link.patch ./
RUN patch -p1 < xray_viewer_form.patch \
    && patch -p1 < xray-viewer-open-label.patch \
    && patch -p1 < xray_dashboard_link.patch \
    && rm xray_viewer_form.patch xray-viewer-open-label.patch xray_dashboard_link.patch
