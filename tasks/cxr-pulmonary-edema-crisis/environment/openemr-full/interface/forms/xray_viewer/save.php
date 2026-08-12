<?php

/**
 * X-ray Viewer form save.php
 *
 * Not part of the normal flow - new.php creates the forms/form_xray_viewer
 * rows itself on first load, since there's no user-submitted data to wait
 * for. Kept only because OpenEMR's generic forms machinery expects every
 * form directory to have a save.php it can safely POST to.
 *
 * @package OpenEMR
 */

require_once(__DIR__ . "/../../globals.php");

use OpenEMR\Common\Csrf\CsrfUtils;
use OpenEMR\Common\Session\SessionWrapperFactory;
use OpenEMR\Core\OEGlobalsBag;

$srcdir = OEGlobalsBag::getInstance()->getSrcDir();
require_once("$srcdir/api.inc.php");
require_once("$srcdir/forms.inc.php");

$session = SessionWrapperFactory::getInstance()->getActiveSession();
CsrfUtils::checkCsrfInput(INPUT_POST, dieOnFail: true);

$pid = $session->get('pid');
$encounter = $session->get('encounter');
$userauthorized = $session->get('userauthorized') ?? 0;

$formId = (int) (sqlQuery(
    "SELECT form_id FROM `forms` WHERE formdir = 'xray_viewer' AND pid = ? AND encounter = ? AND deleted = 0 LIMIT 1",
    [$pid, $encounter]
)['form_id'] ?? 0);

if (!$formId) {
    $newRow = sqlInsert(
        "INSERT INTO form_xray_viewer (date, pid, encounter, user, groupname, authorized, activity) " .
        "VALUES (NOW(), ?, ?, ?, ?, ?, 1)",
        [$pid, $encounter, $session->get('authUser'), $session->get('authProvider'), $userauthorized]
    );
    addForm($encounter, "X-ray Viewer", $newRow, "xray_viewer", $pid, $userauthorized);
}

formHeader("Redirecting....");
formJump();
formFooter();
