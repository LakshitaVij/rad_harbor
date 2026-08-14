INSERT INTO registry
  (name, state, directory, sql_run, unpackaged, date, priority, category, nickname, patient_encounter, therapy_group_encounter, aco_spec, form_foreign_id)
SELECT 'X-ray Viewer', 1, 'xray_viewer', 1, 0, NOW(), 0, 'Clinical', NULL, 1, 0, 'encounters|notes', NULL
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM registry WHERE directory = 'xray_viewer');
