<?php

/**
 * X-ray Viewer "open latest" bridge - the dashboard's "Open X-ray" link
 * points here rather than straight at view_form.php, because view_form.php
 * (and our own new.php underneath it) reads pid/encounter from the PHP
 * SESSION, not from GET params - the dashboard isn't tied to any one
 * encounter, so there is no "current encounter" in session yet when the
 * link is clicked. This script finds the patient's most recent encounter
 * that actually has the X-ray Viewer form attached (i.e. has real
 * matching imaging - see seed_xray_viewer_forms.py), sets it as the
 * active encounter the same way clicking an encounter tab would, then
 * redirects into the real form.
 *
 * @package OpenEMR
 */

require_once("../../globals.php");

use OpenEMR\Common\Session\EncounterSessionUtil;
use OpenEMR\Common\Session\SessionWrapperFactory;
use OpenEMR\Core\OEGlobalsBag;

$session = SessionWrapperFactory::getInstance()->getActiveSession();
$pid = $session->get('pid');

if (empty($pid)) {
    http_response_code(400);
    exit;
}

$row = sqlQuery(
    "SELECT f.encounter, f.form_id FROM forms f " .
    "JOIN form_encounter fe ON fe.pid = f.pid AND fe.encounter = f.encounter " .
    "WHERE f.formdir = 'xray_viewer' AND f.pid = ? AND f.deleted = 0 " .
    "ORDER BY fe.date DESC LIMIT 1",
    [$pid]
);

if (empty($row['encounter'])) {
    // No imaging for this patient at all - back to the dashboard rather
    // than a dead end/error page.
    header("Location: " . $rootdir . "/patient_file/summary/demographics.php");
    exit;
}

EncounterSessionUtil::setEncounter((string) $row['encounter']);

header(
    "Location: " . $rootdir . "/patient_file/encounter/view_form.php?id="
    . urlencode((string) $row['form_id']) . "&formname=xray_viewer"
);
