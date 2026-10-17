"""The proposed live check is four former failures, not another twelve-case run."""

import json
import unittest
from pathlib import Path

from fragmentguard.agentpilot.backends import Budget, LiveLimits, LiveNotAuthorized
from fragmentguard.agentpilot.pilot import load_config

ROOT = Path(__file__).resolve().parents[1]


class HandoffCheckScope(unittest.TestCase):
    def test_four_case_scope_unchanged_inputs_and_disabled_new_limits(self):
        path = ROOT / "experiments/handoff_check_01/pilot_config.json"
        config = load_config(path)
        original = load_config(ROOT / "experiments/agent_pilot_02/pilot_config.json")
        self.assertEqual(config["raw"]["run_order"], ["sc11", "sc04", "sc09", "sc05"])
        self.assertEqual(config["raw"]["development_scenarios"], [])
        for sid in config["raw"]["pilot_scenarios"]:
            self.assertEqual(config["scenarios"][sid].resolve(), original["scenarios"][sid].resolve())
            self.assertEqual(config["plans"][sid].resolve(), original["plans"][sid].resolve())
        pairs = json.loads(config["pairs"].read_text())["pairs"]
        self.assertEqual({p["pair"] for p in pairs}, {"pair-b", "pair-f"})
        proposed = json.loads((path.parent / "limits.proposed.json").read_text())
        limits = LiveLimits(**proposed)
        with self.assertRaises(LiveNotAuthorized):
            limits.validate()
        self.assertEqual(limits.max_total_requests, 84)
        self.assertEqual(limits.max_spend_usd, 0.35)
        self.assertLessEqual(Budget(limits).pessimistic_run_max_usd(4), 0.35)
