<?php

/**
 * Follow-up Action Selection form report.php
 *
 * @package OpenEMR
 */

function action_selection_report($pid, $encounter, $cols, $id, $print = true)
{
    $data = formFetch("form_action_selection", $id);
    if (empty($data)) {
        return;
    }

    $items = sqlStatement(
        "SELECT i.action_id, p.name FROM form_action_selection_items i " .
        "LEFT JOIN procedure_type p ON p.procedure_code = i.action_id " .
        "WHERE i.form_action_selection_id = ?",
        [$id]
    );

    echo "<table><tr><td class='bold'>" . xlt('Selected Follow-up Action(s)') . "</td></tr>";
    while ($row = sqlFetchArray($items)) {
        $label = $row['name'] ? $row['name'] . ' (' . $row['action_id'] . ')' : $row['action_id'];
        echo "<tr><td>" . text($label) . "</td></tr>";
    }
    echo "</table>";
}
