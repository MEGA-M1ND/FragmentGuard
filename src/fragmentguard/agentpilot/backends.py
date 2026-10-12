"""Generation backends for agent episodes, and the live spending guard.

- ``ScriptedBackend`` replays a hand-written tool-call plan. It exercises the real
  tool executor and recorder, but no model chose any action; its runs are always
  labelled ``scripted`` and are never live evidence.
- ``LiveBackend`` calls a tool-calling model through Inspect AI's provider-neutral
  ``get_model``. It runs only with an explicit limits file that enables live mode,
  names the exact model, and supplies positive prices and limits. Before every
  request it reserves a pessimistic maximum cost and refuses the request if the
  reservation could exceed the cap. Automatic retries are disabled.

Credentials are read only by the provider integration from its usual
environment variables (e.g. ``ANTHROPIC_API_KEY``); this module never reads,
prints, or stores them.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .workspace import TOOL_SCHEMAS, canonical

REFUSAL_STOP_REASONS = ("content_filter", "refusal")


class LiveNotAuthorized(Exception):
    """Live generation was requested without explicit, complete authorization."""


class LimitReached(Exception):
    """A request, tool-call, context, or spending limit stops the agent before the call."""


@dataclass(frozen=True)
class AgentLimits:
    max_requests_per_agent: int = 8
    max_tool_calls_per_agent: int = 6

    def __post_init__(self) -> None:
        if self.max_requests_per_agent < 1 or self.max_tool_calls_per_agent < 1:
            raise ValueError("Agent limits must be positive")


LIVE_REQUIRED = (
    "live_enabled", "model", "max_spend_usd", "input_usd_per_million_tokens",
    "output_usd_per_million_tokens", "pricing_source", "pricing_retrieved_utc", "max_output_tokens",
    "max_requests_per_agent", "max_tool_calls_per_agent", "max_total_requests", "max_context_bytes",
    "request_overhead_tokens",
)


@dataclass(frozen=True)
class LiveLimits:
    live_enabled: bool
    model: str
    max_spend_usd: float
    input_usd_per_million_tokens: float
    output_usd_per_million_tokens: float
    pricing_source: str
    pricing_retrieved_utc: str
    max_output_tokens: int
    max_requests_per_agent: int
    max_tool_calls_per_agent: int
    max_total_requests: int
    max_context_bytes: int
    request_overhead_tokens: int
    temperature: float | None = None
    seed: int | None = None
    timeout_seconds: int = 120
    notes: str = ""

    @classmethod
    def load(cls, path: Path) -> "LiveLimits":
        raw = json.loads(path.read_text(encoding="utf-8"))
        missing = [key for key in LIVE_REQUIRED if raw.get(key) in (None, "")]
        if missing:
            raise LiveNotAuthorized(f"Limits file is missing required settings: {missing}")
        unknown = set(raw) - set(cls.__dataclass_fields__)
        if unknown:
            raise LiveNotAuthorized(f"Unknown limits settings: {sorted(unknown)}")
        limits = cls(**raw)
        limits.validate()
        return limits

    def validate(self) -> None:
        if self.live_enabled is not True:
            raise LiveNotAuthorized("Live generation is not enabled (set live_enabled: true explicitly)")
        if "/" not in self.model or self.model.startswith("mockllm/"):
            raise LiveNotAuthorized("model must be an exact provider/model ID (mock models are not live)")
        for name in ("max_spend_usd", "input_usd_per_million_tokens", "output_usd_per_million_tokens"):
            if not isinstance(getattr(self, name), (int, float)) or getattr(self, name) <= 0:
                raise LiveNotAuthorized(f"{name} must be positive; unknown pricing is never treated as zero")
        for name in ("max_output_tokens", "max_requests_per_agent", "max_tool_calls_per_agent",
                     "max_total_requests", "max_context_bytes"):
            if not isinstance(getattr(self, name), int) or getattr(self, name) < 1:
                raise LiveNotAuthorized(f"{name} must be a positive integer")
        if not isinstance(self.request_overhead_tokens, int) or self.request_overhead_tokens < 0:
            raise LiveNotAuthorized("request_overhead_tokens must be a nonnegative integer")

    def agent_limits(self) -> AgentLimits:
        return AgentLimits(self.max_requests_per_agent, self.max_tool_calls_per_agent)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Budget:
    """Reserve-before-request spending guard shared across a whole run."""

    limits: LiveLimits
    spent_usd: float = 0.0
    requests: int = 0
    ledger: list[dict[str, Any]] = field(default_factory=list)

    def reservation_usd(self, request_bytes: int) -> float:
        # Pessimistic input bound: at most one token per UTF-8 byte of the serialized
        # request, plus a fixed allowance for provider-side formatting.
        input_tokens = request_bytes + self.limits.request_overhead_tokens
        return (input_tokens * self.limits.input_usd_per_million_tokens
                + self.limits.max_output_tokens * self.limits.output_usd_per_million_tokens) / 1e6

    def pessimistic_run_max_usd(self, episodes: int, agents_per_episode: int = 3) -> float:
        requests = min(self.limits.max_total_requests,
                       episodes * agents_per_episode * self.limits.max_requests_per_agent)
        return requests * self.reservation_usd(self.limits.max_context_bytes)

    def reserve(self, request_bytes: int) -> float:
        if request_bytes > self.limits.max_context_bytes:
            raise LimitReached(f"request of {request_bytes} bytes exceeds max_context_bytes")
        if self.requests >= self.limits.max_total_requests:
            raise LimitReached("max_total_requests reached")
        reserved = self.reservation_usd(request_bytes)
        if self.spent_usd + reserved > self.limits.max_spend_usd:
            raise LimitReached(
                f"next request could cost up to ${reserved:.4f}; ${self.spent_usd:.4f} of "
                f"${self.limits.max_spend_usd:.2f} already accounted"
            )
        self.requests += 1
        return reserved

    def settle(self, reserved: float, usage: dict[str, Any] | None) -> dict[str, Any]:
        tokens_known = bool(usage) and usage.get("input_tokens") is not None and usage.get("output_tokens") is not None
        if tokens_known:
            input_tokens = (usage["input_tokens"] + (usage.get("input_tokens_cache_read") or 0)
                            + (usage.get("input_tokens_cache_write") or 0))
            output_tokens = usage["output_tokens"] + (usage.get("reasoning_tokens") or 0)
            cost = (input_tokens * self.limits.input_usd_per_million_tokens
                    + output_tokens * self.limits.output_usd_per_million_tokens) / 1e6
            basis = "measured usage x supplied prices (cache and reasoning tokens charged at full rates)"
        else:
            cost = reserved
            basis = "usage unavailable: charged the full reservation"
        self.spent_usd += cost
        entry = {"reserved_usd": reserved, "accounted_usd": cost, "basis": basis,
                 "cumulative_usd": self.spent_usd, "over_cap": self.spent_usd > self.limits.max_spend_usd}
        self.ledger.append(entry)
        return entry


@dataclass
class Turn:
    text: str
    tool_calls: list[dict[str, Any]]
    stop_reason: str
    usage: dict[str, Any] | None = None
    cost: dict[str, Any] | None = None
    error: str | None = None
    model: str | None = None


class ScriptedBackend:
    """Deterministic plan replay. Not a model; results are never live evidence."""

    kind = "scripted"
    model = None

    def __init__(self, plan: dict[str, list[dict[str, Any]]]):
        unknown = set(plan) - {"collector", "processor", "publisher", "note"}
        if unknown:
            raise ValueError(f"Scripted plan has unknown roles: {sorted(unknown)}")
        self.plan = {role: list(steps) for role, steps in plan.items() if role != "note"}
        self.calls = 0

    async def generate(self, role: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> Turn:
        steps = self.plan.setdefault(role, [])
        if not steps:
            return Turn("Done.", [], "stop")
        step = steps.pop(0)
        if "tool" in step:
            self.calls += 1
            call = {"id": f"scripted-{role}-{self.calls}", "name": step["tool"], "arguments": step.get("arguments", {})}
            return Turn("", [call], "tool_calls")
        return Turn(step.get("final", ""), [], step.get("stop_reason", "stop"))


def tool_specs(tool_names: tuple[str, ...]) -> list[dict[str, Any]]:
    return [{"name": name, **TOOL_SCHEMAS[name]} for name in tool_names]


class LiveBackend:
    """Tool-calling model via Inspect AI, guarded by ``Budget``."""

    kind = "live"

    def __init__(self, limits: LiveLimits, budget: Budget, model: Any = None, *, _allow_test_model: bool = False):
        if model is not None and not _allow_test_model:
            raise LiveNotAuthorized("Injected models are for tests only")
        if model is None:
            limits.validate()
            from inspect_ai.model import get_model  # noqa: PLC0415

            model = get_model(limits.model, memoize=False)
        self.limits = limits
        self.budget = budget
        self.model_handle = model
        self.model = limits.model

    def _config(self) -> Any:
        from inspect_ai.model import GenerateConfig  # noqa: PLC0415

        return GenerateConfig(
            max_retries=0, max_tokens=self.limits.max_output_tokens, temperature=self.limits.temperature,
            seed=self.limits.seed, timeout=self.limits.timeout_seconds,
        )

    @staticmethod
    def _messages(messages: list[dict[str, Any]]) -> list[Any]:
        from inspect_ai.model import (  # noqa: PLC0415
            ChatMessageAssistant, ChatMessageSystem, ChatMessageTool, ChatMessageUser,
        )
        from inspect_ai.tool import ToolCall  # noqa: PLC0415

        converted = []
        for message in messages:
            role = message["role"]
            if role == "system":
                converted.append(ChatMessageSystem(content=message["content"]))
            elif role == "user":
                converted.append(ChatMessageUser(content=message["content"]))
            elif role == "assistant":
                calls = [ToolCall(id=c["id"], function=c["name"], arguments=c["arguments"])
                         for c in message.get("tool_calls", [])]
                converted.append(ChatMessageAssistant(content=message.get("content") or "", tool_calls=calls or None))
            else:
                converted.append(ChatMessageTool(content=message["content"], tool_call_id=message["tool_call_id"],
                                                 function=message["name"]))
        return converted

    @staticmethod
    def _tools(tools: list[dict[str, Any]]) -> list[Any]:
        from inspect_ai.tool import ToolInfo, ToolParams  # noqa: PLC0415

        return [ToolInfo(name=t["name"], description=t["description"],
                         parameters=ToolParams.model_validate(t["parameters"])) for t in tools]

    async def generate(self, role: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> Turn:
        request_bytes = len(canonical({"messages": messages, "tools": tools}))
        reserved = self.budget.reserve(request_bytes)  # Raises LimitReached before any call.
        try:
            output = await self.model_handle.generate(
                self._messages(messages), tools=self._tools(tools), tool_choice="auto",
                config=self._config(), cache=False,
            )
        except Exception as error:  # noqa: BLE001 - preserved; no retry with a different request
            cost = self.budget.settle(reserved, None)
            return Turn("", [], "error", None, cost, f"{type(error).__name__}: {error}", self.model)
        usage = output.usage.model_dump(mode="json") if output.usage is not None else None
        cost = self.budget.settle(reserved, usage)
        message = output.message
        calls = [{"id": c.id, "name": c.function, "arguments": c.arguments, "parse_error": c.parse_error}
                 for c in (message.tool_calls or [])]
        stop_reason = str(output.stop_reason)
        error = str(output.error) if getattr(output, "error", None) else None
        return Turn(message.text or "", calls, stop_reason, usage, cost, error, output.model or self.model)

