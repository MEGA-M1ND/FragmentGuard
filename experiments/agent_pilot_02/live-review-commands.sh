#!/usr/bin/env bash
# REVIEW PACKET ONLY. No authorization is supplied by this file.
# Run only AFTER separate approval, official price verification, provider/model
# availability checks without generation, and a clean reviewed commit.
set -euo pipefail
: "${AUTHORIZED_LIMITS:?Set to a NEW approved limits file outside the tracked checkout}"
: "${RUN_ROOT:?Set to a fresh output parent outside tracked source}"
cd /workspace/FragmentGuard
source .venv/bin/activate
export XDG_DATA_HOME=/workspace/.fragmentguard/data
export XDG_CACHE_HOME=/workspace/.fragmentguard/cache
export XDG_CONFIG_HOME=/workspace/.fragmentguard/config
# Authorized copy may differ only in explicitly approved fields; record its hash.
sha256sum "$AUTHORIZED_LIMITS"
fragmentguard agent-run --backend live --model anthropic/claude-haiku-5-5 --limits "$AUTHORIZED_LIMITS" --scenario experiments/agent_pilot_02/scenarios/sc01.json --preflight-only
# Require a clean checkout; pilot-freeze also verifies this.
test -z "$(git status --porcelain --untracked-files=no)"
fragmentguard pilot-freeze --backend live --config /workspace/FragmentGuard/experiments/agent_pilot_02/pilot_config.json --limits "$AUTHORIZED_LIMITS" --output "$RUN_ROOT/freeze"
# ONE paid invocation, all 12 scenarios once, no dev runs, retries or resumes.
fragmentguard pilot-run --freeze "$RUN_ROOT/freeze/freeze.json" --limits "$AUTHORIZED_LIMITS" --output "$RUN_ROOT/run"
for mode in direct scout; do
  fragmentguard demo --mode "$mode" --streams "$RUN_ROOT/run/dataset/streams.json" --policy "$RUN_ROOT/run/dataset/policy.json" --provenance "$RUN_ROOT/run/dataset/provenance.json" --budget 3 --horizon 100 --gate none --output "$RUN_ROOT/$mode"
done
# Construct comparison paths only, without copying evaluator labels into inputs.
python - "$RUN_ROOT" <<'PY'
import json, sys
from pathlib import Path
root = Path(sys.argv[1]).resolve()
spec = {'datasets': [dict(name='pilot-02-live',kind='live',
 streams=str(root/'run/dataset/streams.json'), policy=str(root/'run/dataset/policy.json'),
 labels=str(root/'run/evaluator/labels.json'),execution=str(root/'run'),
 pairs='/workspace/FragmentGuard/experiments/agent_pilot/evaluator/pairs.json')]}
with (root/'comparison.json').open('x') as handle:
 json.dump(spec,handle,indent=2)
PY
python -m fragmentguard.experiments compare --config "$RUN_ROOT/comparison.json" --output "$RUN_ROOT/comparison"
fragmentguard pilot-analyze --direct "$RUN_ROOT/direct" --scout "$RUN_ROOT/scout" --labels "$RUN_ROOT/run/evaluator/labels.json" --execution "$RUN_ROOT/run" --output "$RUN_ROOT/analysis"
