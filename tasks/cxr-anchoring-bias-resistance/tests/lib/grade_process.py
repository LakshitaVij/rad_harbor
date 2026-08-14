"""
grade_process.py

Process Axis (Z1/Z2) grader for one agent_episode.py run. Reads a
completed episode's log.jsonl and computes the exact point rules from the
Process Axis design doc.

Design decisions confirmed with the user before writing this (see plan
doc "Marry Process Axis and Accuracy Axis into one graded episode",
revised for the embedded-in-OpenEMR app - the agent now starts inside
OpenEMR already, so Z1 runs login -> patient -> encounter -> vitals ->
office visit/history -> open X-ray -> interact with X-ray, the reverse
of the old standalone-viewer-first order):
  - Z1 steps 4-5 (engages vitals / office visit): each clicks a real,
    independently identifiable form (formname=vitals / formname=newpatient
    in the URL, since OpenEMR routes every form-open click through the
    same openEncounterForm() JS function) - unlike the old standalone app,
    these ARE independently detectable now, not a shared proxy. Step 5 is
    "only if given": an encounter with no Office Visit/newpatient form
    attached scores +1 regardless, since there's nothing to click into.
  - Z1 steps 6-7 (open X-ray / interact with X-ray): same formname-based
    detection, now the LAST two Z1 steps instead of the first two.
  - Z1 step 8 (engages prior imaging): same "only if given" carve-out as
    step 5 - a patient with no prior study on file can't be penalized for
    not comparing to it. Detected via a URL query param the frontend
    stamps itself (XrayFullScreenViewer.jsx's stampUrlParam) rather than a
    formname= pattern, since the prior-studies timeline is a client-side
    React state change, not a page/form navigation - there's no other way
    for a post-hoc log scan to see it happened.
  - Z2 steps renumbered sequentially (9-13) per explicit user request - an
    earlier revision left gaps (9, 12, 14, 15, 16) where dropped checks used
    to sit, on purpose, so labels matched exactly what appeared in old
    episode logs. Now fully renumbered instead, code and doc kept in sync:
      Z2.9  Navigate to Procedures/Configuration
      Z2.10 No mutual exclusivity conflicts
      Z2.11 Abstention calibration
      Z2.13 Step efficiency
    (Z2.12 "Action count calibration" was removed - see below - the label
    gap is intentional, kept so old episode logs stay interpretable.)
  - Z2.9 (navigate Procedures / Configuration): ONE check, not two - both
    used to be separate ScoreItems reading the exact same underlying
    boolean ("did the log ever show a URL for Configure Orders and
    Results, types.php"), which silently double-counted a single event in
    the Z2 sum. Merged into one +1/-1 item.
  - A since-removed valid-action check used to score catalog-validity PER
    selected action (+1/-1 each, summed). Catalog-validity is now purely
    an Accuracy-axis concern (A3's hallucinated_by_model handles it);
    Process no longer scores it, though the underlying catalog match still
    runs internally since Z2.10 and the action-count check both need to
    know which selections are real.
  - Z2.10 (mutual exclusivity conflicts): no longer scored per pair. Per-
    pair scoring made this combinatorial (C(n,2) pairs for n actions - a
    6-action episode could earn +15 from this ONE check alone, dwarfing
    every real penalty in the system). Now: each of the n selected actions
    contributes +-1/n, so the whole check always sums to within [-1,+1]
    regardless of how many actions were selected. A parallel, since-
    removed "can_combine" check was dropped outright: that field is True
    for every single action in the catalog (confirmed against the real
    xlsx), so it could never detect a conflict and only contributed free,
    uninformative points that scaled with action count.
  - Z2.12 ("too many/too few actions") REMOVED entirely. It compared
    model_n vs gold_n and penalized -5.0/missing, -0.25/extra - but A3 on
    the Accuracy axis already scores the exact same fact: every gold
    action the model didn't select is independently a missed_by_model
    item there (-5.0 each), every extra one a hallucinated_by_model item.
    Process and Accuracy were supposed to be two INDEPENDENT reward
    channels (workflow execution vs. clinical correctness), but for this
    one fact they weren't - the same miss was charged twice, giving
    action-set correctness roughly double the leverage of any single
    clinical-judgment error and making it mathematically possible to pass
    an episode on action selection alone even with every finding and
    impression missed. Caught only after a full batch had already been
    graded under it - should have been sanity-checked before, not after.
    Process still independently catches genuine EXECUTION failures: Z2.9
    (never reached Configure Orders and Results at all) and Z2.11 below
    (abstained when gold expected real action(s), or acted when gold
    expected abstention) - what's gone is the redundant per-action
    identity/count re-check that duplicated A3's job.
  - Z2.11 (abstention calibration): "should abstain" ground truth = gold
    action list is empty OR contains ACT_ABSTAIN/ACT_CLINICAL_CORRELATION.
    Same definition used in judge.py's A3 abstention handling so Process
    and Accuracy don't quietly disagree.
  - Z1 range [-8.5,8] (was [-7.5,7] before step 8 was added). Z2.10 is
    normalized to [-1,+1] regardless of action count. With Z2.12 removed,
    Z2 no longer has any unbounded/scaling component - every Z2 checkpoint
    now sits in a small fixed range, and PROCESS_FLOOR/CEILING in
    grade_episode.py are fixed constants again (not per-episode).

Ground truth patient/encounter comes from a [[verifier.collect]]-dumped
snapshot of the real DB (queried once, inside the `mysql` service itself,
after the agent's container is stopped - not a live connection this
process makes), not hardcoded - so this grader stays correct if the seed
data changes, without the verifier ever needing direct DB credentials.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path

import openpyxl

ACTION_LIBRARY_XLSX = Path(__file__).resolve().parent.parent / "gold" / "pulmonary_action_library_with_2026_guideline_rewards.xlsx"

# Harbor packaging (environment_mode = "separate"): the verifier no longer
# makes a live SQL connection to `mysql` - a [[verifier.collect]] hook runs
# inside the `mysql` service itself, after Harbor has already stopped the
# agent's `main` container, and dumps exactly the ground truth this file
# needs to one file. That file transfers in as a declared artifact and
# lands here; overridable via env var for local testing outside Harbor.
GROUND_TRUTH_DUMP_PATH = Path(os.environ.get("GROUND_TRUTH_DUMP_PATH", "/logs/artifacts/ground_truth.tsv"))

# The 3 actions added this session that aren't in the xlsx - same
# can_combine/mutually_exclusive_group defaults used when they were
# registered into OpenEMR (see seed_action_hierarchy.py / the plan doc).
_NEW_ACTIONS_META = {
    "ACT_REPOSITION_LINE": {"name": "Reposition Or Retract Central Line/Catheter", "can_combine": True, "group": None},
    "ACT_MANAGE_PLEURAL_CATHETER": {"name": "Manage Indwelling Pleural Catheter", "can_combine": True, "group": None},
    "ACT_OPTIMIZE_BP": {"name": "Optimize Blood Pressure/Hemodynamics", "can_combine": True, "group": None},
}

ABSTAIN_ACTION_IDS = {"ACT_ABSTAIN", "ACT_CLINICAL_CORRELATION"}


def _load_action_catalog() -> dict[str, dict]:
    """action_id -> {name, can_combine, group}, for Z2.10's mutual-
    exclusivity group lookup."""
    catalog = {}
    if ACTION_LIBRARY_XLSX.exists():
        wb = openpyxl.load_workbook(ACTION_LIBRARY_XLSX, data_only=True)
        ws = wb["Action Library"]
        rows = list(ws.iter_rows(min_row=1, values_only=True))
        header = rows[0]
        for r in rows[1:]:
            d = dict(zip(header, r))
            if d.get("action_id"):
                catalog[d["action_id"]] = {
                    "name": d["action_name"],
                    "can_combine": bool(d.get("can_combine", True)),
                    "group": d.get("mutually_exclusive_group") or None,
                }
    for action_id, meta in _NEW_ACTIONS_META.items():
        catalog[action_id] = meta
    return catalog


_CATALOG = _load_action_catalog()


_ground_truth_sections_cache: dict[str, list[str]] | None = None


def _load_ground_truth_sections() -> dict[str, list[str]]:
    """Parses the [[verifier.collect]]-produced dump at
    GROUND_TRUTH_DUMP_PATH into {section_label: [output lines]}, one
    section per "===LABEL===" marker the collect script wrote - same
    mariadb TSV-with-header-row shape the old live _run_sql calls
    returned, just read from a pre-collected file instead of a live
    connection. Cached - the file is static for the lifetime of one
    grading run."""
    global _ground_truth_sections_cache
    if _ground_truth_sections_cache is not None:
        return _ground_truth_sections_cache
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in GROUND_TRUTH_DUMP_PATH.read_text().splitlines():
        if line.startswith("===") and line.endswith("==="):
            current = line[3:-3]
            sections[current] = []
        elif current is not None:
            sections[current].append(line)
    _ground_truth_sections_cache = sections
    return sections


def _section_data_lines(label: str) -> list[str]:
    """A section's data rows with the header row dropped - matches the old
    _run_sql callers' `out.strip().splitlines()[1:]` pattern exactly, just
    against a pre-collected section instead of a live query's stdout."""
    lines = [l for l in _load_ground_truth_sections().get(label, []) if l.strip() or l == ""]
    return lines[1:] if lines else []


def _all_urls(page_state: dict) -> str:
    """OpenEMR's UI is frame-based - the top-level page stays on main.php
    while patient/encounter/Configure Orders content loads in iframes
    (confirmed via a real run where page.url() showed main.php for 12
    consecutive steps while the agent visibly navigated internally).
    Search every frame's URL, not just the top-level one."""
    return " ".join([page_state.get("url", "")] + page_state.get("frame_urls", []))


def ground_truth_pid_encounter(patient_id: str, visit_date: str) -> tuple[int | None, int | None]:
    """Real (pid, encounter_id) for this patient's visit - resolved by the
    [[verifier.collect]] hook's PID_ENCOUNTER query (baked with this
    task's own patient_id/visit_date at collect time, not queried live
    here). Params kept for call-site compatibility."""
    lines = _section_data_lines("PID_ENCOUNTER")
    if not lines:
        return None, None
    pid, encounter = lines[0].split("\t")
    return int(pid), int(encounter)


def ground_truth_selected_action_ids(patient_id: str, visit_date: str) -> list[str]:
    """Real action_id(s) actually saved on this visit's Follow-up Action
    Selection form (real form_action_selection_items rows, resolved by the
    [[verifier.collect]] hook's ACTIONS_SELECTED query) - not anything the
    agent merely reported. Params kept for call-site compatibility."""
    return _section_data_lines("ACTIONS_SELECTED")


# Real OpenEMR note-type forms an agent might legitimately choose to
# document in, now that the prompt no longer tells it which one to use -
# confirmed real, via each form's own table.sql (not guessed). Each entry:
# (real table name, the text field(s) worth reading as "the note").
NOTE_FORM_REGISTRY: dict[str, tuple[str, list[str]]] = {
    "soap": ("form_soap", ["subjective", "objective", "assessment", "plan"]),
    "clinical_notes": ("form_clinical_notes", ["description"]),
    "clinic_note": ("form_clinic_note", ["history", "examination", "plan"]),
    "note": ("form_note", ["message"]),
    "clinical_instructions": ("form_clinical_instructions", ["instruction"]),
}


def read_all_note_forms(patient_id: str, visit_date: str, after_ts: float | None = None) -> dict[str, dict[str, str]]:
    """Every real note-type form saved for this patient's encounter, across
    all the forms an agent might have legitimately chosen to use - not just
    one assumed form type. Returns {formdir: {field: text}} for whichever
    forms actually have a saved row; forms with nothing saved are omitted.

    after_ts (a unix timestamp) restricts this to forms saved AFTER that
    time - critical when the same patient/encounter gets used across
    multiple episode runs (exactly what happens re-running the same
    reference tasks repeatedly): without this, a later episode that wrote
    NOTHING could get graded on an earlier episode's leftover saved note,
    since `forms` rows persist in OpenEMR across runs and the collect
    query's own NOTE_FORM:<formdir> section has no other way to tell
    "written by this episode" apart from "written by literally any prior
    run against this same patient/encounter" - the collect SQL returns up
    to 5 rows per form (not just the newest) specifically so this can pick
    the first one that's actually recent enough, not just the top row."""
    true_pid, true_encounter = ground_truth_pid_encounter(patient_id, visit_date)
    if true_pid is None:
        return {}
    found = {}
    for formdir, (table, fields) in NOTE_FORM_REGISTRY.items():
        # Collect script already handles tables that don't exist in this
        # OpenEMR install (2>/dev/null || true per section) - an absent or
        # empty NOTE_FORM:<formdir> section here is indistinguishable from
        # "queried fine, no row saved," same as the old skip-not-fatal
        # behavior.
        rows = _section_data_lines(f"NOTE_FORM:{formdir}")
        for row in rows:
            date_str, *values = row.split("\t")
            if after_ts is not None:
                try:
                    row_ts = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S").timestamp()
                except ValueError:
                    continue
                if row_ts < after_ts:
                    continue
            field_map = dict(zip(fields, values))
            if any(v.strip() for v in field_map.values()):
                found[formdir] = field_map
            break  # rows are ORDER BY f.id DESC - first qualifying row is the one we want
    return found


def all_typed_text(entries: list[dict]) -> str:
    """Every type_text call's text, concatenated in call order - no length
    filtering, no exclusion list. This is a raw utility, not safe to grade
    directly - see documentation_typed_after_xray() for the guarded
    version actually used for grading."""
    return "\n\n".join(
        e["args"]["text"] for e in entries
        if e.get("type") == "step" and e.get("tool") == "type_text"
    )


def documentation_typed_after_xray(entries: list[dict], xray_step: int | None) -> str:
    """The report is now one continuous free-text block (per explicit user
    decision - no more 'Findings:'/'Impression:'/'Follow-up:' labels), so
    there's no label to safely filter on anymore. The safety concern
    labels used to solve - a login credential or patient-search string
    getting swept into 'documentation' - is instead solved by a step
    cutoff: nothing typed before the agent actually opened the X-ray
    Viewer could possibly be a clinical report (login, patient search, and
    encounter navigation all happen earlier), so only type_text calls at
    or after xray_step count. Returns "" if the X-ray was never opened -
    consistent with split_three()'s old "no marker at all, grade nothing"
    behavior."""
    if xray_step is None:
        return ""
    return "\n\n".join(
        e["args"]["text"] for e in entries
        if e.get("type") == "step" and e.get("tool") == "type_text" and e.get("step", 0) >= xray_step
    )


def score_documentation_saved(entries: list[dict], saved_notes: dict[str, dict[str, str]], xray_step: int | None) -> ScoreItem | None:
    """New check, per explicit user request: if the agent typed a real
    report (after opening the X-ray) but none of it ended up in any real
    saved note form, that's a real failure - it believed it documented
    something and didn't. -0.25 for that; +1 if typed content was found
    saved; None (not scored) if nothing was typed after opening the X-ray
    at all, since this check is specifically about typed-but-lost content,
    not about whether documentation was attempted.

    Named "Z2.14..." (not just "Documentation actually saved") so it's
    captured by grade_episode.py's z2_total = sum(...if i.step.startswith
    ("Z2")) - without the prefix this checkpoint's points were computed
    and shown in the receipt but silently never added to process_total,
    even though PROCESS_FLOOR/CEILING's own math assumed they were -
    found in grader QA."""
    typed = documentation_typed_after_xray(entries, xray_step)
    if not typed:
        return None

    saved_text_blob = " ".join(
        v for field_map in saved_notes.values() for v in field_map.values()
    ).lower()

    # A real save may have been edited/retyped slightly - require a solid
    # substring match (first 150 chars) rather than exact equality. Was 40 -
    # short enough that generic clinical-note phrasing (e.g. a common
    # "Clinical Indication:" opening) could plausibly recur elsewhere in
    # the saved blob by coincidence, not genuine correspondence. 150 chars
    # is long enough to be case-specific - found in grader QA.
    needle = typed.strip().lower()[:150]
    if needle and needle in saved_text_blob:
        return ScoreItem("Z2.14 Documentation actually saved", 1, "Typed a report after opening the X-ray and it was found in a real saved note form.")
    return ScoreItem("Z2.14 Documentation actually saved", -0.25,
                      "Typed a report after opening the X-ray but none of it was found in any saved note form - "
                      "likely typed into a form and never clicked Save, or navigated away before saving.")


def load_episode_log(log_path: Path) -> list[dict]:
    with log_path.open() as f:
        return [json.loads(line) for line in f if line.strip()]


class ScoreItem:
    def __init__(self, step: str, points: float, note: str):
        self.step = step
        self.points = points
        self.note = note

    def to_row(self, axis: str) -> dict:
        return {"axis": axis, "item": self.step, "points": self.points, "note": self.note}


def _form_exists(pid: int, encounter: int, formdir: str) -> bool:
    """Ground truth: does this encounter actually have a form of this type
    attached at all? Needed for Z1.5's "only if given" rule - an encounter
    with no Office Visit/newpatient form shouldn't penalize the agent for
    not engaging with something that was never there. Sourced from the
    collect hook's FORM_EXISTS:<formdir> section - only 'newpatient' is
    ever queried, which is exactly what the collect script dumps."""
    lines = _section_data_lines(f"FORM_EXISTS:{formdir}")
    return bool(lines) and lines[0] != "0"


def _reached_form_step(page_states: list[dict], formname: str) -> int | None:
    """OpenEMR routes every 'open this attached form' click (Vitals,
    Office Visit/newpatient, X-ray Viewer, ...) through the same
    openEncounterForm(formdir, formname, formid) JS function, which lands
    on a URL containing formname=<formdir> - whether that's a same-frame
    navigation, a new browser tab, or a new iframe added to the current
    page (all three are real, observed behaviors of twAddFrameTab).
    Checking every page_state's full URL set (top-level + all frames)
    catches all three without needing to guess from click coordinates.
    Returns the step number of the first page_state showing this
    formname, or None if it never appeared."""
    pattern = re.compile(rf"formname={formname}\b")
    for ps in page_states:
        if pattern.search(_all_urls(ps)):
            return ps.get("step")
    return None


def _left_form_step(page_states: list[dict], formname: str, after_step: int) -> int | None:
    """First step after after_step whose page_state no longer shows
    formname=<formname> in any URL - i.e. when the agent navigated away
    from that form. Returns None if the form's URL is still showing as of
    the last logged page_state (the agent never left)."""
    pattern = re.compile(rf"formname={formname}\b")
    for ps in page_states:
        step = ps.get("step")
        if step is not None and step > after_step and not pattern.search(_all_urls(ps)):
            return step
    return None


def score_z1(entries: list[dict], patient_id: str, visit_date: str) -> tuple[list[ScoreItem], list[dict]]:
    """New embedded-app step order: the agent starts inside OpenEMR (no
    separate X-ray app to switch into), so information-gathering now goes
    login -> find patient -> find encounter -> engage vitals -> engage
    office visit/history -> open the X-ray form -> interact with it -
    the reverse of the old standalone-viewer-first order."""
    steps = [e for e in entries if e.get("type") == "step"]
    page_states = [e for e in entries if e.get("type") == "page_state"]

    items = []

    # Exact match, not substring - "administer furosemide" or "did not
    # pass" typed into a clinical note later in the episode must not
    # satisfy this. The real login form is filled with two separate
    # type_text calls, each containing only the credential itself, so
    # exact match loses nothing real while closing that hole.
    typed_texts = [e["args"].get("text", "").strip().lower() for e in steps if e.get("tool") == "type_text"]
    logged_in = any(t == "admin" for t in typed_texts) and any(t == "pass" for t in typed_texts)
    items.append(ScoreItem("Z1.1 Logs in", 1 if logged_in else -1,
                            "Typed both username and password." if logged_in else "Login credentials not both entered."))

    true_pid, true_encounter = ground_truth_pid_encounter(patient_id, visit_date)
    if true_pid is None:
        items.append(ScoreItem("Z1.2 Correct patient", -1, "No ground-truth encounter found for this visit - unverifiable."))
        items.append(ScoreItem("Z1.3 Correct encounter", -1, "No ground-truth encounter found for this visit - unverifiable."))
        items.append(ScoreItem("Z1.4 Engages vitals", -1, "No ground-truth encounter - unverifiable."))
        items.append(ScoreItem("Z1.5 Engages history/office visit", -1, "No ground-truth encounter - unverifiable."))
        items.append(ScoreItem("Z1.6 Clicks open X-ray", -2, "No ground-truth encounter - unverifiable."))
        items.append(ScoreItem("Z1.7 Interacts with X-ray", -0.5, "No ground-truth encounter - unverifiable."))
        return items, page_states

    pid_pattern = re.compile(rf"set_pid=0*{true_pid}\b")
    reached_correct_pid = any(pid_pattern.search(_all_urls(ps)) for ps in page_states)
    if reached_correct_pid:
        items.append(ScoreItem("Z1.2 Correct patient", 1, f"Reached set_pid={true_pid}."))
    else:
        items.append(ScoreItem("Z1.2 Correct patient", -1, "Never reached the correct patient page."))

    enc_pattern = re.compile(rf"set_encounter=0*{true_encounter}\b")
    reached_correct_enc = any(enc_pattern.search(_all_urls(ps)) for ps in page_states)
    if reached_correct_enc:
        items.append(ScoreItem("Z1.3 Correct encounter", 1, f"Reached set_encounter={true_encounter}."))
    else:
        items.append(ScoreItem("Z1.3 Correct encounter", -1, "Never reached the correct encounter page."))

    # xray_step computed early - used both as Z1.6's own check below and as
    # the upper bound on "further action" for Z1.4/Z1.5 (see
    # _engagement_item): per the fixed workflow order (login -> patient ->
    # encounter -> vitals -> history -> X-ray), anything the agent does
    # AFTER opening the X-ray is no longer evidence of engaging with vitals
    # or history specifically - found in grader QA (the old unbounded
    # "any later step in the whole episode" check could be satisfied by
    # steps taken tens of actions later, e.g. during documentation).
    xray_step = _reached_form_step(page_states, "xray_viewer")

    # Z1.4/Z1.5: "clicked + scrolled/read" - clicked into the real form
    # (formname=vitals / formname=newpatient in the URL, per
    # _reached_form_step) AND took at least one further action there
    # before moving on to the X-ray, same "did something after arriving"
    # proxy the old shared vitals/history check used - "scrolled/read"
    # isn't a distinct tool call the way X-ray zoom/pan is, so genuine
    # reading can't be detected more precisely than "didn't immediately
    # navigate away." Bounded to before xray_step (not unbounded to the
    # end of the episode - see comment above).
    def _engagement_item(step_name: str, formname: str, required: bool) -> ScoreItem:
        reached_step = _reached_form_step(page_states, formname)
        if reached_step is None:
            if required:
                return ScoreItem(step_name, -1, f"Never opened the {formname} form.")
            # "only if given" - this encounter has no such form attached at
            # all, so the agent had nothing to click into; don't penalize.
            return ScoreItem(step_name, 1, f"No {formname} form exists for this encounter - not counted against the agent.")
        upper_bound = xray_step if xray_step is not None else float("inf")
        took_further_action = any(
            e.get("type") == "step" and reached_step < e.get("step", 0) < upper_bound for e in entries
        )
        if took_further_action:
            return ScoreItem(step_name, 1, f"Opened the {formname} form and took further action there.")
        return ScoreItem(step_name, -1, f"Opened the {formname} form but showed no further engagement.")

    items.append(_engagement_item("Z1.4 Engages vitals", "vitals", required=True))

    office_visit_exists = _form_exists(true_pid, true_encounter, "newpatient")
    items.append(_engagement_item("Z1.5 Engages history/office visit", "newpatient", required=office_visit_exists))

    items.append(ScoreItem("Z1.6 Clicks open X-ray", 1 if xray_step is not None else -2,
                            "Opened the X-ray Viewer form." if xray_step is not None else "Never opened the X-ray Viewer form."))

    # Z1.7: bounded to scroll calls made while still on the X-ray viewer
    # (before xray_left_step) - scroll is a shared tool also used to
    # scroll long pages like the Follow-up Action Selection form's 55
    # checkboxes, so an unbounded "any scroll after xray_step" could be
    # satisfied by a scroll call made much later on that unrelated form -
    # found in grader QA. Real X-ray review plausibly involves multiple
    # zoom/pan actions while staying on the viewer, so this costs nothing
    # for genuinely correct behavior.
    xray_left_step = _left_form_step(page_states, "xray_viewer", xray_step) if xray_step is not None else None
    xray_upper_bound = xray_left_step if xray_left_step is not None else float("inf")
    interacted = xray_step is not None and any(
        e.get("type") == "step" and e.get("tool") == "scroll" and xray_step < e.get("step", 0) < xray_upper_bound
        for e in entries
    )
    items.append(ScoreItem("Z1.7 Interacts with X-ray", 1 if interacted else -0.5,
                            "scroll tool call after opening the X-ray." if interacted else "No scroll/zoom after opening the X-ray."))

    # Same "nothing to engage with" carve-out as Z1.5 - a patient with no
    # prior imaging on file can't be penalized for not comparing to it.
    # Detected the same way every other Z1 checkpoint is: a pattern in the
    # logged URLs, not a live query - the frontend stamps
    # priorStudiesAvailable=0/1 into the URL once it knows, and
    # viewedPriorStudy=1 if the agent ever clicks a timeline entry (see
    # XrayFullScreenViewer.jsx's stampUrlParam). If priorStudiesAvailable
    # never appears at all, the X-ray was never opened far enough to reach
    # this - already penalized once via Z1.6, not double-counted here.
    prior_checked = any("priorStudiesAvailable=" in _all_urls(ps) for ps in page_states)
    prior_available = any("priorStudiesAvailable=1" in _all_urls(ps) for ps in page_states)
    viewed_prior = any("viewedPriorStudy=1" in _all_urls(ps) for ps in page_states)
    if not prior_checked or not prior_available:
        items.append(ScoreItem("Z1.8 Engages prior imaging", 1, "No prior imaging study exists for this patient - not counted against the agent."))
    elif viewed_prior:
        items.append(ScoreItem("Z1.8 Engages prior imaging", 1, "Viewed a prior study via the timeline."))
    else:
        items.append(ScoreItem("Z1.8 Engages prior imaging", -1, "Prior imaging exists for this patient but was never viewed via the timeline."))

    return items, page_states


def score_z2_navigation(page_states: list[dict]) -> ScoreItem:
    """Reaching the real Follow-up Action Selection form - same
    formname=<formdir> URL detection _reached_form_step already uses for
    vitals/xray_viewer, not a new mechanism. (Formerly checked for
    types.php/Configure Orders and Results, before that screen was
    replaced by the real encounter-scoped form - see grade_episode.py's
    module docstring.)"""
    reached = _reached_form_step(page_states, "action_selection") is not None
    return ScoreItem(
        "Z2.9 Navigate to Follow-up Action Selection", 1 if reached else -1,
        "Reached the Follow-up Action Selection form." if reached else "Never reached the Follow-up Action Selection form.",
    )


def score_z2_actions(real_action_ids: list[str]) -> list[ScoreItem]:
    """No longer scores catalog-validity itself (formerly Z2.11, +1/-1 per
    selected action) - an agent hallucinating a nonexistent action is an
    Accuracy-axis concern (A3's hallucinated_by_model), not a Process one.
    real_action_ids comes from ground_truth_selected_action_ids() - real
    procedure_type.procedure_code values read back from the database, so
    (unlike the old free-text level_2 label) every entry is already a
    valid catalog id - no fuzzy matching needed."""
    items = []
    valid_ids = list(real_action_ids)

    # Z2.10: mutual exclusivity - one non-scaling check, not scored per pair
    # (per-pair scoring made this combinatorial: C(n,2) pairs meant a
    # 6-action episode could earn +15 from this single check alone,
    # dwarfing every real penalty in the system). Each of the n selected
    # actions contributes +-1/n instead, so the whole check always sums to
    # within [-1, +1] no matter how many actions were selected.
    n = len(valid_ids)
    if n > 0:
        groups = [_CATALOG.get(a, {}).get("group") for a in valid_ids]
        conflicted = [False] * n
        for i in range(n):
            for j in range(i + 1, n):
                if groups[i] and groups[i] == groups[j]:
                    conflicted[i] = conflicted[j] = True
        per_action = 1.0 / n
        points = round(sum(per_action if not c else -per_action for c in conflicted), 3)
        n_conflicted = sum(conflicted)
        items.append(ScoreItem("Z2.10 No mutual exclusivity conflicts", points,
                                f"{n - n_conflicted}/{n} action(s) conflict-free."))

    # Z2.12 ("too many/too few actions", -5/missing, -0.25/extra) removed -
    # it was scoring the exact same underlying fact as A3 on the Accuracy
    # axis (each missing gold action is independently a missed_by_model
    # item there, each extra one a hallucinated_by_model item), just from
    # the Process side instead of the judged-output side. Process and
    # Accuracy are supposed to be two independent reward channels, but for
    # this one fact they weren't - a missing action cost -5 on BOTH axes
    # for the identical miss, giving action-set correctness roughly double
    # the leverage of any single clinical-judgment error and making it
    # possible to pass an episode on action selection alone even with
    # every finding/impression missed. Process still catches genuine
    # EXECUTION failures independently: Z2.9 (never reached Configure
    # Orders and Results at all) and Z2.11 below (abstained when gold
    # expected real action(s), or vice versa) - what's gone is the
    # redundant per-action identity/count re-check that duplicated A3.

    return items, valid_ids


def score_z2_abstention(valid_ids: list[str], gold_action_ids: list[str]) -> ScoreItem:
    gold_says_abstain = len(gold_action_ids) == 0 or any(a in ABSTAIN_ACTION_IDS for a in gold_action_ids)
    model_abstained = len(valid_ids) == 0 or any(a in ABSTAIN_ACTION_IDS for a in valid_ids)

    if gold_says_abstain and model_abstained:
        return ScoreItem("Z2.11 Abstention calibration", 1, "Gold expected abstention, agent abstained.")
    if not gold_says_abstain and model_abstained:
        return ScoreItem("Z2.11 Abstention calibration", -2, "Gold expected real action(s), agent abstained instead.")
    if gold_says_abstain and not model_abstained:
        # Was +0.25 - positive credit for the wrong move (acting when gold
        # expected abstention). judge.py's equivalent case
        # (abstention_calibration, "gold expected abstention but the model
        # still recommended something") scores this -0.5; Process and
        # Accuracy shouldn't disagree on which direction this behavior
        # points. This branch is unreachable against the 4 shipped golds
        # (none currently expects abstention) but was a live sign bug -
        # found in grader QA.
        return ScoreItem("Z2.11 Abstention calibration", -0.5, "Gold expected abstention, agent acted anyway.")
    return ScoreItem("Z2.11 Abstention calibration", 1, "Gold expected real action(s), agent acted.")


STEP_EFFICIENCY_FIXED_OVERHEAD = 15
# 1 X-ray interaction (zoom/pan) + 1 click to open the X-ray Viewer form +
# 2 type login credentials (username, password) + 1 submit login + 1
# find/reach the correct patient + 1 find/reach the correct encounter + 1
# engage vitals +
# 1 engage history + 1 navigate to a note form + 1 type documentation +
# 1 click Save + 1 open "Add Form: Follow-up Action Selection" + 1 click
# Save on that form + 1 finish = 15. Interaction with the X-ray is treated
# as a required step, not optional - per explicit user decision, since a
# real clinical read requires actually inspecting the image, not just
# glancing at the default view. This is a transparent, fixed floor - not a
# claim about the exact optimal click path (that depends on OpenEMR's UI
# in ways not verifiable from the log alone) - plus one checkbox click per
# gold action for this visit (minimum 1, even for an abstention decision).
# (Formerly "navigate to Procedures + navigate to Configuration", before
# Configure Orders and Results was replaced by the real form.)

STEP_EFFICIENCY_INTERACTION_BUFFER = 2
# Extra allowance on top of the 1 required interaction step, since a real
# read of the X-ray plausibly needs more than one zoom/pan (e.g. checking
# multiple regions) - this buffer absorbs that without penalizing
# reasonable additional interaction as "wasted steps."


def _episode_fully_completed(process_items: list[ScoreItem], action_count_matches: bool) -> bool:
    """'Completed fully end to end, without skipping anything' - stricter
    than a positive Z1/Z2 point total (which can stay positive even with a
    real gap, e.g. several correct action selections offsetting one bad
    one). Every checkpoint below must have cleanly passed. action_count_matches
    is passed in directly (not re-derived from a Z2.12 ScoreItem, which no
    longer exists) - it only gates the step-efficiency BONUS below, it does
    not itself apply any penalty, so this isn't a re-introduction of the
    double-counting Z2.12 was removed for."""
    by_step: dict[str, list[float]] = {}
    for item in process_items:
        by_step.setdefault(item.step, []).append(item.points)

    def _all_positive(step_name: str) -> bool:
        return step_name in by_step and all(p > 0 for p in by_step[step_name])

    required_clean = [
        "Z1.2 Correct patient", "Z1.3 Correct encounter",
        "Z1.4 Engages vitals", "Z1.5 Engages history/office visit",
        "Z1.6 Clicks open X-ray", "Z1.7 Interacts with X-ray",
        "Z1.8 Engages prior imaging",
        "Z2.9 Navigate to Follow-up Action Selection",
    ]
    if not all(_all_positive(s) for s in required_clean):
        return False
    if any(p < 0 for p in by_step.get("Z2.10 No mutual exclusivity conflicts", [])):
        return False
    if not action_count_matches:
        return False
    doc_points = by_step.get("Z2.14 Documentation actually saved", [])
    if not doc_points or doc_points[0] != 1:
        return False
    return True


def score_step_efficiency(entries: list[dict], process_items: list[ScoreItem], gold_action_ids: list[str], valid_ids: list[str]) -> ScoreItem:
    """New check, per explicit user request: reward completing the full
    required workflow in the fewest steps, penalize unnecessary extra
    steps. Full +1 credit only if the episode both (a) completed the
    entire required workflow with no skipped/failed checkpoint (per
    _episode_fully_completed) and (b) took no more than the minimum step
    count.

    Step-count penalty, per explicit user request: a flat -2.0 once the
    episode goes more than 5 steps over the minimum, 0 within that 5-step
    grace window - not a gradual per-step scale. This ScoreItem's step
    name ("Z2.13...") starts with "Z2", so it's included in grade_episode.py's
    z2_total/process_total sum via the normal Z2 aggregation - the penalty
    genuinely docks points from the Process axis, not just from this
    function's own return value.
    """
    actual_steps = len([e for e in entries if e.get("type") == "step"])
    min_actions = max(1, len(gold_action_ids))
    minimum_steps = STEP_EFFICIENCY_FIXED_OVERHEAD + STEP_EFFICIENCY_INTERACTION_BUFFER + min_actions
    extra_steps = max(0, actual_steps - minimum_steps)
    # Flat -2.0 beyond a 5-step grace window (was a linear -0.25/extra-step
    # scale, capped at -2.0 after 8 extra steps) - per explicit user
    # request, replacing gradual scaling with a blanket penalty once the
    # episode is meaningfully inefficient.
    penalty = 0.0 if extra_steps <= 5 else -2.0

    action_count_matches = len(valid_ids) == len(gold_action_ids)
    fully_completed = _episode_fully_completed(process_items, action_count_matches)
    bonus = 1 if (fully_completed and extra_steps == 0) else 0
    points = round(bonus + penalty, 2)

    note = (
        f"{actual_steps} actual step(s) vs. {minimum_steps} minimum "
        f"({STEP_EFFICIENCY_FIXED_OVERHEAD} fixed incl. required X-ray interaction + "
        f"{STEP_EFFICIENCY_INTERACTION_BUFFER} interaction buffer + {min_actions} for "
        f"{len(gold_action_ids)} gold action(s)). "
        f"{'Fully completed' if fully_completed else 'NOT fully completed (skipped/failed a required checkpoint)'}, "
        f"{extra_steps} step(s) over minimum."
    )
    return ScoreItem("Z2.13 Step efficiency", points, note)


def grade_process(log_path: Path, patient_id: str, visit_date: str, gold_action_ids: list[str]) -> list[ScoreItem]:
    entries = load_episode_log(log_path)
    z1_items, page_states = score_z1(entries, patient_id, visit_date)

    z2_nav = score_z2_navigation(page_states)
    real_action_ids = ground_truth_selected_action_ids(patient_id, visit_date)
    z2_actions, valid_ids = score_z2_actions(real_action_ids)
    z2_abstain = score_z2_abstention(valid_ids, gold_action_ids)

    xray_step = _reached_form_step(page_states, "xray_viewer")
    # after_ts scopes the note lookup to THIS episode only - agent_episode.py
    # names each episode dir with its own start time
    # (f"{patient_id}_{visit_date}_{int(time.time())}"), so a rerun against
    # the same patient/visit can never get graded on a prior run's leftover
    # saved note (see grade_episode.py for the full explanation).
    episode_start_ts = int(log_path.parent.name.rsplit("_", 1)[-1])
    saved_notes = read_all_note_forms(patient_id, visit_date, after_ts=episode_start_ts)
    doc_saved_item = score_documentation_saved(entries, saved_notes, xray_step)
    doc_items = [doc_saved_item] if doc_saved_item else []

    all_items = z1_items + [z2_nav] + z2_actions + [z2_abstain] + doc_items
    efficiency_item = score_step_efficiency(entries, all_items, gold_action_ids, valid_ids)

    return all_items + [efficiency_item]


if __name__ == "__main__":
    import sys
    log_path = Path(sys.argv[1])
    patient_id = sys.argv[2]
    visit_date = sys.argv[3]
    gold_ids = sys.argv[4].split(";") if len(sys.argv) > 4 and sys.argv[4] else []

    items = grade_process(log_path, patient_id, visit_date, gold_ids)
    total = sum(i.points for i in items)
    for i in items:
        print(f"  {i.points:+.2f}  {i.step}: {i.note}")
    print(f"\nProcess total: {total:+.2f}")
