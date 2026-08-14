FROM openemr/openemr:8.3.0

RUN apk add --no-cache patch

WORKDIR /var/www/localhost/htdocs/openemr

COPY xray_viewer_form.patch xray-viewer-open-label.patch xray_dashboard_link.patch ./
RUN patch -p1 < xray_viewer_form.patch \
    && patch -p1 < xray-viewer-open-label.patch \
    && patch -p1 < xray_dashboard_link.patch \
    && rm xray_viewer_form.patch xray-viewer-open-label.patch xray_dashboard_link.patch

COPY sqlconf.php sites/default/sqlconf.php
RUN chown apache:apache sites/default/sqlconf.php && chmod 400 sites/default/sqlconf.php

COPY action_selection/ interface/forms/action_selection/
RUN chown -R apache:apache interface/forms/action_selection/

# xray_viewer_form.patch adds interface/forms/xray_viewer/public/index.php,
# which serves this SPA - it reads its manifest from a `dist/` directory
# relative to ITS OWN location (public/dist/, not xray_viewer/dist/ - found
# the hard way, via a live 500 on a real run). Pre-built dist/ copied in
# directly (matches xray-viewer-frontend/'s own real build output) rather
# than adding a node/npm build stage for one static bundle.
COPY xray_viewer_dist/ interface/forms/xray_viewer/public/dist/
RUN chown -R apache:apache interface/forms/xray_viewer/public/dist/
