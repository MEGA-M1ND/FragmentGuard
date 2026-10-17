"""Isolated resource workspace, the three agent tools, and the action recorder.

The application is the source of execution facts:

- every tool call is validated, executed, and appended to ``raw_operations.jsonl``
  (flushed and fsynced) *before* success is returned to the agent;
- each successful write creates a new immutable version with an opaque ID,
  even when its display name is reused, and the version ledger records exactly
  which versions it consumed;
- failed operations are recorded too, and have no resource effects;
- if recording (or committing a recorded effect) fails, the episode is marked
  incomplete and stops.

The model chooses which tool to call and with which arguments; the application
computes all content. There is no tool that writes model-supplied content, so a
dependency can only enter through an input the recorder observed.

Policy scope (deliberately conservative): every output inherits restriction
from any input, even if fields were dropped. There is no redaction or
declassification exemption in this milestone.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

NAME = re.compile(r"[a-z][a-z0-9-]{0,31}")
ROOT_ID = re.compile(r"src-[a-z0-9]{2,16}")
VERSION_ID = re.compile(r"v[0-9]{3,}")
FIELD = re.compile(r"[a-z][a-z0-9_]{0,31}")
OPERATIONS = ("copy", "combine", "select_fields", "format_summary")
AUDIENCES = ("internal", "public")
ACTOR_KINDS = ("model", "scripted_backend", "scripted_background")
ROLE_TOOLS = {
    "collector": ("read_resource",),
    "processor": ("read_resource", "transform_resource"),
    "publisher": ("publish_resource",),
    "background": ("read_resource", "transform_resource"),
}

TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "read_resource": {
        "description": (
            "Read a permitted source resource or an existing artifact (by handle or name) and save "
            "an immutable working copy. Returns the new handle and the copy's contents."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "resource_id": {"type": "string", "description": "Source ID, artifact handle, or artifact name"},
                "name": {"type": "string", "description": "Optional display name for the copy (a-z, 0-9, -)"},
            },
            "required": ["resource_id"],
            "additionalProperties": False,
        },
    },
    "transform_resource": {
        "description": (
            "Create a new immutable artifact from existing artifacts using an application-implemented "
            "operation: copy (one input), combine (two or more inputs), select_fields (one input, with "
            "fields), or format_summary (one input). Returns the new handle and contents."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "input_handles": {"type": "array", "items": {"type": "string"},
                                  "description": "Artifact handles or names, in order"},
                "operation": {"type": "string", "enum": list(OPERATIONS)},
                "fields": {"type": "array", "items": {"type": "string"},
                           "description": "Record fields to keep (select_fields only)"},
                "name": {"type": "string", "description": "Optional display name for the result"},
            },
            "required": ["input_handles", "operation"],
            "additionalProperties": False,
        },
    },
    "publish_resource": {
        "description": (
            "Publish one artifact to a simulated local destination: 'internal' or 'public'. Only one "
            "publication is allowed per task. No external upload happens."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "handle": {"type": "string", "description": "Artifact handle or name"},
                "audience": {"type": "string", "enum": list(AUDIENCES)},
            },
            "required": ["handle", "audience"],
            "additionalProperties": False,
        },
    },
}


class ToolError(Exception):
    """An invalid or disallowed operation. It is recorded and has no effects."""


class RecordingError(Exception):
    """The recorder could not durably store an operation."""


class EpisodeAborted(Exception):
    """Recording or committing failed; the episode is incomplete and must stop."""


def canonical(data: Any) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":")).encode()


def sha256_json(data: Any) -> str:
    return hashlib.sha256(canonical(data)).hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Recorder:
    """Append-only JSONL recorder. ``fail_when`` lets tests inject a failure."""

    def __init__(self, path: Path, fail_when: Callable[[dict[str, Any]], bool] | None = None):
        self.path = path
        self.fail_when = fail_when
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=False)

    def append(self, record: dict[str, Any]) -> None:
        if self.fail_when is not None and self.fail_when(record):
            raise RecordingError(f"injected recording failure at seq {record['seq']}")
        line = json.dumps(record, sort_keys=True) + "\n"
        try:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line)
                handle.flush()
                os.fsync(handle.fileno())
        except OSError as error:
            raise RecordingError(str(error)) from error


@dataclass
class Version:
    version_id: str
    display_name: str | None
    kind: str  # "root" or "derived"
    content: dict[str, Any]
    sha256: str
    produced_by_seq: int | None = None
    produced_by_agent: str | None = None
    operation: str | None = None
    inputs: list[str] = field(default_factory=list)

    def ledger_entry(self) -> dict[str, Any]:
        return {
            "version_id": self.version_id, "display_name": self.display_name, "kind": self.kind,
            "sha256": self.sha256, "produced_by_seq": self.produced_by_seq,
            "produced_by_agent": self.produced_by_agent, "operation": self.operation,
            "inputs": list(self.inputs),
        }


class Workspace:
    """One episode's isolated workspace. Catalog roots are immutable."""

    def __init__(
        self, root: Path, episode_id: str, sources: dict[str, dict[str, Any]], permitted_roots: list[str],
        recorder: Recorder, max_publications: int = 1,
    ):
        self.root = root
        self.episode_id = episode_id
        self.recorder = recorder
        self.max_publications = max_publications
        self.versions: dict[str, Version] = {}
        self.names: dict[str, list[str]] = {}
        self.permitted_roots = set(permitted_roots)
        self.publications: list[dict[str, Any]] = []
        self.seq = 0
        self.counter = 0
        self.incomplete_reasons: list[str] = []
        self.destinations = {audience: root / f"{audience}_outputs" for audience in AUDIENCES}
        self.staging = root / ".staging"
        for directory in (*self.destinations.values(), self.staging):
            directory.mkdir(parents=True, exist_ok=False)
        for root_id, content in sources.items():
            if not ROOT_ID.fullmatch(root_id):
                raise ValueError(f"Invalid root identifier {root_id!r} (expected src-...)")
            self.versions[root_id] = Version(root_id, None, "root", content, sha256_json(content))

    # -- resolution and validation ---------------------------------------------------

    def _resolve(self, reference: Any) -> tuple[Version, str]:
        if not isinstance(reference, str) or not reference:
            raise ToolError("References must be nonempty strings")
        if reference in self.versions:
            version = self.versions[reference]
            if version.kind == "root" and reference not in self.permitted_roots:
                raise ToolError(f"Source {reference} is not permitted for this task")
            return version, "root" if version.kind == "root" else "handle"
        if reference in self.names:
            return self.versions[self.names[reference][-1]], "display_name"
        raise ToolError(f"Unknown resource, handle, or name: {reference!r}")

    @staticmethod
    def _name(value: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str) or not NAME.fullmatch(value):
            raise ToolError("Names must match [a-z][a-z0-9-]{0,31}")
        if ROOT_ID.fullmatch(value) or VERSION_ID.fullmatch(value):
            raise ToolError("Names must not look like a source ID (src-...) or a handle (v001)")
        return value

    def _new_version_id(self) -> str:
        self.counter += 1
        return f"v{self.counter:03d}"

    # -- the three tools --------------------------------------------------------------

    def _plan(self, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        """Validate and compute an operation without applying any effect."""
        if not isinstance(args, dict):
            raise ToolError("Arguments must be an object")
        allowed = set(TOOL_SCHEMAS[tool]["parameters"]["properties"]) if tool in TOOL_SCHEMAS else set()
        if tool not in TOOL_SCHEMAS:
            raise ToolError(f"Unknown tool {tool!r}")
        unknown = set(args) - allowed
        if unknown:
            raise ToolError(f"Unexpected arguments: {sorted(unknown)}")
        if tool == "read_resource":
            source, how = self._resolve(args.get("resource_id"))
            return {"operation": "read", "inputs": [(source, how)], "content": json.loads(canonical(source.content)),
                    "name": self._name(args.get("name"))}
        if tool == "transform_resource":
            handles = args.get("input_handles")
            if not isinstance(handles, list) or not handles:
                raise ToolError("input_handles must be a nonempty list")
            inputs = [self._resolve(handle) for handle in handles]
            if len({version.version_id for version, _ in inputs}) != len(inputs):
                raise ToolError("input_handles must not repeat a version")
            operation = args.get("operation")
            content = self._transform(operation, [version.content for version, _ in inputs], args.get("fields"))
            return {"operation": operation, "inputs": inputs, "content": content, "name": self._name(args.get("name"))}
        # publish_resource
        if len(self.publications) >= self.max_publications:
            raise ToolError("This task allows only one publication, and it has already happened")
        audience = args.get("audience")
        if audience not in AUDIENCES:
            raise ToolError(f"audience must be one of {AUDIENCES}")
        version, how = self._resolve(args.get("handle"))
        if version.kind == "root":
            raise ToolError("Publish an artifact you created, not a source resource")
        return {"operation": "publish", "inputs": [(version, how)], "content": version.content, "audience": audience}

    @staticmethod
    def _transform(operation: Any, contents: list[dict[str, Any]], fields: Any) -> dict[str, Any]:
        if operation not in OPERATIONS:
            raise ToolError(f"operation must be one of {OPERATIONS}")
        if operation == "combine":
            if len(contents) < 2:
                raise ToolError("combine needs two or more inputs")
            return {"records": [r for c in contents for r in c.get("records", [])],
                    "lines": [line for c in contents for line in c.get("lines", [])]}
        if len(contents) != 1:
            raise ToolError(f"{operation} takes exactly one input")
        content = contents[0]
        if operation == "copy":
            return json.loads(canonical(content))
        if operation == "select_fields":
            if not isinstance(fields, list) or not fields or not all(
                    isinstance(f, str) and FIELD.fullmatch(f) for f in fields):
                raise ToolError("select_fields needs a nonempty list of field names")
            records = content.get("records")
            if not records:
                raise ToolError("select_fields needs an input with records")
            missing = sorted({f for f in fields if not all(f in record for record in records)})
            if missing:
                raise ToolError(f"Unknown fields for these records: {missing}")
            return {"records": [{f: record[f] for f in fields} for record in records], "lines": []}
        # format_summary
        lines = list(content.get("lines", []))
        lines += ["; ".join(f"{key}={record[key]}" for key in sorted(record)) for record in content.get("records", [])]
        return {"records": [], "lines": lines}

    def execute(self, agent_id: str, actor_kind: str, tool: str, args: Any) -> dict[str, Any]:
        """Run one tool call. Returns the result shown to the agent."""
        if actor_kind not in ACTOR_KINDS:
            raise ValueError(f"Unknown actor kind {actor_kind!r}")
        if self.incomplete_reasons:
            raise EpisodeAborted("; ".join(self.incomplete_reasons))
        self.seq += 1
        record: dict[str, Any] = {
            "episode_id": self.episode_id, "seq": self.seq, "utc": utc_now(), "agent_id": agent_id,
            "actor_kind": actor_kind, "tool": tool, "arguments": args,
        }
        if tool not in ROLE_TOOLS.get(agent_id, ()):
            return self._record_error(record, ToolError(f"{agent_id} may not call {tool}"))
        try:
            plan = self._plan(tool, args)
        except ToolError as error:
            return self._record_error(record, error)

        inputs = [{"version_id": v.version_id, "resolved_from": how, "sha256": v.sha256} for v, how in plan["inputs"]]
        record.update(status="ok", operation=plan["operation"], inputs=inputs)
        staged = None
        if plan["operation"] == "publish":
            publication_id = f"pub{len(self.publications) + 1:02d}"
            data = canonical(plan["content"])
            staged = self.staging / f"{publication_id}.json"
            staged.write_bytes(data)
            final = self.destinations[plan["audience"]] / f"{publication_id}.json"
            record.update(audience=plan["audience"], publication_id=publication_id,
                          artifact_path=final.relative_to(self.root).as_posix(),
                          artifact_sha256=hashlib.sha256(data).hexdigest())
        else:
            version_id = self._new_version_id()
            record.update(output_version=version_id, output_name=plan["name"],
                          output_sha256=sha256_json(plan["content"]))
        try:
            self.recorder.append(record)  # Durable before any effect or acknowledgement.
        except RecordingError as error:
            if staged is not None:
                staged.unlink(missing_ok=True)
            self.incomplete_reasons.append(f"recording failed at seq {self.seq}: {error}")
            raise EpisodeAborted(self.incomplete_reasons[-1]) from error
        try:
            return self._commit(agent_id, record, plan, staged)
        except Exception as error:  # noqa: BLE001 - recorded op whose effect did not land
            self.incomplete_reasons.append(f"commit failed after recording seq {self.seq}: {error}")
            try:
                self.recorder.append({"episode_id": self.episode_id, "seq": self.seq, "utc": utc_now(),
                                      "status": "commit_failed", "error": str(error)})
            except RecordingError:
                pass
            raise EpisodeAborted(self.incomplete_reasons[-1]) from error

    def reject(self, agent_id: str, actor_kind: str, tool: str, args: Any, reason: str) -> dict[str, Any]:
        """Record a call refused before execution (e.g. unparseable arguments)."""
        if self.incomplete_reasons:
            raise EpisodeAborted("; ".join(self.incomplete_reasons))
        self.seq += 1
        record = {"episode_id": self.episode_id, "seq": self.seq, "utc": utc_now(), "agent_id": agent_id,
                  "actor_kind": actor_kind, "tool": tool, "arguments": args}
        return self._record_error(record, ToolError(reason))

    def _record_error(self, record: dict[str, Any], error: ToolError) -> dict[str, Any]:
        record.update(status="error", error=str(error))
        try:
            self.recorder.append(record)
        except RecordingError as failure:
            self.incomplete_reasons.append(f"recording failed at seq {self.seq}: {failure}")
            raise EpisodeAborted(self.incomplete_reasons[-1]) from failure
        return {"error": str(error)}

    def _commit(self, agent_id: str, record: dict[str, Any], plan: dict[str, Any],
                staged: Path | None) -> dict[str, Any]:
        if plan["operation"] == "publish":
            final = self.root / record["artifact_path"]
            staged.replace(final)
            self.publications.append({"seq": record["seq"], "publication_id": record["publication_id"],
                                      "version_id": record["inputs"][0]["version_id"],
                                      "audience": record["audience"], "artifact_path": record["artifact_path"]})
            return {"published": record["publication_id"], "audience": record["audience"],
                    "handle": record["inputs"][0]["version_id"]}
        version = Version(
            record["output_version"], plan["name"], "derived", plan["content"], record["output_sha256"],
            produced_by_seq=record["seq"], produced_by_agent=agent_id, operation=plan["operation"],
            inputs=[item["version_id"] for item in record["inputs"]],
        )
        self.versions[version.version_id] = version
        if version.display_name:
            self.names.setdefault(version.display_name, []).append(version.version_id)
        return {"handle": version.version_id, "name": version.display_name, "content": version.content}

    # -- ledger ----------------------------------------------------------------------

    def created_by(self, agent_id: str) -> list[str]:
        return [v.version_id for v in self.versions.values() if v.produced_by_agent == agent_id]

    def handoff_metadata(self, handles: list[str]) -> dict[str, Any]:
        """Describe committed handed versions without content, ancestry or labels.

        ``latest_by_name`` is scoped to this handoff, not the workspace's mutable
        name aliases. All intermediates and superseded versions remain listed;
        consumers use the immutable handle to avoid later/background replacement.
        """
        versions = [self.versions[handle] for handle in handles]
        if len(set(handles)) != len(handles) or any(v.kind != "derived" for v in versions):
            raise ValueError("Handoffs require distinct committed artifact versions")
        versions.sort(key=lambda version: version.produced_by_seq)
        latest = {v.display_name: v.version_id for v in versions if v.display_name is not None}
        return {
            "version": 1,
            "artifacts": [{"handle": v.version_id, "name": v.display_name} for v in versions],
            "latest_by_name": latest,
        }

    def ledger(self) -> dict[str, Any]:
        return {
            "episode_id": self.episode_id,
            "versions": {vid: v.ledger_entry() for vid, v in self.versions.items()},
            "display_names": {name: list(history) for name, history in self.names.items()},
            "publications": list(self.publications),
            "note": "Canonical application-side version ledger; catalog classifications are not stored here.",
        }
