"""Diagnosis retriever: crop + symptoms → ranked, evidence-cited candidates.

Pure DuckDB over the gold tables (no LLM, no vector DB). Follows the blueprint's
diagnosis chain as far as static data allows:

    SYMPTOM → candidate diseases/deficiencies/pests
           → crop compatibility
           → growth-stage compatibility (soft filter)
           → ranked by (symptom matches, crop match, authority)

Returns candidates with management options, the causal agent, differential
diagnosis hints, and the source that backs each entry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pipelines.storage import LAKE_DIR, get_read_connection
from reasoning.symptoms import match_score, matched_tokens, tokenize_symptoms

DEFAULT_LAKE = LAKE_DIR / "agrilake.duckdb"

# Weighting for the static ranking (before any LLM re-ranking).
W_CROP = 3.0     # candidate is for the reported crop
W_SYM = 2.0      # each matched symptom token
W_STAGE = 1.0    # candidate's documented stage includes the reported stage


@dataclass
class DiagnosisResult:
    entity_type: str              # disease | pest | deficiency
    entity_id: str
    name: str
    score: float
    matched_symptoms: list[str] = field(default_factory=list)
    causal_agent: str | None = None
    pathogen_type: str | None = None
    growth_stage: str | None = None
    differential_diagnosis: str | None = None
    economic_threshold: str | None = None
    management: dict[str, str] = field(default_factory=dict)
    source: str = "seed ontology"

    def as_dict(self) -> dict[str, Any]:
        d = {k: v for k, v in self.__dict__.items()}
        return d


def _rank_candidate(
    *,
    crop_match: bool,
    token_matches: int,
    stage: str | None,
    reported_stage: str | None,
    authority: float = 1.0,
) -> float:
    score = authority * (W_SYM * token_matches + (W_CROP if crop_match else 0.0))
    if stage and reported_stage and reported_stage in stage.split("|"):
        score += W_STAGE
    return round(score, 4)


def diagnose(
    crop: str,
    symptoms: str,
    *,
    growth_stage: str | None = None,
    top_n: int = 5,
    lake: Path | None = None,
    strict_crop: bool = True,
) -> list[DiagnosisResult]:
    """Return ranked candidate diseases/pests/deficiencies for a crop + symptoms.

    `crop` accepts a canonical id, English name, or Indian-language alias;
    `symptoms` accepts free text in any language the seed data carries.

    `strict_crop=True` treats crop compatibility as a filter (the blueprint's
    diagnosis chain): when a crop is reported, only that crop's candidates are
    returned. Set it False to surface cross-crop differentials (they must then
    match ≥3 symptom tokens).
    """
    from pipelines.entities import resolve_crop  # local import: avoids cycle at pkg import

    lake = Path(lake or DEFAULT_LAKE)
    tokens = tokenize_symptoms(symptoms)
    crop_row = resolve_crop(crop)
    crop_id = crop_row["crop_id"] if crop_row else None

    def _crop_ok(candidate_crop: str | None, crop_match: bool) -> bool:
        """Crop compatibility gate."""
        if not crop_id:
            return True                      # no crop reported → include everything
        if strict_crop:
            return crop_match                # hard filter
        return True                          # soft: cross-crop allowed if symptoms strong

    con = get_read_connection(lake)
    results: list[DiagnosisResult] = []

    # nutrient id → human name (e.g. NUT_ZN → Zinc)
    nutrient_names = {
        r[0]: r[1]
        for r in con.execute("SELECT nutrient_id, name FROM gold.dim_nutrient").fetchall()
    }

    # ── Diseases ──────────────────────────────────────────────────────
    for row in con.execute(
        "SELECT disease_id, name, crop_id, pathogen_type, causal_agent, symptoms, "
        "growth_stage, differential_diagnosis, management FROM gold.dim_disease"
    ).fetchall():
        (did, name, d_crop, ptype, agent, sympt, stage, diff, mgmt) = row
        n_match = match_score(tokens, sympt or "")
        if n_match == 0:
            continue
        crop_match = bool(crop_id and d_crop == crop_id)
        if not crop_match and crop_id and (not strict_crop and n_match < 3):
            # cross-crop candidates only when symptoms are highly specific
            continue
        if not _crop_ok(d_crop, crop_match):
            continue
        score = _rank_candidate(
            crop_match=crop_match,
            token_matches=n_match,
            stage=stage,
            reported_stage=growth_stage,
            authority=1.0,
        )
        results.append(
            DiagnosisResult(
                entity_type="disease",
                entity_id=did,
                name=name or did,
                score=score,
                matched_symptoms=matched_tokens(tokens, sympt or ""),
                causal_agent=agent,
                pathogen_type=ptype,
                growth_stage=stage,
                differential_diagnosis=diff,
                management={"chemical/cultural": mgmt or ""},
            )
        )

    # ── Pests ────────────────────────────────────────────────────────
    for row in con.execute(
        "SELECT pest_id, name, crop_hosts, damage_symptoms, growth_stage, economic_threshold, "
        "monitoring, cultural_control, biological_control, chemical_control FROM gold.dim_pest"
    ).fetchall():
        (pid, name, hosts, sympt, stage, etl, mon, cult, bio, chem) = row
        n_match = match_score(tokens, sympt or "")
        if n_match == 0:
            continue
        hosts_norm = (hosts or "").lower()
        crop_match = bool(
            crop_id
            and crop_row
            and (crop_row["canonical_en"].lower() in hosts_norm or crop_id in hosts_norm)
        )
        if not crop_match and crop_id and (not strict_crop and n_match < 3):
            continue
        if not _crop_ok(None, crop_match):
            continue
        score = _rank_candidate(
            crop_match=crop_match,
            token_matches=n_match,
            stage=stage,
            reported_stage=growth_stage,
            authority=0.9,
        )
        results.append(
            DiagnosisResult(
                entity_type="pest",
                entity_id=pid,
                name=name or pid,
                score=score,
                matched_symptoms=matched_tokens(tokens, sympt or ""),
                growth_stage=stage,
                economic_threshold=etl,
                management={
                    "cultural": cult or "",
                    "biological": bio or "",
                    "chemical": chem or "",
                    "monitoring": mon or "",
                },
            )
        )

    # ── Nutrient deficiencies ────────────────────────────────────────
    for row in con.execute(
        "SELECT deficiency_id, nutrient_id, crop_id, symptoms, correction FROM gold.nutrient_deficiency"
    ).fetchall():
        (did, nutrient_id, d_crop, sympt, correction) = row
        n_match = match_score(tokens, sympt or "")
        if n_match == 0:
            continue
        crop_match = bool(crop_id and d_crop == crop_id)
        if not crop_match and crop_id and (not strict_crop and n_match < 3):
            continue
        if not _crop_ok(d_crop, crop_match):
            continue
        score = _rank_candidate(
            crop_match=crop_match,
            token_matches=n_match,
            stage=None,
            reported_stage=growth_stage,
            authority=0.95,
        )
        results.append(
            DiagnosisResult(
                entity_type="deficiency",
                entity_id=did,
                name=f"{nutrient_names.get(nutrient_id, nutrient_id)} deficiency",
                score=score,
                matched_symptoms=matched_tokens(tokens, sympt or ""),
                management={"correction": correction or ""},
            )
        )

    results.sort(key=lambda r: (-r.score, r.name))
    return results[:top_n]
