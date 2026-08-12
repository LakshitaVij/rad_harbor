<?php

/**
 * X-ray Viewer SPA shell.
 *
 * Loaded inside new.php's <iframe>. Re-authenticates via the normal
 * OpenEMR session (this is a same-origin request, so the session cookie is
 * sent same as any other page) rather than trusting the GET params blindly
 * - pid/encounter/csrf_token in the URL are a tamper/staleness check
 * against the session's own values, not the source of truth themselves.
 * Injects window.__XRAY_BOOTSTRAP__ with the real DICOM identifiers, which
 * turn out to already exist natively in OpenEMR: patient_data.lname is the
 * exact DICOM PatientID string, and form_encounter.date is the exact DICOM
 * StudyDateTime - confirmed against the real seeded data, not guessed. No
 * separate imaging-lookup table or service needed.
 *
 * @package OpenEMR
 */

require_once('../../../globals.php');

use OpenEMR\Common\Csrf\CsrfUtils;
use OpenEMR\Common\Session\SessionWrapperFactory;
use OpenEMR\Core\OEGlobalsBag;
use OpenEMR\Services\PatientService;

$srcdir = OEGlobalsBag::getInstance()->getSrcDir();
require_once("$srcdir/api.inc.php");

$session = SessionWrapperFactory::getInstance()->getActiveSession();

$sessionPid = (string) $session->get('pid');
$sessionEncounter = (string) $session->get('encounter');
$requestPid = (string) ($_GET['pid'] ?? '');
$requestEncounter = (string) ($_GET['encounter'] ?? '');
$csrfToken = $_GET['csrf_token'] ?? '';

if (
    $requestPid === '' || $requestEncounter === ''
    || $requestPid !== $sessionPid || $requestEncounter !== $sessionEncounter
    || !CsrfUtils::verifyCsrfToken($csrfToken, $session, 'api')
) {
    http_response_code(403);
    exit;
}

$pid = $sessionPid;
$encounter = $sessionEncounter;

$patientService = new PatientService();
$patient = $patientService->findByPid($pid);
$dicomPatientId = $patient['lname'] ?? '';

$encounterRow = sqlQuery("SELECT `date` FROM form_encounter WHERE pid = ? AND encounter = ?", [$pid, $encounter]);
$studyDateYYYYMMDD = $encounterRow['date'] ? date('Ymd', strtotime((string) $encounterRow['date'])) : '';

$age = null;
if (!empty($patient['DOB'])) {
    $dob = new DateTime((string) $patient['DOB']);
    $age = $dob->diff(new DateTime())->y;
}
$sex = !empty($patient['sex']) ? strtoupper(substr((string) $patient['sex'], 0, 1)) : '';

$bootstrap = [
    'pid' => $pid,
    'encounter' => $encounter,
    'patientId' => $dicomPatientId,
    'studyDateYYYYMMDD' => $studyDateYYYYMMDD,
    'patientDemographics' => [
        'age' => $age,
        'sex' => $sex,
    ],
];

$manifestPath = __DIR__ . '/dist/.vite/manifest.json';
if (!file_exists($manifestPath)) {
    http_response_code(500);
    echo 'X-ray viewer bundle not built (dist/ missing). Run `npm run build` in xray-viewer-frontend/.';
    exit;
}
$manifest = json_decode(file_get_contents($manifestPath), true);
$entry = $manifest['index.html'] ?? null;
if (!$entry) {
    http_response_code(500);
    echo 'X-ray viewer bundle manifest missing its entry point.';
    exit;
}
$entryJs = 'dist/' . $entry['file'];
$entryCss = array_map(static fn($f) => 'dist/' . $f, $entry['css'] ?? []);
?>
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title><?php echo xlt('X-ray Viewer'); ?></title>
    <?php foreach ($entryCss as $css): ?>
    <link rel="stylesheet" href="<?php echo attr($css); ?>">
    <?php endforeach; ?>
</head>
<body>
    <div id="root"></div>
    <script>window.__XRAY_BOOTSTRAP__ = <?php echo json_encode($bootstrap, JSON_HEX_TAG | JSON_HEX_AMP | JSON_HEX_APOS | JSON_HEX_QUOT); ?>;</script>
    <script type="module" src="<?php echo attr($entryJs); ?>"></script>
</body>
</html>
