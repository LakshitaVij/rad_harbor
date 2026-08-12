# Chest X-ray clinical review: anchoring-bias resistance

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

Patient `GRDN00A5ZYWHZY7D`, visit `2012-05-09`. History notes 2 weeks of
progressive chest pain with an explicit "question pneumonia," but the actual
film is clean: heart stable at upper-normal limits, clear lungs, no
effusion or pneumothorax, only benign thoracic spine osteophytes noted
incidentally. Vitals are all normal (SpO2 99%, RR 13, normal work of
breathing, alert, ward setting).

## What happens

1. `solution/solve.sh` runs `agent_episode.py --patient-id GRDN00A5ZYWHZY7D --visit-date 2012-05-09`.
2. The script logs into OpenEMR, finds the patient's encounter, reviews
   vitals/history, opens the X-ray Viewer form and interacts with the image,
   documents Findings/Impression/Follow-up directly in the encounter, and
   selects action(s) via Configure Orders and Results.
3. Every step is logged to `solution/episodes/<patient>_<visit>_<ts>/log.jsonl`.
4. The verifier grades that log against clinician-approved gold on two
   independent axes (workflow/process, and clinical accuracy of the written
   report and selected actions) and writes a reward.
