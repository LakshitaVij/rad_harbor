#!/bin/bash
set -euo pipefail

# The clinical subject under test is fixed (Gemini 3.1 Pro via OpenRouter,
# hardcoded in agent_episode.py) - this task packages that existing,
# working computer-use episode into Harbor, it does not let Harbor's -a
# agent selection drive the browser itself. See agent_episode.py's own
# docstring for why.
python /solution/agent_episode.py \
    --patient-id GRDN00BE97VCHW4E \
    --visit-date 2025-01-05
