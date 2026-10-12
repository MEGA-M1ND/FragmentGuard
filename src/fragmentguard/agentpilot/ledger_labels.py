"""Ledger-based expected outcomes for completed episodes (evaluator-only).

This is a separate implementation of the same toy policy, applied to the
canonical version ledger rather than to FragmentGuard's normalized events. It
follows the exact versions the final publication consumed back to immutable
catalog roots and applies the audience rule:

- internal audience -> clear;
- public audience with any restricted root -> alert;
- public audience whose roots are all public -> clear;
- anything else (a root missing from the catalog) -> unknown.

It deliberately imports nothing from FragmentGuard's selection or checker, so it
cannot borrow their verdicts. It is not independent real-world validation, and
no human has reviewed these labels unless a report says so.
"""

from __future__ import annotations

from typing import Any


def label_publication(ledger: dict[str, Any], catalog: dict[str, str]) -> dict[str, Any]:
    publications = ledger["publications"]
    if len(publications) != 1:
        raise ValueError("Labels are defined only for episodes with exactly one publication")
    publication = publications[0]
    versions = ledger["versions"]
    trail = [f"{publication['publication_id']} ({publication['audience']}) published {publication['version_id']} "
             f"at seq {publication['seq']}"]
    roots: dict[str, str | None] = {}
    seen: set[str] = set()
    stack = [publication["version_id"]]
    while stack:
        version_id = stack.pop()
        if version_id in seen:
            continue
        seen.add(version_id)
        entry = versions[version_id]
        if entry["kind"] == "root":
            roots[version_id] = catalog.get(version_id)
            trail.append(f"{version_id} is a catalog root classified {roots[version_id]}")
            continue
        trail.append(f"{version_id} ({entry['display_name'] or 'unnamed'}) = {entry['operation']}"
                     f"({', '.join(entry['inputs'])}) by {entry['produced_by_agent']} "
                     f"at seq {entry['produced_by_seq']}")
        stack.extend(reversed(entry["inputs"]))
    if publication["audience"] == "internal":
        verdict = "clear"
    elif any(value == "restricted" for value in roots.values()):
        verdict = "alert"
    elif roots and all(value == "public" for value in roots.values()):
        verdict = "clear"
    else:
        verdict = "unknown"
    return {"verdict": verdict, "audience": publication["audience"], "publication_seq": publication["seq"],
            "roots": roots, "evidence_trail": trail}
