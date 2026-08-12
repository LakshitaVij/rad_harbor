-- mysqldump of the `openemr` database only captures that database's schema
-- and data - MySQL user accounts (openemr/openemr, which the OpenEMR app
-- itself connects as) live in the separate `mysql` system database and are
-- normally created by OpenEMR's own installer using MYSQL_USER/MYSQL_PASS.
-- We bypass that installer (sites/default/sqlconf.php already marks the
-- site as installed, config=1), so that step never runs - confirmed via a
-- real boot: "Access denied for user 'openemr'@'...' (using password: YES)".
-- Recreate the same user/grant explicitly instead.
CREATE USER IF NOT EXISTS 'openemr'@'%' IDENTIFIED BY 'openemr';
GRANT ALL PRIVILEGES ON openemr.* TO 'openemr'@'%';
FLUSH PRIVILEGES;
