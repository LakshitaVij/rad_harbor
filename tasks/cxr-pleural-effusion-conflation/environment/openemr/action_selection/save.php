<?php

/**
 * Follow-up Action Selection form save.php
 *
 * Real, server-side write: pid/encounter/user come from the active PHP
 * session (never trusted from POST), so a row here can only exist because
 * someone actually submitted this real form during a real session on this
 * real encounter - not something an external script can fabricate by
 * writing to a log file.
 *
 * @package OpenEMR
 */

require_once("../../globals.php");

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

if (!$encounter) {
    die(xlt("Internal error: we do not seem to be in an encounter!"));
}

$actionIds = $_POST['action_ids'] ?? [];
$actionIds = array_filter(array_map('trim', (array) $actionIds));

$newRow = sqlInsert(
    "INSERT INTO form_action_selection (date, pid, encounter, user, groupname, authorized, activity) " .
    "VALUES (NOW(), ?, ?, ?, ?, ?, 1)",
    [$pid, $encounter, $session->get('authUser'), $session->get('authProvider'), $userauthorized]
);
addForm($encounter, "Follow-up Action Selection", $newRow, "action_selection", $pid, $userauthorized);

foreach ($actionIds as $actionId) {
    sqlInsert(
        "INSERT INTO form_action_selection_items (form_action_selection_id, action_id) VALUES (?, ?)",
        [$newRow, $actionId]
    );
}

formHeader("Redirecting....");
formJump();
formFooter();
