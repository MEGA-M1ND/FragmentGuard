"""Preserved bytes: original fixtures, the imported prototype, and committed run artifacts."""

import json
import unittest
from pathlib import Path

from fragmentguard.reporting import sha256_file
from fragmentguard.schema import FIXTURE_DIR

ROOT = Path(__file__).resolve().parent.parent
HISTORICAL = ROOT / "examples" / "historical_prototype"
# SHA-256 of the fixtures as first imported; they must never change.
ORIGINAL_FIXTURES = {
    "streams.json": "d85b3e341f078f73b5ad80b1d17c15164cb6e59bc7b90e0b7e73d709c6ac2520",
    "policy.json": "882c757afd574c7933f9a489886380c6f436e52677cc8d3bd571f2edfd0f34eb",
    "ground_truth.json": "0837ca672ac64148ef1d27ef0abd15c02fb6ecdbec6fc773189c385f6f5429e2",
}


class PreservationTests(unittest.TestCase):
    def test_bundled_fixtures_keep_their_original_bytes(self):
        for name, digest in ORIGINAL_FIXTURES.items():
            self.assertEqual(sha256_file(FIXTURE_DIR / name), digest, name)
            self.assertEqual(sha256_file(HISTORICAL / "fixtures" / name), digest, name)

    def test_historical_prototype_matches_its_own_manifest(self):
        manifest = json.loads((HISTORICAL / "ARTIFACT_MANIFEST.json").read_text())
        self.assertEqual(len(manifest["files"]), 28)
        for relative, digest in manifest["files"].items():
            self.assertEqual(sha256_file(HISTORICAL / relative), digest, relative)

    def test_committed_run_artifacts_match_their_manifests(self):
        manifests = sorted((ROOT / "examples").rglob("manifest.json"))
        self.assertGreaterEqual(len(manifests), 2)
        for path in manifests:
            manifest = json.loads(path.read_text())
            self.assertEqual(manifest["completion"]["status"], "complete", path)
            for relative, digest in manifest["artifacts"].items():
                self.assertEqual(sha256_file(path.parent / relative), digest, f"{path.parent}/{relative}")


if __name__ == "__main__":
    unittest.main()
