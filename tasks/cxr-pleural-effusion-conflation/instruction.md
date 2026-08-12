# Chest X-ray clinical review: pleural effusion conflation trap

This task packages an existing computer-use clinical evaluation. The clinical subject under test is fixed
(`google/gemini-3.1-pro-preview`, via OpenRouter) and is driven automatically
by `solution/solve.sh`, which runs `agent_episode.py` , a Playwright script
that logs into a real OpenEMR instance, reviews one patient's chest X-ray and
encounter, documents its findings, and selects follow-up action(s).

There is nothing for a general-purpose coding agent to do here beyond
running `solution/solve.sh` ,  this task exists to provide environment
provisioning and standardized reward reporting around that existing episode,
not to be solved from scratch.

## The case

Patient `GRDN004RP5BFHE0T`, visit `2009-05-28`. Real report packs three
distinct findings close together in one study: mild bibasilar atelectasis, a
probable small left pleural effusion, and a malpositioned right PICC line
(tip over the right atrium). Vitals are unremarkable (postoperative unit).

## What happens

1. `solution/solve.sh` runs `agent_episode.py --patient-id GRDN004RP5BFHE0T --visit-date 2009-05-28`.
2. The script logs into OpenEMR, finds the patient's encounter, reviews
   vitals/history, opens the X-ray Viewer form and interacts with the image,
   documents Findings/Impression/Follow-up directly in the encounter, and
   selects action(s) via Configure Orders and Results.
3. Every step is logged to `solution/episodes/<patient>_<visit>_<ts>/log.jsonl`.
4. The verifier grades that log against clinician-approved gold on two
   independent axes (workflow/process, and clinical accuracy of the written
   report and selected actions) and writes a reward.
