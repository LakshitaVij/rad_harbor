-- Registers the X-ray Viewer as an encounter form, same mechanism as
-- every other entry in sql/database.sql's registry seed block (e.g.
-- 'Clinical Notes'/'clinical_notes'). priority 0 matches the convention
-- used by every other clinical form (SOAP, ROS, vitals, etc.) rather than
-- an arbitrary higher number that would reorder the existing form list.
INSERT INTO `registry` (name, state, directory, sql_run, unpackaged, date, priority, category, patient_encounter, aco_spec)
VALUES ('X-ray Viewer', 1, 'xray_viewer', 1, 0, NOW(), 0, 'Clinical', 1, 'encounters|notes');
