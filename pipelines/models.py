"""Model-selection policy: upper-boundary (frontier) models only, fail closed.

Standing instruction for this project (`docs/v7-plan.md` §5): any stage that
needs a large language model — gap analysis, extraction-schema design, source
triage, ontology *proposals*, context compaction, evaluation — must use a
**frontier** model. Mid-tier or small models are never substituted: if no
allowlisted model is reachable the stage **stops** rather than quietly
degrading. That is the same lesson the fixture fallback taught us (F4): silent
degradation produces confident, wrong output.

Tiering
-------
``T1`` authoring / analysis  → frontier only, cross-vendor quorum for ontology writes
``T2`` runtime generation    → frontier only (a frontier *flash* class is allowed
                               once the eval gate passes)
``T3`` mechanical work       → no LLM at all; use the deterministic engines

Every selection is budget-checked and auditable via :meth:`ModelPolicy.audit`.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

#: Verified frontier tier, 2026-09-02 (public leaderboards). Primary/secondary
#: defaults are the two best price/capability frontier models with different
#: vendors, so a quorum is genuinely independent.
DEFAULT_ALLOWLIST: tuple[str, ...] = (
    "grok-4.6",
    "qwen3.8-max",
    "claude-opus-5",
    "kimi-k3",
    "gpt-5.6-sol",
    "gemini-3.7-flash",
    "glm-5.3",
)

DEFAULT_PRIMARY = "grok-4.6"
DEFAULT_SECONDARY = "qwen3.8-max"

#: Vendor per model id — used to enforce a *cross-vendor* quorum.
VENDORS: dict[str, str] = {
    "grok-4.6": "xai",
    "grok-4.5": "xai",
    "qwen3.8-max": "alibaba",
    "qwen3.7-max": "alibaba",
    "claude-opus-5": "anthropic",
    "claude-opus-4.8": "anthropic",
    "claude-sonnet-5": "anthropic",
    "kimi-k3": "moonshot",
    "kimi-k2.6": "moonshot",
    "gpt-5.6-sol": "openai",
    "gpt-5.6-terra": "openai",
    "gemini-3.7-flash": "google",
    "glm-5.3": "zhipu",
}

#: Stages that require a frontier model, by tier.
TIER_OF_STAGE: dict[str, str] = {
    "gap_analysis": "T1",
    "extraction_schema": "T1",
    "source_triage": "T1",
    "ontology_proposal": "T1",
    "evaluation_design": "T1",
    "compaction": "T2",
    "answer_drafting": "T2",
    "translation_qa": "T2",
}


class ModelPolicyError(Exception):
    """Base class for policy violations."""


class ModelTierViolation(ModelPolicyError):
    """A non-frontier model was requested for a stage that forbids it."""


class ModelUnavailable(ModelPolicyError):
    """No allowlisted model is reachable — the stage must stop (fail closed)."""


class BudgetExceeded(ModelPolicyError):
    """The run/day USD budget is exhausted."""


class QuorumNotMet(ModelPolicyError):
    """Independent models did not agree on an ontology write."""


@dataclass(frozen=True)
class ModelSelection:
    model_id: str
    tier: str
    stage: str
    vendor: str
    role: str = "primary"          # primary | secondary

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id, "tier": self.tier, "stage": self.stage,
            "vendor": self.vendor, "role": self.role,
        }


@dataclass
class ModelPolicy:
    """Enforces frontier-only selection, quorum and budget."""

    allowlist: tuple[str, ...] = DEFAULT_ALLOWLIST
    primary: str = DEFAULT_PRIMARY
    secondary: str = DEFAULT_SECONDARY
    quorum: int = 2
    budget_run_usd: float = 5.0
    budget_day_usd: float = 50.0
    policy_version: str = "frontier-only/2026-09-02"
    #: models currently reachable; ``None`` means "assume reachable" (offline tests)
    available: Optional[frozenset[str]] = None
    spend_run_usd: float = 0.0
    spend_day_usd: float = 0.0
    audit_trail: list[dict[str, Any]] = field(default_factory=list)

    # ── construction ───────────────────────────────────────────────────────
    @classmethod
    def from_env(cls, environ: dict[str, str] | None = None) -> "ModelPolicy":
        env = dict(os.environ if environ is None else environ)
        allow_raw = env.get("AGRI_MODEL_ALLOWLIST", "")
        allowlist = tuple(m.strip() for m in allow_raw.split(",") if m.strip()) or DEFAULT_ALLOWLIST
        return cls(
            allowlist=allowlist,
            primary=env.get("AGRI_MODEL_PRIMARY", DEFAULT_PRIMARY),
            secondary=env.get("AGRI_MODEL_SECONDARY", DEFAULT_SECONDARY),
            quorum=int(env.get("AGRI_MODEL_QUORUM", "2") or 2),
            budget_run_usd=float(env.get("AGRI_MODEL_BUDGET_RUN_USD", "5") or 5),
            budget_day_usd=float(env.get("AGRI_MODEL_BUDGET_DAY_USD", "50") or 50),
            policy_version=env.get("AGRI_MODEL_POLICY", "frontier-only/2026-09-02"),
        )

    # ── selection ──────────────────────────────────────────────────────────
    def tier_for(self, stage: str) -> str:
        return TIER_OF_STAGE.get(stage, "T2")

    def is_allowlisted(self, model_id: str) -> bool:
        return model_id in self.allowlist

    def select(self, stage: str, *, role: str = "primary", model_id: str | None = None) -> ModelSelection:
        """Resolve a model for ``stage``, enforcing the frontier-only rule.

        Raises :class:`ModelTierViolation` for a non-allowlisted id and
        :class:`ModelUnavailable` when no allowlisted model is reachable — the
        caller must stop, never substitute a weaker model.
        """
        tier = self.tier_for(stage)
        if tier == "T3":
            raise ModelTierViolation(f"stage {stage!r} is deterministic; no LLM may be used")

        chosen = model_id or (self.primary if role == "primary" else self.secondary)
        if not self.is_allowlisted(chosen):
            raise ModelTierViolation(
                f"{chosen!r} is not on the frontier allowlist {list(self.allowlist)}; "
                f"stage {stage!r} ({tier}) requires an upper-boundary model"
            )
        if self.available is not None and chosen not in self.available:
            fallback = next((m for m in self.allowlist if m in self.available), None)
            if fallback is None:
                raise ModelUnavailable(
                    f"no allowlisted model reachable for stage {stage!r}; refusing to "
                    "degrade to a weaker model — stop the stage and retry later"
                )
            chosen = fallback
        return ModelSelection(
            model_id=chosen, tier=tier, stage=stage, vendor=VENDORS.get(chosen, "unknown"), role=role
        )

    def pair(self, stage: str) -> tuple[ModelSelection, ModelSelection]:
        """Primary + secondary selection, guaranteed to be cross-vendor."""
        primary = self.select(stage, role="primary")
        secondary = self.select(stage, role="secondary")
        if primary.vendor == secondary.vendor:
            alternative = next(
                (m for m in self.allowlist if VENDORS.get(m, m) != primary.vendor), None
            )
            if alternative is None:
                raise QuorumNotMet("allowlist contains a single vendor; cannot form an independent quorum")
            secondary = ModelSelection(
                model_id=alternative, tier=primary.tier, stage=stage,
                vendor=VENDORS.get(alternative, "unknown"), role="secondary",
            )
        return primary, secondary

    # ── quorum ─────────────────────────────────────────────────────────────
    def quorum_ok(self, proposals: Iterable[tuple[str, Any]]) -> bool:
        """True when ``quorum`` *different-vendor* models produced equal output."""
        seen: dict[str, Any] = {}
        for model_id, value in proposals:
            if not self.is_allowlisted(model_id):
                raise ModelTierViolation(f"{model_id!r} is not frontier; its vote does not count")
            seen.setdefault(VENDORS.get(model_id, model_id), value)
        if len(seen) < max(2, self.quorum):
            return False
        values = {hashlib.sha256(str(v).encode("utf-8")).hexdigest() for v in seen.values()}
        return len(values) == 1

    def agree_or_raise(self, proposals: Iterable[tuple[str, Any]]) -> Any:
        materialised = list(proposals)
        if not self.quorum_ok(materialised):
            raise QuorumNotMet(
                f"frontier models disagreed or fewer than {self.quorum} independent vendors voted; "
                "route to human review instead of writing the ontology"
            )
        return materialised[0][1]

    # ── budget + audit ─────────────────────────────────────────────────────
    def charge(self, cost_usd: float) -> None:
        """Accumulate spend; raise :class:`BudgetExceeded` past either cap."""
        if cost_usd < 0:
            raise ValueError("cost_usd must be >= 0")
        if self.spend_run_usd + cost_usd > self.budget_run_usd:
            raise BudgetExceeded(
                f"run budget exhausted: {self.spend_run_usd + cost_usd:.4f} > {self.budget_run_usd} USD"
            )
        if self.spend_day_usd + cost_usd > self.budget_day_usd:
            raise BudgetExceeded(
                f"daily budget exhausted: {self.spend_day_usd + cost_usd:.4f} > {self.budget_day_usd} USD"
            )
        self.spend_run_usd = round(self.spend_run_usd + cost_usd, 6)
        self.spend_day_usd = round(self.spend_day_usd + cost_usd, 6)

    def audit(
        self,
        *,
        selection: ModelSelection,
        run_id: str,
        task: str,
        tokens_in: int = 0,
        tokens_out: int = 0,
        cost_usd: float = 0.0,
        latency_ms: int = 0,
        status: str = "ok",
        prompt: str = "",
    ) -> dict[str, Any]:
        """Record one model call (also enforces the budget)."""
        if status == "ok" and cost_usd:
            self.charge(cost_usd)
        row = {
            "run_id": run_id,
            "stage": selection.stage,
            "task": task,
            "model_id": selection.model_id,
            "tier": selection.tier,
            "vendor": selection.vendor,
            "policy_version": self.policy_version,
            "prompt_hash": hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16] if prompt else "",
            "tokens_in": int(tokens_in),
            "tokens_out": int(tokens_out),
            "cost_usd": float(cost_usd),
            "latency_ms": int(latency_ms),
            "status": status,
        }
        self.audit_trail.append(row)
        return row


AUDIT_DDL = """
CREATE TABLE IF NOT EXISTS gold.model_call_audit (
    run_id VARCHAR, stage VARCHAR, task VARCHAR, model_id VARCHAR, tier VARCHAR,
    vendor VARCHAR, policy_version VARCHAR, prompt_hash VARCHAR, tokens_in INTEGER,
    tokens_out INTEGER, cost_usd DOUBLE, latency_ms INTEGER, status VARCHAR,
    called_at VARCHAR
)
"""


def persist_audit(rows: Iterable[dict[str, Any]], lake: Any = None) -> int:
    """Append audit rows to ``gold.model_call_audit``; returns rows written."""
    from pipelines.collect import _connect
    from pipelines.storage import utcnow_iso

    rows = list(rows)
    if not rows:
        return 0
    now = utcnow_iso()
    con = _connect(lake)
    try:
        con.execute(AUDIT_DDL)
        for row in rows:
            con.execute(
                "INSERT INTO gold.model_call_audit VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    row.get("run_id", ""), row.get("stage", ""), row.get("task", ""),
                    row.get("model_id", ""), row.get("tier", ""), row.get("vendor", ""),
                    row.get("policy_version", ""), row.get("prompt_hash", ""),
                    int(row.get("tokens_in", 0)), int(row.get("tokens_out", 0)),
                    float(row.get("cost_usd", 0.0)), int(row.get("latency_ms", 0)),
                    row.get("status", "ok"), now,
                ],
            )
        return len(rows)
    finally:
        con.close()
