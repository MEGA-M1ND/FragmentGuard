"""Serialization, provenance and evaluator-only summaries for offline experiments."""

import hashlib
import json
from collections import Counter
from pathlib import Path

from .evaluate import METHODS


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def resolved(spec_path):
    spec = read(spec_path)
    return [{**d, **{key: spec_path.parent / d[key] for key in
                    ("streams", "policy", "labels", "execution", "pairs") if key in d}}
            for d in spec["datasets"]]


def counts(rows):
    result = {}
    for method in METHODS:
        selected = [r for r in rows if r["method"] == method]
        c = Counter(r["status"] for r in selected)
        result[method] = {"publications": len(selected), "verdicts": dict(c),
                          "correct": sum(r["status"] == r["reference"] for r in selected),
                          "insufficient_evidence": c["insufficient_evidence"],
                          "wrong_clear": sum(r["status"] == "clear" and r["reference"] == "alert" for r in selected),
                          "wrong_alert": sum(r["status"] == "alert" and r["reference"] == "clear" for r in selected),
                          "definitive": c["clear"] + c["alert"]}
    return result


