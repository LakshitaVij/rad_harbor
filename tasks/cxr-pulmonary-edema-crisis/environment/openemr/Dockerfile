FROM openemr/openemr:flex@sha256:5a9f1ce09a313206f675cb397fea58f5f4780ed4c1256deb395b2e4395061122

# The "flex" tag ships NO PHP application source at all by design (confirmed
# empty at build time) - it's meant to be paired with a bind-mounted host
# source checkout at container start (as the original dev compose does).
# For a portable, self-contained task, bake the actual source in instead:
# this is the same local checkout the seeded DB (mysql-init/) was created
# against, already including the xray_viewer form module and
# oe-module-xray-dashboard-link (both untracked custom additions on top of
# upstream OpenEMR) and the one tracked-file label patch, already applied in
# this working tree - no separate patch step needed.
#
# EASY_DEV_MODE_NEW's entrypoint rsyncs FROM /openemr INTO the live serving
# directory (/var/www/localhost/htdocs/openemr) at container start - that's
# the actual mechanism the original dev compose's dual bind-mount
# (`/openemr:ro` + `/var/www/.../openemr:rw`) provided. The rsync SOURCE
# needs to be baked in here; the entrypoint populates the live directory
# itself at startup (confirmed via a real boot: without /openemr, it fails
# with "rsync: link_stat /openemr failed: No such file or directory").
#
# openemr-full/{vendor,public/assets,public/themes} are the REAL,
# already-built output pulled from the live working container (`docker
# cp`), not freshly installed here - confirmed the hard way that letting the
# entrypoint build these itself inside our task's empty named volumes
# breaks: npm install's postinstall step populates public/assets/* (raw
# vendor packages like bootstrap-rtl), and webpack's SASS build then reads
# FROM those exact paths to compile the theme CSS - two ordering-dependent
# steps sharing one empty volume that don't reliably complete together on a
# clean boot (confirmed via a real run: 24 webpack errors, "Can't find
# stylesheet to import" for paths npm install should have populated first).
# Using proven-working output sidesteps that fragility entirely. node_modules
# itself isn't shipped (~600MB, needed only to rebuild these, not to run
# them) - FORCE_NO_BUILD_MODE=yes in the compose env skips the entrypoint's
# rebuild-detection entirely, so its absence is never even checked for.
COPY openemr-full/ /openemr

# Same "separate named volume needs content baked at the exact live mount
# path, not just at /openemr" requirement as sites/default/sqlconf.php below
# - vendor/public/assets/public/themes are each their own named volume in
# this task's compose file, so they need to be placed here too, not only at
# the /openemr rsync source.
COPY openemr-full/vendor /var/www/localhost/htdocs/openemr/vendor
COPY openemr-full/public/assets /var/www/localhost/htdocs/openemr/public/assets
COPY openemr-full/public/themes /var/www/localhost/htdocs/openemr/public/themes

# The entrypoint's install-skip check reads $config straight out of
# sites/default/sqlconf.php at the LIVE serving path (not /openemr) via
# `php -r "require sqlconf.php; echo $config;"` - and sites/ is its own
# separate named volume (sitesvolume), which starts empty and only inherits
# content baked into the IMAGE at that exact mount path (not whatever the
# entrypoint's own rsync later copies in). The checked-in sqlconf.php has
# $config=0 (a pre-install template - never mutated back to the host
# checkout after the live system's own install flipped it to 1 at runtime),
# so without this, the entrypoint always re-runs its installer and collides
# with our already-seeded database (confirmed via a real boot: "Can't
# create database 'openemr'; database exists"). These two files are pulled
# directly from the live, already-installed container's own runtime state.
COPY openemr-sites-default/sqlconf.php /var/www/localhost/htdocs/openemr/sites/default/sqlconf.php
COPY openemr-sites-default/config.php /var/www/localhost/htdocs/openemr/sites/default/config.php

# openemr.sh unconditionally rsyncs /couchdb/data -> /couchdb/original at
# startup (EASY_DEV_MODE_NEW's devtools-snapshot support) regardless of
# whether couchdb is actually wired up - confirmed via a real boot: this is
# not gated behind any couchdb-enabled check, and a missing source dir
# aborts the whole entrypoint (rsync exit code 23 under `set -e`). We don't
# run a couchdb service (not needed by the agent or grading), so give it an
# empty directory to satisfy the rsync trivially.
RUN mkdir -p /couchdb/data
