"""Recheck rehearsal files/ledger/bindings/target identity; no generation."""
import argparse
import hashlib
import json
from pathlib import Path

from fragmentguard.agentpilot.episode import verify_artifacts
from fragmentguard.agentpilot.normalize import check_bindings
from fragmentguard.agentpilot.pilot import load_config


def verify(execution, config_path):
    config = load_config(config_path)
    results = []
    summary = json.loads((execution / 'run_summary.json').read_text())
    for sid in config['raw']['run_order']:
        ep = execution / 'episodes' / sid
        load = lambda name: json.loads((ep / name).read_text())  # noqa: E731
        manifest = load('execution_manifest.json')
        ledger = load('resource_ledger.json')
        records = [json.loads(line) for line in (ep / 'raw_operations.jsonl').read_text().splitlines()]
        stream = load('normalized_stream.json')[0]
        bindings = check_bindings(stream, load('normalization_map.json'), ledger, records)
        plan = json.loads(config['plans'][sid].read_text())
        target = next(c['arguments']['handle'] for c in plan['publisher'] if c.get('tool') == 'publish_resource')
        publication = ledger['publications'][0]
        version = ledger['versions'][publication['version_id']]
        files = verify_artifacts(ep)
        pub_record = next(r for r in records if r['operation'] == 'publish' and r['status'] == 'ok')
        payload_hash = hashlib.sha256((ep / 'workspace' / publication['artifact_path']).read_bytes()).hexdigest()
        result = dict(scenario_id=sid, target_name=target, version_id=version['version_id'],
                      display_name=version['display_name'], producer=version['produced_by_agent'],
                      resolution=pub_record['inputs'][0]['resolved_from'], bindings=bindings, files=files,
                      published_bytes_match_version=payload_hash == version['sha256'],
                      complete=manifest['status'] == 'complete')
        result['ok'] = (result['complete'] and files['ok'] and bindings['agree']
                        and version['display_name'] == target and version['produced_by_agent'] == 'processor'
                        and result['resolution'] == 'display_name' and result['published_bytes_match_version'])
        results.append(result)
    return dict(complete=len(summary['complete']), planned=len(summary['planned']),
                all_ok=all(r['ok'] for r in results), results=results,
                note='Scripted wiring evidence, not live-model instruction compliance.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execution', type=Path, required=True)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.execution, args.config)
    with args.output.open('x') as handle:
        json.dump(result, handle, indent=2)
        handle.write('\n')
    print('all_ok:', result['all_ok'])
    raise SystemExit(0 if result['all_ok'] else 1)
