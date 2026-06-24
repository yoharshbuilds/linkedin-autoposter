#!/bin/bash
# Run one cycle of the auto-poster. Used by launchd/cron.
set -euo pipefail
cd "$(dirname "$0")"
export PATH="$HOME/.local/bin:$PATH"   # so twitter-cli is reachable
source .venv/bin/activate
python src/main.py >> out/run.log 2>&1
