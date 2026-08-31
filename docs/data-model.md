# Data model

## Gold lakehouse tables (V1 target)

Dimensions (slowly-changing, versioned):

| Table | Purpose |
| --- | --- |
| `dim_crop` | canonical crop, scientific name, family, type, group |
| `dim_crop_variety` | released/notable varieties per crop |
| `dim_disease` | disease + pathogen type + symptoms + controls |
| `dim_pathogen` | causal agents (fungal/bacterial/viral/phytoplasma/nematode) |
| `dim_pest` | pest + lifecycle + damage + IPM control ladder |
| `dim_weed` | weeds + hosts + management |
| `dim_fertilizer` | fertilizer products + nutrient composition |
| `dim_nutrient` | N/P/K/S/Zn/B/Fe/Mn/Cu/Mo/Ca/Mg + deficiency symptoms |
| `dim_pesticide` | actives + target + IRAC/FRAC class |
| `dim_biocontrol` | biocontrol agents + targets |
| `dim_soil` | soil types + properties |
| `dim_geography` | state/UT → district → … → agro-climatic/ecological zone |
| `dim_agroclimatic_zone` | zone definitions |
| `dim_growth_stage` | phenological stages |
| `dim_season` | kharif/rabi/zaid/summer/whole-year |

Facts:

| Table | Grain | Source |
| --- | --- | --- |
| `fact_crop_production` | district × crop × season × year × area × production | data.gov.in |
| `fact_yield` | derived `production / area` | derived |
| `fact_crop_calendar` | crop × stage × window × location override | curate/ICAR |
| `fact_mandi_price` | market × commodity × variety × date × min/max/modal | Agmarknet |
| `fact_weather` / `fact_rainfall` | station/district × date × params | IMD |
| `fact_agromet_advisory` | district × valid window × weather + crop advisories | IMD AAS |
| `fact_soil_test` | sample × NPK + micronutrients + pH/EC/OC | Soil Health Card |
| `fact_fertilizer_recommendation` | crop × soil test × target yield → nutrients → product (versioned) | derived |
| `fact_pest_occurrence` / `fact_disease_occurrence` | crop × location × month × severity | PPQS/KVK |
| `farmer_query` / `expert_answer` | KCC + first-party | KCC/app |
| `research_document` / `research_chunk` | semantic chunks with authority | ICAR/SAU/FAO |
| `agri_image` / `image_annotation` | image + labels + license tier | PlantDoc/PlantVillage/own |
| `crop_practice` / `irrigation_practice` / `harvest_practice` / `postharvest_practice` | practice cards | extension |
| `scheme` / `insurance` / `subsidy` | government support | PM-KISAN etc. |

## Unified agriculture record (gold export)

The shape that lets fundamentally different datasets coexist:

```json
{
  "record_id": "…",
  "domain": "crop_protection",
  "crop": "tomato",
  "variety": null,
  "season": "kharif",
  "location": {"state": "Maharashtra", "district": "Pune"},
  "growth_stage": "flowering",
  "problem": {"type": "disease", "symptoms": ["leaf spots", "yellowing"]},
  "weather_context": {},
  "soil_context": {},
  "recommendation": {},
  "source": {"publisher": "…", "url": "…", "license": "…", "authority": "government"},
  "quality": {"confidence": 0.94, "verified": true}
}
```

Schema: `schemas/unified.py` → `schemas/json/unified_agriculture_record.json`.

## Evidence vs recommendation

Never flatten `{"disease": "late blight", "treatment": "spray X"}`. Store:

```
OBSERVATION ──→ DIAGNOSIS
DIAGNOSIS    ──→ EVIDENCE            (symptom/pathogen/lab/visual)
DIAGNOSIS    ──→ MANAGEMENT OPTION
OPTION       ──→ SOURCE
OPTION       ──→ LEGAL / LABEL VALIDITY   (registered for crop/region/date)
OPTION       ──→ LOCATION
OPTION       ──→ DATE
```

This is enforced by `farmer_query`/`expert_answer` carrying `authority`,
`source_url`, `evidence`, `validity` fields, and by the advisory tables being
**versioned** (`fertilizer_advisory@2026.08`, `pesticide_registry@2026.08.30`).

## Fertilizer model — four concepts kept separate

```
NUTRIENT    N P K S Zn B Fe Mn Cu Mo Ca Mg
FERTILIZER  Urea → N ; DAP → N + P2O5 ; MOP → K2O ; SSP → P2O5 + Ca + S …
ORGANIC     FYM / compost / vermicompost / green manure
BIOFERTILIZER  Rhizobium / Azotobacter / PSB / KSB / Mycorrhiza
```

Fertilizer advice is **not** `crop → fertilizer`. It is:

```
Crop + Variety + Growth stage + Soil test + Soil type + Previous crop
+ Irrigation + Target yield + Geography
        ↓
Nutrient requirement
        ↓
Fertilizer recommendation
```

## Multilingual policy

Keep original language text. Every text field may carry:

```json
{
  "original_language": "mr",
  "original_text": "टोमॅटोच्या पानावर काळे डाग आले आहेत…",
  "normalized_text": "…",
  "english_translation": "Black spots are appearing on tomato leaves…",
  "transliteration": "tomyatõchyā pāṇāvar kāḷe ḍāg āle āhet…"
}
```

Original Hindi/Marathi/… is never replaced by the English translation.

## Lineage

Every derived answer must be traceable:

```
farmer question → retrieved fact #28392 → ICAR document XYZ → page 82 → published 2025
→ "Sources used: ICAR + IMD + Soil Health Card"
```

Lineage fields (`source`, `source_url`, `document`, `page`, `published`,
`retrieved_at`, `ingested_at`, `version`) are present on every silver/gold record.
