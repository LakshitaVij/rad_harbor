"""
run_grading.py

Verifier entrypoint: finds the episode written under
/logs/artifacts/recorder_episodes/ - pulled from the `recorder` service,
NOT from /solution/episodes (which comes from `main`, the agent's own
container, and is kept around only for human debugging - screenshots
live there). Runs the full grade_episode() pipeline (Process axis via
grade_process.py + Accuracy axis via judge.py) against it, and writes
Harbor's reward file plus a copy of the human-readable receipt into
/logs/verifier/.
"""

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from grade_episode import grade_episode  # noqa: E402

# recorder.py only ever appends events under a POST - `main` (the agent)
# has network access to add new events there, never filesystem access to
# edit or delete ones already written. This is what actually makes
# log.jsonl trustworthy - not the prefix-matching below, which is just a
# secondary sanity check.
EPISODES_DIR = Path("/logs/artifacts/recorder_episodes")
LOGS_DIR = Path("/logs/verifier")

# Matches solution/solve.sh's hardcoded --patient-id/--visit-date for this
# task - agent_episode.py always names its episode dir
# "<patient_id>_<visit_date>_<timestamp>". Grading only trusts an episode
# dir whose name actually starts with this prefix, instead of blindly
# picking whichever dir under EPISODES_DIR happens to have the newest
# mtime.
PATIENT_ID = "GRDN004RP5BFHE0T"
VISIT_DATE = "2009-05-28"


def find_episode() -> Path | None:
    if not EPISODES_DIR.is_dir():
        return None
    prefix = f"{PATIENT_ID}_{VISIT_DATE}_"
    candidates = [
        d for d in EPISODES_DIR.iterdir()
        if d.is_dir() and d.name.startswith(prefix) and (d / "log.jsonl").exists()
    ]
    if not candidates:
        return None
    if len(candidates) > 1:
        names = ", ".join(sorted(d.name for d in candidates))
        raise RuntimeError(
            f"Found {len(candidates)} candidate episode dirs matching prefix "
            f"'{prefix}' ({names}) - refusing to guess which is real. "
            "Only one completed episode is expected per grading run."
        )
    return candidates[0]


def main() -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    try:
        episode_dir = find_episode()
    except RuntimeError as e:
        print(str(e))
        (LOGS_DIR / "reward.json").write_text(json.dumps({"reward": 0.0}))
        return

    if episode_dir is None:
        print(f"No completed episode found under /solution/episodes/ matching {PATIENT_ID}_{VISIT_DATE}_* - agent_episode.py did not run or produced no log.")
        (LOGS_DIR / "reward.json").write_text(json.dumps({"reward": 0.0}))
        return

    print(f"Grading episode: {episode_dir}")
    result = grade_episode(episode_dir)
    totals = result["totals"]

    for label, value in totals.items():
        print(f"{label}: {value}")

    # totals only has the '%'-formatted string version of the Final Grade
    # (isinstance filter below drops it), so pull the real number straight
    # from result instead - the actual bug this fixes: reward.json used to
    # get no "reward" key at all on a successful grading run, only on the
    # failure paths above (which explicitly write {"reward": 0.0}).
    reward_payload = {k: v for k, v in totals.items() if isinstance(v, (int, float))}
    if result.get("final_grade_pct") is not None:
        reward_payload["reward"] = result["final_grade_pct"]
    (LOGS_DIR / "reward.json").write_text(json.dumps(reward_payload, indent=2))

    shutil.copy(result["csv_path"], LOGS_DIR / "receipt.csv")
    shutil.copy(result["json_path"], LOGS_DIR / "receipt.json")
    print(f"\nReward written to {LOGS_DIR / 'reward.json'}")


if __name__ == "__main__":
    main()
