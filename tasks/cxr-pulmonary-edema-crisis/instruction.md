# Chest X-ray clinical review: multi-finding pulmonary edema crisis

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

Patient `GRDN00BKCEOKC7S1`, visit `2025-07-23` - a patient with a cardiac
conduction device, in the ED with "increased oxygen requirements." Three
real findings at once: cardiomegaly, worsening pulmonary vascular
congestion, and bilateral pleural effusions with associated airspace disease
(right greater than left). Vitals are critical: SpO2 72%, RR 33, severe
work of breathing, confused mental status.

## What happens

1. `solution/solve.sh` runs `agent_episode.py --patient-id GRDN00BKCEOKC7S1 --visit-date 2025-07-23`.
2. The script logs into OpenEMR, finds the patient's encounter, reviews
   vitals/history, opens the X-ray Viewer form and interacts with the image,
   documents Findings/Impression/Follow-up directly in the encounter, and
   selects action(s) via Configure Orders and Results.
3. Every step is logged to `solution/episodes/<patient>_<visit>_<ts>/log.jsonl`.
4. The verifier grades that log against clinician-approved gold on two
   independent axes (workflow/process, and clinical accuracy of the written
   report and selected actions) and writes a reward.
