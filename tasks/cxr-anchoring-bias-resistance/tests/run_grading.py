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


def find_latest_episode() -> Path | None:
    if not EPISODES_DIR.is_dir():
        return None
    candidates = [d for d in EPISODES_DIR.iterdir() if d.is_dir() and (d / "log.jsonl").exists()]
    if not candidates:
        return None
    return max(candidates, key=lambda d: d.stat().st_mtime)


def main() -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    episode_dir = find_latest_episode()
    if episode_dir is None:
        print("No completed episode found under /solution/episodes/ - agent_episode.py did not run or produced no log.")
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
