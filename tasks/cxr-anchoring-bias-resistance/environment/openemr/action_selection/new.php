<?php

/**
 * Follow-up Action Selection form new.php
 *
 * Real, encounter-scoped selection of follow-up action(s) from the same
 * action catalog "Configure Orders and Results" (types.php) manages -
 * queried live from procedure_type, not duplicated. Unlike Configure
 * Orders and Results (a global admin/config screen with no patient
 * concept), a selection made here is tied to this specific pid/encounter
 * and saved by this form's own save.php - a real, server-side record of
 * what was actually selected, not just a claim logged elsewhere.
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
$csrfToken = CsrfUtils::collectCsrfToken($session);

$categories = [];
$rows = sqlStatement(
    "SELECT c.name AS category, a.name AS action_name, a.procedure_code AS action_id " .
    "FROM procedure_type a JOIN procedure_type c ON c.procedure_type_id = a.parent " .
    "WHERE c.procedure_type = 'grp' AND a.procedure_code != '' " .
    "ORDER BY c.procedure_type_id, a.procedure_type_id"
);
while ($row = sqlFetchArray($rows)) {
    $categories[$row['category']][] = ['id' => $row['action_id'], 'name' => $row['action_name']];
}
?>
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title><?php echo xlt('Follow-up Action Selection'); ?></title>
    <style>
        body { padding: 16px; }
        .action-category { margin-bottom: 1rem; }
        .action-category h4 { margin-bottom: 0.4rem; }
        .action-item { margin-left: 1rem; }
    </style>
</head>
<body>
    <form method="post" action="<?php echo attr(OEGlobalsBag::getInstance()->getWebRoot()); ?>/interface/forms/action_selection/save.php">
        <input type="hidden" name="csrf_token_form" value="<?php echo attr($csrfToken); ?>" />
        <h3><?php echo xlt('Select follow-up action(s) for this encounter'); ?></h3>
        <?php foreach ($categories as $categoryName => $actions) { ?>
            <div class="action-category">
                <h4><?php echo text($categoryName); ?></h4>
                <?php foreach ($actions as $action) { ?>
                    <div class="action-item form-check">
                        <input class="form-check-input" type="checkbox" name="action_ids[]"
                               id="action_<?php echo attr($action['id']); ?>" value="<?php echo attr($action['id']); ?>">
                        <label class="form-check-label" for="action_<?php echo attr($action['id']); ?>">
                            <?php echo text($action['name']); ?> (<?php echo text($action['id']); ?>)
                        </label>
                    </div>
                <?php } ?>
            </div>
        <?php } ?>
        <button type="submit" class="btn btn-primary" id="save-action-selection"><?php echo xlt('Save'); ?></button>
    </form>
</body>
</html>
