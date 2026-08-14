"""
grade_episode.py

Orchestrates full grading for one agent_episode.py run: Process Axis
(via grade_process.py) + Accuracy Axis (via judge.py, using THIS
episode's own output - not a separate text-generation call). Writes one
combined receipt per episode - every Z1/Z2 step and every A1/A2/A3 scored
item as rows, plus a totals summary.

Findings/impressions grading prefers the real SOAP note (Objective/
Assessment) the agent wrote into OpenEMR using its ordinary click/
type_text tools - a genuine per-patient/per-encounter written artifact,
not just our own tool-call capture (report_findings/report_impression
still exist and are used as a fallback for episodes with no SOAP note).

Every graded episode ALSO gets appended to a single running store
(all_receipts.csv / all_receipts.jsonl, in this directory) - same rows as
the per-episode receipt, plus patient_id/visit_date/episode_dir columns
for traceability, so results across many episodes can be opened/queried
together in one place instead of hunting through each episode's own
folder. The per-episode receipt still gets written too - this is
additive, not a replacement.

This is the "marriage" point: A3 follow-up scoring runs against the real
action_id(s) saved on the Follow-up Action Selection form (read back from
OpenEMR's own database via the verifier.collect hook), matched against
oracle.py's gold_action_ids for the same visit - not self-reported text.

Usage:
    python grade_episode.py episodes/<patient>_<visit>_<timestamp>/
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

# Harbor packaging: judge.py/oracle.py/grade_process.py now live alongside
# this file in tests/lib/ (flattened from the original two-directory split),
# so Python's own "script's own directory is on sys.path" behavior resolves
# these directly - no sys.path manipulation needed.
from grade_process import grade_process, ScoreItem, read_all_note_forms, documentation_typed_after_xray, _reached_form_step, ground_truth_selected_action_ids
from judge import judge, judge_followup, AccuracyJudgement, FollowupJudgement, _action_label
from oracle import _GOLD_INDEX, GoldAnswer

FOLLOWUP_CSV = Path(__file__).resolve().parent.parent / "gold" / "generated_followups_fin.csv"

# Some gold action lists consist entirely of conservative "keep monitoring,
# no acute intervention" actions - clinically indistinguishable from
# abstaining outright. cxr-anchoring-bias-resistance's gold is exactly
# [ACT_STOP_SURVEILLANCE, ACT_OBSERVE] with a recommendation reading "No
# acute chest imaging follow-up is indicated. Continue routine clinical
# observation..." - a genuinely correct "nothing acute needed" response
# was being scored as -2 (Z2.11 abstention calibration, "abstained when
# gold expected real action(s)") plus two -5 A3 misses, ~-12 points, for
# what's arguably the right clinical call. Not a mutual-exclusivity
# concern (Z2.10 already handles conflicting actions) - this is about the
# ABSTENTION-CALIBRATION framing specifically treating a 2-action gold as
# "real work required" when the actions themselves represent doing
# nothing acute.
#
# Deliberately scoped here, not added to grade_process.py's shared
# ABSTAIN_ACTION_IDS - these two IDs could legitimately appear alongside
# genuinely different real actions in some other task's gold, and
# ABSTAIN_ACTION_IDS is checked with an "any of these present" test, which
# would misfire on a mixed selection (e.g. [ACT_OBSERVE, ACT_RAPID_RESPONSE]
# would wrongly register as "abstained" if ACT_OBSERVE were in that set).
# Verified today neither ID appears in any other task's gold, but scoping
# the transform to just this orchestration layer means the shared grader
# logic in grade_process.py/judge.py never has to know about this special
# case at all - zero risk to the other 3 tasks even if that ever changes.
_MONITORING_ONLY_IDS = {"ACT_STOP_SURVEILLANCE", "ACT_OBSERVE"}


def _effective_gold_action_ids(gold_action_ids: list[str]) -> list[str]:
    """Collapses a monitoring-only gold action list to empty (pure
    abstention) before it reaches anything abstention-sensitive - both
    grade_process.py's Z2.11 check and judge.py's follow-up scoring read
    "empty gold_action_ids" as "abstention expected" already, so this is
    the one place that needs to know about the equivalence."""
    if gold_action_ids and all(a in _MONITORING_ONLY_IDS for a in gold_action_ids):
        return []
    return gold_action_ids


def _extract_written_note(saved_notes: dict[str, dict[str, str]]) -> tuple[str, str, str]:
    """The report is one continuous free-text block now (per explicit user
    decision - no more 'Findings:'/'Impression:'/'Follow-up:' labels, no
    more per-field SOAP-style splitting). Every non-empty field across
    whichever real note form(s) the agent used gets concatenated into one
    text, and that SAME full text is handed to all three judges (A1/A2/A3-
    written) - a real radiology report doesn't physically separate
    "findings" from "impression" into different documents either; a reader
    (or a judge) parses out what's relevant to each from context."""
    parts = [
        value for fields in saved_notes.values() for value in fields.values() if value.strip()
    ]
    full_text = "\n\n".join(parts)
    return full_text, full_text, full_text


def _study_time_for(patient_id: str, study_date: str) -> str | None:
    """oracle.py's gold is keyed on (patient_id, study_date, study_time),
    but agent_episode.py only knows (patient_id, visit_date as YYYY-MM-DD)
    - look up the matching StudyTime by PatientID+StudyDate."""
    import csv as _csv
    with FOLLOWUP_CSV.open() as f:
        for row in _csv.DictReader(f):
            if row["PatientID"] == patient_id and row["StudyDate"] == study_date:
                return row["StudyTime"]
    return None


def _lookup_gold(patient_id: str, visit_date: str) -> GoldAnswer | None:
    study_date = visit_date.replace("-", "")  # YYYY-MM-DD -> YYYYMMDD
    study_time = _study_time_for(patient_id, study_date)
    if study_time is None:
        return None
    return _GOLD_INDEX.get((patient_id, study_date, study_time))


def _flatten_findings(findings: list[dict]) -> str:
    lines = []
    for f in findings:
        lines.append(
            f"- {f.get('description', '')} (laterality: {f.get('laterality', '')}, "
            f"severity: {f.get('severity', '')}, location: {f.get('location', '')}, "
            f"confidence: {f.get('confidence', '')}): {f.get('reasoning', '')}"
        )
    return "\n".join(lines)


def _flatten_impression(diagnoses: list[dict]) -> str:
    lines = []
    for d in diagnoses:
        tag = "PRIMARY" if d.get("is_primary") else "secondary"
        lines.append(f"- [{tag}] {d.get('diagnosis', '')} (confidence: {d.get('confidence', '')}): {d.get('reasoning', '')}")
    return "\n".join(lines)


def _load_episode_summary(log_path: Path) -> dict:
    with log_path.open() as f:
        entries = [json.loads(line) for line in f if line.strip()]
    summary = next((e for e in reversed(entries) if e.get("type") == "episode_summary"), None)
    start = next((e for e in entries if e.get("type") == "episode_start"), {})
    if summary is None:
        raise ValueError(f"No episode_summary entry found in {log_path} - episode may not have completed.")
    return {
        "patient_id": start.get("patient_id"),
        "visit_date": start.get("visit_date"),
        "reported_findings": summary.get("reported_findings", []),
        "reported_impression": summary.get("reported_impression", []),
        "entries": entries,
    }


# Process axis bounds are fixed - identical for every episode regardless of
# task complexity - recomputed directly from the actual per-checkpoint
# ranges in grade_process.py (the prior -12.5/12.0 were stale and didn't
# match what the code could actually produce - found in grader QA):
#   Ceiling: Z1 (+1 x8 = +8) + Z2.9 (+1) + Z2.10 (+1) + Z2.11 (+1) +
#     Z2.13 (+1 bonus) + documentation-saved (+1) = 13.0
#   Floor:   Z1 (-8.5) + Z2.9 (-1) + Z2.10 (-1) + Z2.11 (-2, worst real
#     branch) + Z2.13 (-2.0, now CAPPED - see score_step_efficiency) +
#     documentation-saved (-0.25) = -14.75
# Z2.13's step-efficiency penalty used to be uncapped (-0.25/extra step,
# no floor) - the only unbounded component in Process, able on its own to
# swing further negative than the entire rest of the axis combined for a
# slow-but-correct episode, clamping process_norm to 0 regardless of every
# other checkpoint. Capping it at -2.0 in grade_process.py is what makes a
# fixed, bounded PROCESS_FLOOR possible again.
PROCESS_FLOOR, PROCESS_CEILING = -14.75, 13.0

# Per-item ceiling/floor for each Accuracy sub-axis, from judge.py's actual
# point values (worst case here means "still matched, but scored badly on
# every field" - not "the model hallucinated infinite extra items", which
# is unbounded and excluded from this ceiling/floor by design).
_A1_ITEM_BOUNDS = (8.0, -10.0)  # was (7.0, -9.0) before comparison_accuracy was added
_A2_ITEM_BOUNDS = (6.0, -7.5)
_A3_ITEM_BOUNDS = (6.0, -7.0)
_A3_EPISODE_BOUNDS = (2.0, -4.0)  # abstention_calibration + unnecessary_avoidance, ceiling/floor

# Fixed, judge-independent gold item counts for THIS task - hand-counted
# directly from tests/gold/consolidated_real_reports.csv (findings/
# impressions) and generated_followups_fin.csv (actions), not derived from
# any judge call. The previous approach (_n_real() counting whatever the
# live judge happened to segment gold into this run) meant the same model
# output could score differently across repeated grading runs purely from
# judge segmentation noise (the judge is documented elsewhere in this file
# as occasionally inventing phantom items even on empty input) - moving/
# merging one gold item shifts the ceiling/floor, not just the score.
# Found in grader QA.
_GOLD_ITEM_COUNTS = {"a1": 7, "a2": 1, "a3": 6}


def _final_grade(process_total: float, accuracy: AccuracyJudgement, no_real_output: bool) -> float | None:
    """Single 0-100 grade combining Process (30%) and Accuracy (70%). Raw
    point sums can't be weighted directly - Accuracy's scale (tens to
    hundreds of points, scaling with how many real findings/diagnoses/
    actions this visit has) dwarfs Process's fixed small range, so a naive
    0.3*process + 0.7*accuracy wouldn't actually produce a 30/70 split.
    Both axes are normalized to [0,1] against their own ceiling/floor
    first, THEN weighted - so "70% on a 6-action visit" and "70% on a
    2-action visit" represent the same proportional correctness, not
    raw-point parity. Ceiling/floor use fixed gold-side item counts
    (_GOLD_ITEM_COUNTS), not the judge's own per-run segmentation - a model
    can't inflate its own ceiling by hallucinating extra items either way,
    since hallucinations only ever cost points and were never counted here."""
    n_a1 = _GOLD_ITEM_COUNTS["a1"]
    n_a2 = _GOLD_ITEM_COUNTS["a2"]
    a1_ceiling, a1_floor = n_a1 * _A1_ITEM_BOUNDS[0], n_a1 * _A1_ITEM_BOUNDS[1]
    a2_ceiling, a2_floor = n_a2 * _A2_ITEM_BOUNDS[0], n_a2 * _A2_ITEM_BOUNDS[1]
    accuracy_ceiling, accuracy_floor = a1_ceiling + a2_ceiling, a1_floor + a2_floor

    if accuracy.follow_up is not None:
        n_a3 = _GOLD_ITEM_COUNTS["a3"]
        accuracy_ceiling += n_a3 * _A3_ITEM_BOUNDS[0] + _A3_EPISODE_BOUNDS[0]
        accuracy_floor += n_a3 * _A3_ITEM_BOUNDS[1] + _A3_EPISODE_BOUNDS[1]

    if accuracy_ceiling == accuracy_floor:  # no gold items at all - degenerate case
        return None

    # A genuine no-show (the model produced no relevant output at all) looks
    # IDENTICAL, per-item, to "attempted every gold item and missed all of
    # them" - both are 100% missed_by_model rows. But those are different
    # failures: missing an item you tried to address costs -2 (cheaper than
    # a badly-wrong matched item at -9, on purpose - an actively wrong
    # answer should be penalized harder than silence). Left as-is, that
    # means total silence normalizes to ~30-40%, not near 0%, since -2/item
    # sits well above the -9/item floor.
    #
    # This used to be INFERRED from the judge's own output (zero matched AND
    # zero hallucinated items across every axis) - but a real run surfaced
    # the judge occasionally hallucinating 1-2 phantom items even when given
    # completely empty input, which silently defeated that detection (Task
    # 5's connection-error episode: truly zero agent output, but the judge
    # still reported 2 hallucinated_by_model items). Trusting the judge's
    # interpretation of "was there real output" is trusting a second LLM
    # call that can itself be wrong. `no_real_output` is ground truth from
    # the episode log instead - were model_findings/model_impressions/
    # model_follow_up_actions actually empty BEFORE they were ever sent to
    # the judge - so this can't be fooled by judge noise.
    process_norm = (process_total - PROCESS_FLOOR) / (PROCESS_CEILING - PROCESS_FLOOR)
    if no_real_output:
        accuracy_norm = 0.0
    else:
        accuracy_norm = (accuracy.total_score - accuracy_floor) / (accuracy_ceiling - accuracy_floor)
    # Clamp - hallucinated extras can push the real score below the
    # "realistic" floor computed above, since that floor only accounts for
    # gold items scored badly, not unlimited hallucinated ones on top.
    process_norm = max(0.0, min(1.0, process_norm))
    accuracy_norm = max(0.0, min(1.0, accuracy_norm))

    return 100.0 * (0.3 * process_norm + 0.7 * accuracy_norm)


def grade_episode(episode_dir: Path) -> dict:
    log_path = episode_dir / "log.jsonl"
    ep = _load_episode_summary(log_path)
    patient_id, visit_date = ep["patient_id"], ep["visit_date"]

    gold = _lookup_gold(patient_id, visit_date)
    if gold is None:
        raise ValueError(f"No gold found for {patient_id}/{visit_date} - can't grade Accuracy Axis for this visit.")

    effective_gold_action_ids = _effective_gold_action_ids(gold.gold_action_ids)
    process_items = grade_process(log_path, patient_id, visit_date, effective_gold_action_ids)

    # Prefer whatever real note form(s) the agent actually wrote into
    # OpenEMR (genuine per-patient/per-encounter artifacts) over our own
    # tool-call capture for findings/impressions - checks every real note
    # form in the registry, not just SOAP, since the prompt no longer tells
    # it which one to use.
    #
    # episode_start_ts scopes this to notes saved AFTER this specific
    # episode began - agent_episode.py names each episode dir with its own
    # start time (f"{patient_id}_{visit_date}_{int(time.time())}"), so it's
    # already sitting right there in the directory name. Without this, a
    # rerun against the same patient/visit (exactly what happens re-running
    # reference tasks) could get graded on a PRIOR episode's leftover saved
    # note instead of its own - a real bug, found via a real run.
    episode_start_ts = int(episode_dir.name.rsplit("_", 1)[-1])
    saved_notes = read_all_note_forms(patient_id, visit_date, after_ts=episode_start_ts)
    model_findings, model_impressions, model_written_followup = ("", "", "")
    if saved_notes:
        model_findings, model_impressions, model_written_followup = _extract_written_note(saved_notes)

    # Nothing saved (or a save that came back empty) - fall back to
    # whatever the agent actually typed, even though it never got saved.
    # Process still penalizes this (-0.25, "Documentation actually saved"
    # in grade_process.py) - but a correct answer that got lost shouldn't
    # ALSO be graded identically to no answer at all on the Accuracy axis.
    # documentation_typed_after_xray() only grades text typed AFTER the
    # agent opened the X-ray Viewer - login/patient-search/encounter-nav
    # typing all happens earlier, so this can't sweep in a credential or
    # patient ID the way "every type_text call, unfiltered" would. Only
    # falls further back to the old report_findings/report_impression
    # tool-call capture (empty for any episode run after those tools were
    # removed) if nothing was typed post-X-ray at all.
    if not model_findings and not model_impressions and not model_written_followup:
        page_states = [e for e in ep["entries"] if e.get("type") == "page_state"]
        xray_step = _reached_form_step(page_states, "xray_viewer")
        typed = documentation_typed_after_xray(ep["entries"], xray_step)
        model_findings = model_impressions = model_written_followup = typed
        if not typed:
            model_findings = _flatten_findings(ep["reported_findings"])
            model_impressions = _flatten_impression(ep["reported_impression"])

    # A3 is graded TWICE, independently, per explicit user decision:
    # (1) "A3 Follow-up (actions)" - the real "marriage" point: action_id(s)
    #     actually saved on the Follow-up Action Selection form, read back
    #     from OpenEMR's own database via the verifier.collect hook. Can't
    #     be faked by writing about a follow-up without actually saving it -
    #     unlike the old select_action tool, there is no code path that
    #     produces this data without a real save.php POST.
    # (2) "A3 Follow-up (written)" - the agent's actual written Follow-up
    #     note text (if any), graded against the same gold independently.
    #     These two scores are NOT combined into one - kept as separate
    #     axes so a mismatch between what was saved and what was written
    #     stays visible rather than averaged away.
    real_selected_action_ids = ground_truth_selected_action_ids(patient_id, visit_date, after_ts=episode_start_ts)
    model_follow_up_actions = "\n".join(f"- {_action_label(a)}" for a in real_selected_action_ids) or "(no actions selected)"

    accuracy: AccuracyJudgement = judge(
        model_findings=model_findings,
        model_impressions=model_impressions,
        gold_findings=gold.findings,
        gold_impressions=gold.impressions,
        model_follow_up=model_follow_up_actions,
        gold_action_ids=effective_gold_action_ids,
        gold_recommendation=gold.gold_recommendation,
    )

    written_followup_judgement: FollowupJudgement | None = None
    if model_written_followup:
        written_followup_judgement = judge_followup(model_written_followup, effective_gold_action_ids, gold.gold_recommendation)

    rows = []
    for item in process_items:
        rows.append({"axis": "Process", "item": item.step, "component": "", "points": round(item.points, 2), "note": item.note})

    # Non-metric fields on each Pydantic item - everything else is a real
    # scored sub-metric and gets its own row, per explicit request to show
    # every component individually rather than folding into one sum.
    _NON_METRIC_FIELDS = {"finding_description", "diagnosis_description", "action_description", "match_status", "reasoning"}

    def _explode(axis_label: str, item, description: str):
        data = item.model_dump()
        for field, value in data.items():
            if field in _NON_METRIC_FIELDS:
                continue
            rows.append({
                "axis": axis_label, "item": f"[{item.match_status}] {description}",
                "component": field, "points": value, "note": item.reasoning,
            })
        # _match_penalty is a computed @property, not a real Pydantic field -
        # model_dump() above never sees it, so without this it silently
        # vanishes into the TOTAL row with no line item explaining where a
        # missed/hallucinated item's points actually came from.
        rows.append({
            "axis": axis_label, "item": f"[{item.match_status}] {description}",
            "component": "match_status_penalty", "points": round(item._match_penalty, 2), "note": item.reasoning,
        })
        rows.append({
            "axis": axis_label, "item": f"[{item.match_status}] {description}",
            "component": "TOTAL (sum of components above)", "points": round(item.raw_total, 2), "note": item.reasoning,
        })

    def _explode_followup(axis_label: str, fu: FollowupJudgement):
        for item in fu.items:
            _explode(axis_label, item, item.action_description)
        # abstention_calibration and unnecessary_avoidance are episode-level
        # fields on FollowupJudgement itself, not per-item - the generic
        # _explode() loop above never sees them since they're outside
        # fu.items. Give them their own rows so per-checkpoint analysis can
        # see them individually, matching how every other A3 sub-metric
        # gets a row.
        rows.append({"axis": axis_label, "item": "[episode] abstention_calibration",
                     "component": "abstention_calibration", "points": round(fu.abstention_calibration, 2), "note": ""})
        rows.append({"axis": axis_label, "item": "[episode] unnecessary_avoidance",
                     "component": "unnecessary_avoidance", "points": round(fu.unnecessary_avoidance, 2), "note": ""})

    for item in accuracy.findings.items:
        _explode("A1 Findings", item, item.finding_description)
    for item in accuracy.impressions.items:
        _explode("A2 Impressions", item, item.diagnosis_description)
    if accuracy.follow_up:
        _explode_followup("A3 Follow-up (actions)", accuracy.follow_up)
    if written_followup_judgement:
        _explode_followup("A3 Follow-up (written)", written_followup_judgement)

    written_followup_score = (
        sum(i.raw_total for i in written_followup_judgement.items)
        + written_followup_judgement.abstention_calibration
        + written_followup_judgement.unnecessary_avoidance
        if written_followup_judgement else None
    )

    z1_total = sum(i.points for i in process_items if i.step.startswith("Z1"))
    z2_total = sum(i.points for i in process_items if i.step.startswith("Z2"))
    process_total = z1_total + z2_total

    # Ground truth for the no-show case, from what was actually sent to the
    # judge - not inferred from the judge's own (occasionally noisy) output.
    no_real_output = not (model_findings.strip() or model_impressions.strip() or model_follow_up_actions.strip())
    final_grade_pct = _final_grade(process_total, accuracy, no_real_output)

    totals = {
        "Z1 (Information-Gathering) total": round(z1_total, 2),
        "Z2 (Action-Execution) total": round(z2_total, 2),
        "Process total (Z1+Z2)": round(process_total, 2),
        "A1 (Findings) total": round(accuracy.a1_score, 2),
        "A2 (Impressions) total": round(accuracy.a2_score, 2),
        "A3 (Follow-up - actions) total": round(accuracy.a3_score, 2) if accuracy.a3_score is not None else "",
        "A3 (Follow-up - written) total": round(written_followup_score, 2) if written_followup_score is not None else "",
        "Accuracy total (A1+A2+A3-actions)": round(accuracy.total_score, 2),
        "Final Grade (30% Process / 70% Accuracy)": f"{final_grade_pct:.1f}%" if final_grade_pct is not None else "",
    }
    for label, value in totals.items():
        rows.append({"axis": "TOTAL", "item": label, "component": "", "points": value, "note": ""})

    csv_path = episode_dir / "receipt.csv"
    with csv_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["axis", "item", "component", "points", "note"])
        writer.writeheader()
        writer.writerows(rows)

    json_path = episode_dir / "receipt.json"
    with json_path.open("w") as f:
        json.dump({"patient_id": patient_id, "visit_date": visit_date, "rows": rows, "totals": totals}, f, indent=2)

    _append_to_combined_store(patient_id, visit_date, episode_dir.name, rows)

    return {"rows": rows, "totals": totals, "csv_path": csv_path, "json_path": json_path, "final_grade_pct": final_grade_pct}


ALL_RECEIPTS_CSV = Path(__file__).resolve().parent / "all_receipts.csv"
ALL_RECEIPTS_JSONL = Path(__file__).resolve().parent / "all_receipts.jsonl"
_ALL_RECEIPTS_FIELDS = ["patient_id", "visit_date", "episode_dir", "axis", "item", "component", "points", "note"]


def _append_to_combined_store(patient_id: str, visit_date: str, episode_dir_name: str, rows: list[dict]) -> None:
    """Appends this episode's rows to the running cross-episode store -
    additive, never overwrites, so results across many episodes/runs
    accumulate in one place rather than being scattered one-per-folder."""
    write_header = not ALL_RECEIPTS_CSV.exists()
    with ALL_RECEIPTS_CSV.open("a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_ALL_RECEIPTS_FIELDS)
        if write_header:
            writer.writeheader()
        for row in rows:
            writer.writerow({"patient_id": patient_id, "visit_date": visit_date, "episode_dir": episode_dir_name, **row})

    with ALL_RECEIPTS_JSONL.open("a") as f:
        for row in rows:
            f.write(json.dumps({"patient_id": patient_id, "visit_date": visit_date, "episode_dir": episode_dir_name, **row}) + "\n")


if __name__ == "__main__":
    # Trust boundary, documented not fixed here: everything in log.jsonl
    # (Z1/Z2 step timing, URLs, typed text) is taken on faith as coming
    # from a real Harbor-launched episode against a real agent container -
    # this file has no way to verify that itself. What CAN'T be forged
    # this way is A3's action selection and the note-content axes (A1/A2),
    # since those are cross-checked against real database rows via the
    # verifier.collect hook, not read from this file - see
    # ground_truth_selected_action_ids()/read_all_note_forms() in
    # grade_process.py. A genuine fix for the log itself would need a
    # guarantee from Harbor's own container/artifact boundary, not
    # anything achievable from inside this grading script - flagged in
    # grader QA, deliberately left as a known limitation rather than
    # papered over.
    episode_dir = Path(sys.argv[1])
    result = grade_episode(episode_dir)
    for row in result["rows"]:
        comp = f" :: {row['component']}" if row.get("component") else ""
        points_display = f"{row['points']:+.2f}" if isinstance(row["points"], (int, float)) else str(row["points"])
        print(f"  {points_display}  [{row['axis']}] {row['item']}{comp}")
    print()
    for label, value in result["totals"].items():
        print(f"{label}: {value}")
    print(f"\nReceipt written to {result['csv_path']} and {result['json_path']}")
