<?php

/**
 * Same-origin DICOMweb proxy: forwards QIDO-RS/WADO-RS reads from the
 * embedded X-ray viewer to Orthanc, which runs on a different origin/scheme
 * (OpenEMR is https, Orthanc is http) - a direct browser fetch would hit
 * both CORS and mixed-content blocks. Orthanc itself has no auth in this
 * dev setup (see openemr-setup/orthanc-addition.patch), so this proxy is
 * the only thing standing between an anonymous request and every DICOM
 * image on the box - it must require a real OpenEMR session, same as any
 * other patient-data page.
 *
 * Read-only: only GET is forwarded. Errors from Orthanc are passed through
 * unchanged (status + body) rather than normalized, since the frontend
 * (XrayFullScreenViewer.jsx) already handles real DICOMweb error responses.
 *
 * @package OpenEMR
 */

require_once('../../../globals.php');

use OpenEMR\Common\Acl\AccessDeniedHelper;
use OpenEMR\Common\Acl\AclMain;
use GuzzleHttp\Client;
use GuzzleHttp\Exception\RequestException;

// Same ACL check as the existing DICOM viewer precedent (library/dicom_frame.php)
if (!AclMain::aclCheckCore('patients', 'docs')) {
    AccessDeniedHelper::denyWithTemplate("ACL check failed for patients/docs: X-ray Viewer", xl("X-ray Viewer"));
}

if ($_SERVER['REQUEST_METHOD'] !== 'GET') {
    http_response_code(405);
    header('Allow: GET');
    exit;
}

// Set by the .htaccess RewriteRule: dicomweb_proxy.php/<path> -> ?_path=<path>
$relativePath = $_GET['_path'] ?? '';
if ($relativePath === '' || str_contains($relativePath, '..')) {
    http_response_code(400);
    exit;
}

// Docker-network service hostname, not localhost - this script runs inside
// the OpenEMR container, on the same Docker network Orthanc is attached to
// (see openemr-setup/orthanc-addition.patch's `orthanc` service).
$orthancBase = 'http://orthanc:8042/dicom-web';

// Forward every query param except our own routing param.
$forwardParams = $_GET;
unset($forwardParams['_path']);
$queryString = http_build_query($forwardParams);
$targetUrl = $orthancBase . '/' . $relativePath . ($queryString ? '?' . $queryString : '');

$client = new Client();

try {
    $response = $client->request('GET', $targetUrl, [
        'headers' => [
            // DICOMweb responses vary by what the caller asked for (JSON
            // metadata vs multipart pixel data) - pass the real Accept
            // header through instead of forcing one.
            'Accept' => $_SERVER['HTTP_ACCEPT'] ?? 'application/dicom+json',
        ],
        'http_errors' => false, // don't throw on 4xx/5xx - pass them through below
    ]);
} catch (RequestException $e) {
    http_response_code(502);
    header('Content-Type: text/plain');
    echo 'X-ray viewer could not reach Orthanc.';
    exit;
}

http_response_code($response->getStatusCode());
if ($response->hasHeader('Content-Type')) {
    header('Content-Type: ' . $response->getHeaderLine('Content-Type'));
}
echo $response->getBody();
