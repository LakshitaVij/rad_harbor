"""
run_grading.py

Verifier entrypoint: finds the episode agent_episode.py just wrote under
/solution/episodes/, runs the full grade_episode() pipeline (Process axis
via grade_process.py + Accuracy axis via judge.py) against it, and writes
Harbor's reward file plus a copy of the human-readable receipt into
/logs/verifier/.
"""

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from grade_episode import grade_episode  # noqa: E402

EPISODES_DIR = Path("/solution/episodes")
LOGS_DIR = Path("/logs/verifier")

# Matches solution/solve.sh's hardcoded --patient-id/--visit-date for this
# task - agent_episode.py always names its episode dir
# "<patient_id>_<visit_date>_<timestamp>". Grading only trusts an episode
# dir whose name actually starts with this prefix, instead of blindly
# picking whichever dir under /solution/episodes/ (an agent-writable
# directory) happens to have the newest mtime - the latter would let a
# fabricated log.jsonl win just by being written last.
PATIENT_ID = "GRDN00A5ZYWHZY7D"
VISIT_DATE = "2012-05-09"


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

    reward_payload = {k: v for k, v in totals.items() if isinstance(v, (int, float))}
    (LOGS_DIR / "reward.json").write_text(json.dumps(reward_payload, indent=2))

    shutil.copy(result["csv_path"], LOGS_DIR / "receipt.csv")
    shutil.copy(result["json_path"], LOGS_DIR / "receipt.json")
    print(f"\nReward written to {LOGS_DIR / 'reward.json'}")


if __name__ == "__main__":
    main()
