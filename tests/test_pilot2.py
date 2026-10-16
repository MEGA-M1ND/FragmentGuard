"""Pilot 2 changes only the four ambiguous publisher instructions."""

import copy
import json
import unittest
from pathlib import Path

from fragmentguard.agentpilot.pilot import load_config

ROOT = Path(__file__).resolve().parents[1]


class Pilot2Inputs(unittest.TestCase):
    def test_minimal_symmetric_revision(self):
        first = load_config(ROOT / "experiments/agent_pilot/pilot_config.json")
        second = load_config(ROOT / "experiments/agent_pilot_02/pilot_config.json")
        changes = {"sc04": "report", "sc09": "report", "sc05": "summary", "sc11": "summary"}
        for sid, path in first["scenarios"].items():
            original = json.loads(path.read_text())
            revised = json.loads(second["scenarios"][sid].read_text())
            if sid in changes:
                self.assertIn(f"named {changes[sid]}, created by the processor",
                              revised["agents"]["publisher"]["instruction"])
            comparison = copy.deepcopy(revised)
            comparison["agents"]["publisher"] = original["agents"]["publisher"]
            self.assertEqual(original, comparison)
            if sid not in changes:
                self.assertEqual(path.read_bytes(), second["scenarios"][sid].read_bytes())
        for key in ("sources", "catalog", "pairs"):
            self.assertEqual(first[key].resolve(), second[key].resolve())
        for sid in first["plans"]:
            self.assertEqual(first["plans"][sid].resolve(), second["plans"][sid].resolve())
        for key in ("run_order", "selection", "agent_limits_scripted", "pilot_scenarios"):
            self.assertEqual(first["raw"][key], second["raw"][key])
        limits = json.loads((ROOT / "experiments/agent_pilot_02/limits.proposed.json").read_text())
        self.assertFalse(limits["live_enabled"])
