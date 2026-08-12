<?php

/**
 * X-ray Dashboard Link module Bootstrap class.
 *
 * Adds an "Open X-ray" button to the patient dashboard, pointing at the
 * patient's most recent visit that has real DICOM imaging attached (via
 * the X-ray Viewer form - see interface/forms/xray_viewer/). Uses
 * RenderEvent::EVENT_SECTION_LIST_RENDER_BEFORE, the same dashboard
 * injection point oe-module-dashboard-context uses, so demographics.php
 * itself never needs to be touched.
 *
 * @package OpenEMR
 */

namespace OpenEMR\Modules\XrayDashboardLink;

use OpenEMR\Core\OEGlobalsBag;
use OpenEMR\Events\PatientDemographics\RenderEvent;
use Symfony\Component\EventDispatcher\EventDispatcherInterface;

class Bootstrap
{
    public function __construct(
        private readonly EventDispatcherInterface $eventDispatcher
    ) {
    }

    public function subscribeToEvents(): void
    {
        $this->eventDispatcher->addListener(RenderEvent::EVENT_SECTION_LIST_RENDER_BEFORE, $this->renderWidget(...));
    }

    public function renderWidget(RenderEvent $event): void
    {
        $pid = $event->getPid();
        if (empty($pid)) {
            return;
        }

        $row = sqlQuery(
            "SELECT fe.date FROM forms f " .
            "JOIN form_encounter fe ON fe.pid = f.pid AND fe.encounter = f.encounter " .
            "WHERE f.formdir = 'xray_viewer' AND f.pid = ? AND f.deleted = 0 " .
            "ORDER BY fe.date DESC LIMIT 1",
            [$pid]
        );

        // No imaging for this patient at all - nothing to link to, don't
        // show a dead-end button.
        if (empty($row['date'])) {
            return;
        }

        $mostRecentDate = date('Y-m-d', strtotime((string) $row['date']));
        $rootdir = OEGlobalsBag::getInstance()->get('rootdir');
        $openUrl = $rootdir . '/forms/xray_viewer/open_latest.php';
        ?>
        <div class="card mb-3" id="card_xray_dashboard_link">
            <div class="card-header d-flex justify-content-between align-items-center">
                <span><?php echo xlt('X-ray'); ?></span>
            </div>
            <div class="card-body d-flex justify-content-between align-items-center">
                <span class="text-muted small">
                    <?php echo xlt('Most recent'); ?>: <?php echo text($mostRecentDate); ?>
                </span>
                <a href="<?php echo attr($openUrl); ?>" class="btn btn-primary btn-sm">
                    <?php echo xlt('Open'); ?> &rarr;
                </a>
            </div>
        </div>
        <?php
    }
}
