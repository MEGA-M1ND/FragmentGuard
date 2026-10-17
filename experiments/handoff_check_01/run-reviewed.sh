#!/usr/bin/env bash
# One four-case successor check ONLY after fresh explicit USD 0.35 authorization.
# Never reuse pilot 2's enabled limits or authorization.
set -euo pipefail
: "${AUTHORIZED_LIMITS:?Set to a fresh approved limits file outside tracked source}"
: "${RUN_ROOT:?Set to a fresh run directory}"
cd /workspace/FragmentGuard
source .venv/bin/activate
export XDG_DATA_HOME=/workspace/.fragmentguard/data
export XDG_CACHE_HOME=/workspace/.fragmentguard/cache
export XDG_CONFIG_HOME=/workspace/.fragmentguard/config
python - "$AUTHORIZED_LIMITS" <<'PY'
import hashlib,json,sys
from pathlib import Path
from fragmentguard.agentpilot.backends import Budget,LiveLimits
from fragmentguard.reporting import source_fingerprint
packet=json.loads(Path('experiments/handoff_check_01/review-packet.json').read_text())
if source_fingerprint()['package_sha256']!=packet['package_sha256']:
 raise SystemExit('Reviewed package changed; prepare a new review packet')
for name,digest in packet['input_hashes'].items():
 if hashlib.sha256(Path(name).read_bytes()).hexdigest()!=digest:
  raise SystemExit(f'Reviewed input changed: {name}')
limits=LiveLimits.load(Path(sys.argv[1]))
original=json.loads(Path('experiments/handoff_check_01/limits.proposed.json').read_text())
allowed={'live_enabled','pricing_source','pricing_retrieved_utc','input_usd_per_million_tokens','output_usd_per_million_tokens','notes'}
if any(limits.to_dict()[k]!=v for k,v in original.items() if k not in allowed):
 raise SystemExit('Run settings/cap changed; new review required')
if Budget(limits).pessimistic_run_max_usd(4)>0.35:
 raise SystemExit('Current-price ceiling exceeds USD 0.35')
PY
sha256sum "$AUTHORIZED_LIMITS"
fragmentguard agent-run --backend live --model anthropic/claude-haiku-5-5 --limits "$AUTHORIZED_LIMITS" --scenario experiments/agent_pilot_02/scenarios/sc11.json --preflight-only
test -z "$(git status --porcelain --untracked-files=no)"
fragmentguard pilot-freeze --backend live --config /workspace/FragmentGuard/experiments/handoff_check_01/pilot_config.json --limits "$AUTHORIZED_LIMITS" --output "$RUN_ROOT/freeze"
fragmentguard pilot-run --freeze "$RUN_ROOT/freeze/freeze.json" --limits "$AUTHORIZED_LIMITS" --output "$RUN_ROOT/run"
for mode in direct scout; do
 fragmentguard demo --mode "$mode" --streams "$RUN_ROOT/run/dataset/streams.json" --policy "$RUN_ROOT/run/dataset/policy.json" --provenance "$RUN_ROOT/run/dataset/provenance.json" --budget 3 --horizon 100 --gate none --output "$RUN_ROOT/$mode"
done
fragmentguard pilot-analyze --direct "$RUN_ROOT/direct" --scout "$RUN_ROOT/scout" --labels "$RUN_ROOT/run/evaluator/labels.json" --execution "$RUN_ROOT/run" --output "$RUN_ROOT/analysis"
python - "$RUN_ROOT" <<'PY'
import json,sys
from pathlib import Path
root=Path(sys.argv[1]).resolve()
spec={'datasets':[dict(name='handoff-check-01',kind='live',streams=str(root/'run/dataset/streams.json'),policy=str(root/'run/dataset/policy.json'),labels=str(root/'run/evaluator/labels.json'),execution=str(root/'run'),pairs='/workspace/FragmentGuard/experiments/handoff_check_01/evaluator_pairs.json')]}
with (root/'comparison.json').open('x') as f:json.dump(spec,f,indent=2)
PY
python -m fragmentguard.experiments compare --config "$RUN_ROOT/comparison.json" --output "$RUN_ROOT/comparison"
