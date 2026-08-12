<?php

/**
 * X-ray Viewer form report.php
 *
 * No text fields to summarize (the form is a live image viewer, not
 * stored data) - renders one confirmation line rather than leaving this
 * form's section of the encounter report blank, which would otherwise look
 * like a rendering bug next to every other form's real content.
 *
 * @package OpenEMR
 */

require_once(__DIR__ . "/../../globals.php");

function xray_viewer_report($pid, $encounter, $cols, $id): void
{
    $record = sqlQuery("SELECT `date` FROM form_xray_viewer WHERE id = ?", [$id]);
    $date = $record['date'] ?? null;

    echo "<table><tr><td class='detail'>";
    if ($date) {
        echo xlt('X-ray Viewer reviewed') . ' - ' . text(oeFormatDateTime($date));
    } else {
        echo xlt('X-ray Viewer reviewed');
    }
    echo "</td></tr></table>";
}
