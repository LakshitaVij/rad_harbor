<?php

/**
 * X-ray Viewer form new.php
 *
 * Modeled on clinical_notes/new.php's lightweight (non-C_Form-class)
 * pattern - this form has no user-editable fields of its own, it just
 * embeds the Cornerstone3D X-ray viewer for the encounter's imaging. Since
 * there is nothing for the user to fill in and submit, the forms/
 * form_xray_viewer rows are created immediately on first load (mirroring
 * what save.php would otherwise do for a real data-entry form) rather than
 * waiting for an explicit save action that will never come.
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
    $formId = $newRow;
}

// Short-lived, subject-scoped token for public/index.php to verify - the
// iframe boundary means that page can't read the parent's PHP session
// directly, so identity/authorization has to be handed across explicitly
// rather than assumed. Same verification mechanism dicom_frame.php uses
// for its own sensitive param (CsrfUtils), applied here as a scoped token
// instead of a form-submission check since this is a GET-loaded iframe.
$csrfToken = CsrfUtils::collectCsrfToken($session, 'api');

// Absolute ($rootdir-based), not relative - real production navigation
// doesn't load this file directly. OpenEMR's own "Edit Form" flow requests
// interface/patient_file/encounter/view_form.php, which require()'s our
// view.php/new.php INTO its own response rather than the browser ever
// requesting new.php's URL directly - confirmed via a live OpenEMR session
// (my own dev testing had navigated straight to new.php's URL, which
// masked this). That means the browser's actual document URL for this
// page is view_form.php's, so a relative "public/index.php" iframe src
// resolved to .../patient_file/encounter/public/index.php (404) instead of
// this form's own public/ directory.
$iframeSrc = $rootdir . "/forms/xray_viewer/public/index.php?pid=" . urlencode((string) $pid)
    . "&encounter=" . urlencode((string) $encounter)
    . "&csrf_token=" . urlencode($csrfToken);

// Absolute, webroot-relative path - correct regardless of how deep this
// page happens to be loaded in OpenEMR's tab/frame structure. Same pattern
// delete_form.php uses for its Cancel button's location.href target
// ($rootdir/patient_file/encounter/forms.php), including the same
// same-frame navigation (no top./parent. escaping needed - this page
// occupies whatever frame level OpenEMR loaded it into, same as
// delete_form.php does).
$backToChartUrl = $rootdir . "/patient_file/encounter/forms.php";
?>
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title><?php echo xlt('X-ray Viewer'); ?></title>
    <style>
        /* Deliberately no OpenEMR/Bootstrap styling loaded for the iframe
           below - the embedded viewer's own CSS (Cornerstone3D
           canvas/toolbar) would conflict with it, same reasoning
           library/dicom_frame.php gives for keeping its DICOM viewer
           wrapper bootstrap-free. The header bar above it is plain/minimal
           for the same reason - kept out of the iframe entirely. */
        html, body { margin: 0; padding: 0; height: 100%; overflow: hidden; }
        .xray-header {
            display: flex; align-items: center; height: 40px; padding: 0 12px;
            background: #111; border-bottom: 1px solid #333; font-family: sans-serif;
        }
        .xray-header a {
            color: #7fd9a8; text-decoration: none; font-size: 0.95rem; font-weight: 600;
        }
        .xray-header a:hover { text-decoration: underline; }
        iframe { border: none; width: 100%; height: calc(100vh - 40px); display: block; }
    </style>
</head>
<body>
    <div class="xray-header">
        <a href="#" id="back-to-chart" onclick="top.restoreSession(); location.href=<?php echo js_escape($backToChartUrl); ?>; return false;">&larr; <?php echo xlt('Back to Chart'); ?></a>
    </div>
    <iframe id="xray-viewer-frame" src="<?php echo attr($iframeSrc); ?>" allow="fullscreen"></iframe>
</body>
</html>
