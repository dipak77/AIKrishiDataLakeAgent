"""Krushi Mitra assistant (Track 13) — intent routing + answer composition.

A farmer query (English / Hindi / Marathi / Tamil / Telugu) is turned into a
structured, evidence-cited answer:

    1. detect language (pipelines.language)
    2. classify intent (keyword + lexicon scoring, offline, deterministic)
    3. extract entities (crop, district/state, growth stage, symptoms)
    4. route to the right engine(s):
         diagnosis    → reasoning.diagnose
         fertilizer   → reasoning.advisory.recommend_fertilizer
         mandi_price  → reasoning.mandi.market_advisory
         weather      → reasoning.weather.agromet_advisory
         crop_planning→ reasoning.crop_plan.crop_plan
         evidence     → reasoning.rag.search
         general      → graph health-map + RAG fallback
    5. compose a single AssistantResponse with observation/recommendation/
       evidence separation (blueprint non-negotiable).

The router is deliberately heuristic + transparent: every answer records which
intent fired and why (matched keywords), so it can be audited and later
replaced by a trained classifier without changing the engine contracts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pipelines.language import detect_language
from pipelines.storage import LAKE_DIR
from reasoning import nlu as nlu_mod

DEFAULT_LAKE = LAKE_DIR / "agrilake.duckdb"

# ── Intent keyword lexicons (English + Indic) ────────────────────────────────
_INTENT_KEYWORDS: dict[str, list[str]] = {
    "diagnosis": [
        "disease", "symptom", "symptoms", "spots", "spot", "wilting", "wilt",
        "yellowing", "yellow", "blight", "pest", "rot", "insect", "borer",
        "fungus", "fungal", "lesion", "leaf", "leaves", "curling", "stunted",
        "drooping", "infection", "treat", "treatment", "spray", "control",
        "cure", "problem", "attack", "रोग", "बीमारी", "कीड़ा", "दाग", "धब्बे",
        "पत्ति", "மருத்துவம்", "நோய்", "பூச்சி", "புள்ளி", "వ్యాధి", "చీడ",
        "మచ్చ", "తెగులు",
    ],
    "fertilizer": [
        "fertilizer", "urea", "dap", "mop", "npk", "nutrient", "dose", "kg",
        "soil test", "compost", "manure", "fym", "nitrogen", "phosphorus",
        "potash", "पोटाश", "खत", "उर्वरक", "खाद", "மண்ணு", "உரம்", "எரு",
        "ఎరువు", "ఎరువులు",
    ],
    "mandi_price": [
        "price", "rate", "mandi", "bazaar", "bazar", "market", "quintal",
        "bhav", "sell", "selling", "मंडी", "भाव", "दाम", "कीमत", "விலை",
        "சந்தை", "ధర", "మార్కెట్", "మండి",
    ],
    "weather": [
        "rain", "rainfall", "weather", "temperature", "humidity", "monsoon",
        "frost", "wind", "storm", "बारिश", "वर्षा", "मौसम", "வானிலை", "மழை",
        "వర్షం", "వాతావరణం",
    ],
    "crop_planning": [
        "sow", "sowing", "plant", "planting", "season", "when", "month",
        "cultivate", "transplant", "बोना", "बुवाई", "मौसम", "விதைக்க",
        "விதைப்பு", "నాటు", "విత్తనం",
    ],
    "evidence": [
        "research", "guide", "practice", "paper", "information", "about",
        "what is", "recommendation", "how to", "अनुसंधान", "जानकारी",
        "முறை", "வழிகாட்டி", "సమాచారం", "పద్ధతి",
    ],
}


def classify_intent(query: str) -> tuple[str, dict[str, int]]:
    """Score each intent by keyword hits; return (intent, scores)."""
    q = query.lower()
    scores: dict[str, int] = {}
    for intent, keywords in _INTENT_KEYWORDS.items():
        scores[intent] = sum(1 for kw in keywords if kw in q)
    # Symptom lexicon is the strongest diagnosis signal (Indic scripts).
    from domain.seed_data import SYMPTOM_LEXICON

    for lang_terms in SYMPTOM_LEXICON.values():
        for term in lang_terms:
            if term in q:
                scores["diagnosis"] += 2
    best = max(scores, key=lambda k: scores[k])
    if scores[best] == 0:
        best = "general"
    return best, scores


def extract_crop(query: str) -> dict[str, Any] | None:
    from pipelines.entities import extract_crops

    crops = extract_crops(query)
    return crops[0] if crops else None


def extract_location(query: str) -> dict[str, Any]:
    """Best-effort district/state extraction from a query."""
    from domain.catalog import GEOGRAPHY_LOOKUP
    from pipelines.geocode import _norm

    words = query.split()
    # Try 2-token then 1-token windows against state names.
    for n in (2, 1):
        for i in range(len(words) - n + 1):
            chunk = _norm(" ".join(words[i:i + n]))
            if not chunk:
                continue
            if chunk in GEOGRAPHY_LOOKUP["by_state"]:
                row = GEOGRAPHY_LOOKUP["by_state"][chunk]
                return {"state": row["name"], "state_code": row["state_code"]}
            if chunk in GEOGRAPHY_LOOKUP["by_alias"]:
                row = GEOGRAPHY_LOOKUP["by_alias"][chunk]
                return {"state": row["name"], "state_code": row["state_code"]}
    # District names (flattened across states).
    for n in (2, 1):
        for i in range(len(words) - n + 1):
            chunk = _norm(" ".join(words[i:i + n]))
            if not chunk:
                continue
            for (scode, dname), row in GEOGRAPHY_LOOKUP["by_district"].items():
                if dname == chunk:
                    return {
                        "district": row["district_name"],
                        "district_code": row["district_code"],
                        "state": row["state_name"],
                        "state_code": row["state_code"],
                    }
            for (scode, dname), row in GEOGRAPHY_LOOKUP["by_district_alias"].items():
                if dname == chunk:
                    return {
                        "district": row["district_name"],
                        "district_code": row["district_code"],
                        "state": row["state_name"],
                        "state_code": row["state_code"],
                    }
    return {}


def extract_stage(query: str) -> str | None:
    from domain.seed_data import GROWTH_STAGES

    q = query.lower()
    synonyms = {"fruiting": "fruit_set", "fruit development": "fruit_set"}
    for st in GROWTH_STAGES:
        if st["name"].lower() in q or st["stage_id"].lower().replace("stage_", "") in q:
            return st["name"]
    for syn, canon in synonyms.items():
        if syn in q:
            return canon
    return None


@dataclass
class AssistantAnswer:
    """One engine's contribution to the final answer."""

    engine: str
    title: str
    body: list[str] = field(default_factory=list)
    data: Any = None
    citations: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class AssistantResponse:
    query: str
    language: str | None
    language_confidence: float
    intent: str
    intent_scores: dict[str, float]
    entities: dict[str, Any] = field(default_factory=dict)
    answers: list[AssistantAnswer] = field(default_factory=list)
    matched_keywords: list[str] = field(default_factory=list)
    intent_confidence: float = 1.0
    nlu_model: str = "heuristic"

    def as_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "language": self.language,
            "language_confidence": self.language_confidence,
            "intent": self.intent,
            "intent_scores": self.intent_scores,
            "intent_confidence": self.intent_confidence,
            "nlu_model": self.nlu_model,
            "entities": self.entities,
            "answers": [
                {
                    "engine": a.engine,
                    "title": a.title,
                    "body": a.body,
                    "data": a.data,
                    "citations": a.citations,
                }
                for a in self.answers
            ],
            "matched_keywords": self.matched_keywords,
        }


def _diagnosis_answer(query: str, crop: dict | None, stage: str | None) -> AssistantAnswer:
    from reasoning.diagnose import diagnose

    if not crop:
        return AssistantAnswer("diagnosis", "Diagnosis", ["Tell me which crop is affected to diagnose it."])
    results = diagnose(crop["canonical_en"], query, growth_stage=stage, top_n=3)
    if not results:
        return AssistantAnswer(
            "diagnosis", "Diagnosis",
            [f"No candidate matched for {crop['canonical_en']} from these symptoms. Add more symptom words."],
        )
    body = []
    citations = []
    for r in results:
        agent = f" ({r.causal_agent})" if r.causal_agent else ""
        body.append(f"{r.name}{agent} — score {r.score}")
        if r.matched_symptoms:
            body.append(f"    matched symptoms: {', '.join(r.matched_symptoms)}")
        if r.management:
            for k, v in r.management.items():
                if v:
                    body.append(f"    {k}: {v}")
        citations.append({"source": r.source, "entity": r.name, "score": r.score})
    return AssistantAnswer("diagnosis", f"Diagnosis for {crop['canonical_en']}", body, data=[r.as_dict() for r in results], citations=citations)


def _fertilizer_answer(query: str, crop: dict | None, stage: str | None) -> AssistantAnswer:
    from reasoning.advisory import recommend_fertilizer

    if not crop:
        return AssistantAnswer("fertilizer", "Fertilizer advisory", ["Tell me which crop to advise on."])
    adv = recommend_fertilizer(crop["canonical_en"], growth_stage=stage)
    if not adv:
        return AssistantAnswer(
            "fertilizer", "Fertilizer advisory",
            [f"No nutrient recipe seeded for {crop['canonical_en']} yet."],
        )
    body = list(adv.recommendations)
    if adv.notes:
        body.append("notes: " + " | ".join(adv.notes))
    return AssistantAnswer(
        "fertilizer",
        f"Fertilizer advisory for {adv.crop} ({adv.version})",
        body,
        data=adv.as_dict(),
        citations=[adv.evidence],
    )


def _mandi_answer(query: str, crop: dict | None) -> AssistantAnswer:
    from reasoning.mandi import market_advisory

    commodity = crop["canonical_en"] if crop else None
    if not commodity:
        # try extracting a known commodity token
        commodity = query.split()[0]
    adv = market_advisory(commodity)
    if not adv:
        return AssistantAnswer("mandi", "Mandi prices", [f"No price data for '{commodity}'."])
    body = []
    for s in adv.stats:
        body.append(
            f"{s.market} ({s.district or s.state}): modal ₹{s.latest_modal}/q on {s.latest_date}, "
            f"trend {s.trend}, ±{s.volatility_pct}%"
        )
    body.append(f"season: [{adv.season_signal}] {adv.season_note}")
    return AssistantAnswer(
        "mandi", f"Mandi prices — {adv.commodity}",
        body, data=adv.as_dict(), citations=[adv.evidence],
    )


def _weather_answer(query: str, location: dict) -> AssistantAnswer:
    from reasoning.weather import agromet_advisory

    district = location.get("district") or location.get("state")
    if not district:
        return AssistantAnswer("weather", "Weather advisory", ["Tell me a district (e.g. Pune) to get its agromet advisory."])
    adv = agromet_advisory(district)
    if not adv:
        return AssistantAnswer("weather", "Weather advisory", [f"No advisory seeded for '{district}'."])
    body = [
        f"{adv.valid_from} → {adv.valid_to}: {adv.weather.get('rainfall')}, "
        f"{adv.weather.get('temp_min')}–{adv.weather.get('temp_max')}°C"
    ]
    for f in adv.flags:
        body.append(f"[{f.flag}] {f.note}")
    for c in adv.crops:
        body.append(f"{c.crop} ({c.growth_stage}): {c.risk}")
    return AssistantAnswer(
        "weather", f"Weather advisory — {adv.district}",
        body, data=adv.as_dict(), citations=[adv.evidence],
    )


def _plan_answer(query: str, crop: dict | None, location: dict) -> AssistantAnswer:
    from reasoning.crop_plan import crop_plan

    if not crop:
        return AssistantAnswer("crop_planning", "Crop plan", ["Tell me which crop to plan for."])
    plan = crop_plan(crop["canonical_en"], state=location.get("state"), district=location.get("district"))
    if not plan:
        return AssistantAnswer("crop_planning", "Crop plan", [f"No calendar for {crop['canonical_en']}."])
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    body = [
        f"seasons: {', '.join(plan.seasons)}",
        "sow: " + ", ".join(months[m - 1] for m in plan.sow_window),
        "harvest: " + ", ".join(months[m - 1] for m in plan.harvest_window),
    ]
    return AssistantAnswer(
        "crop_planning", f"Crop plan — {plan.crop}",
        body, data=plan.as_dict(), citations=[plan.evidence],
    )


def _evidence_answer(query: str, crop: dict | None) -> AssistantAnswer:
    from reasoning.rag import hybrid_search

    crop_id = crop["crop_id"] if crop else None
    hits = hybrid_search(query, top_k=3, crop=crop_id)
    if not hits:
        return AssistantAnswer("evidence", "Research evidence", ["No matching research chunk."])
    body = [f"{h.document} — {h.institution} ({h.year})" for h in hits]
    citations = [
        {"source": h.source_url or h.institution, "authority": h.authority, "score": h.score}
        for h in hits
    ]
    return AssistantAnswer(
        "evidence", "Research evidence",
        body, data=[h.as_dict() for h in hits], citations=citations,
    )


def _general_answer(query: str, crop: dict | None) -> AssistantAnswer:
    from reasoning.graph_query import crop_health_map

    if not crop:
        from reasoning.rag import hybrid_search

        hits = hybrid_search(query, top_k=3)
        if hits:
            return _evidence_answer(query, None)
        return AssistantAnswer("general", "Krushi Mitra", ["Ask about a crop's diseases, prices, weather, or when to sow."])
    hm = crop_health_map(crop["canonical_en"])
    body = [
        f"diseases: {', '.join(d['label'] for d in hm['diseases']) or '-'}",
        f"pests: {', '.join(p['label'] for p in hm['pests']) or '-'}",
        f"deficiencies: {', '.join(d['label'] for d in hm['deficiencies']) or '-'}",
    ]
    return AssistantAnswer(
        "general", f"Health map — {crop['canonical_en']}",
        body, data=hm,
        citations=[{"source": "knowledge graph (seed ontology)", "authority": "government_extension"}],
    )


def ask(query: str, *, lake: Path | None = None) -> AssistantResponse:
    """Route + answer a farmer query (trained NLU, heuristic fallback)."""
    lang = detect_language(query)
    # Trained intent + NER pipeline; gracefully degrades to the keyword router.
    try:
        nlu = nlu_mod.get_pipeline().predict(query)
    except Exception:
        nlu = nlu_mod.NLUPipeline._heuristic(query)
    intent = nlu.intent
    scores = nlu.intent_scores
    crop = nlu.crop
    location = nlu.location
    stage = nlu.stage

    # matched keywords (for auditability) — reuse the classifier's lexicon
    matched = [
        kw for intent_keywords in _INTENT_KEYWORDS.values() for kw in intent_keywords
        if kw in query.lower()
    ]

    entities = {
        "crop": crop["canonical_en"] if crop else None,
        "crop_id": crop["crop_id"] if crop else None,
        "district": location.get("district"),
        "state": location.get("state"),
        "stage": stage,
        "symptoms": nlu.symptoms,
    }
    resp = AssistantResponse(
        query=query,
        language=lang["language"],
        language_confidence=lang["confidence"],
        intent=intent,
        intent_scores=scores,
        entities=entities,
        matched_keywords=sorted(set(matched))[:20],
        intent_confidence=nlu.intent_confidence,
        nlu_model=nlu.model,
    )

    handlers = {
        "diagnosis": lambda: _diagnosis_answer(query, crop, stage),
        "fertilizer": lambda: _fertilizer_answer(query, crop, stage),
        "mandi_price": lambda: _mandi_answer(query, crop),
        "weather": lambda: _weather_answer(query, location),
        "crop_planning": lambda: _plan_answer(query, crop, location),
        "evidence": lambda: _evidence_answer(query, crop),
        "general": lambda: _general_answer(query, crop),
    }
    primary = handlers[intent]()

    # Multi-engine enrichment: a crop diagnosis also surfaces weather + evidence.
    if intent == "diagnosis" and location.get("district"):
        primary.body.append("")
        primary.body.append("(local weather context is available — try the weather advisory)")
    resp.answers.append(primary)
    return resp
