<?php

/**
 * X-ray Dashboard Link module bootstrap.
 *
 * Modeled on oe-module-dashboard-context's registration pattern (the
 * existing precedent for injecting into the patient dashboard without
 * patching demographics.php core).
 *
 * @package OpenEMR
 */

use OpenEMR\Core\ModulesClassLoader;
use OpenEMR\Core\OEGlobalsBag;
use OpenEMR\Modules\XrayDashboardLink\Bootstrap;

$file = OEGlobalsBag::getInstance()->getProjectDir();
$classLoader = new ModulesClassLoader($file);
$classLoader->registerNamespaceIfNotExists('OpenEMR\\Modules\\XrayDashboardLink\\', __DIR__ . DIRECTORY_SEPARATOR . 'src');

$eventDispatcher = OEGlobalsBag::getInstance()->getKernel()->getEventDispatcher();
$bootstrap = new Bootstrap($eventDispatcher);
$bootstrap->subscribeToEvents();
