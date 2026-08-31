# Provenance, licensing & authority

The lake is a **governed** data foundation. Every row/image/chunk carries:
source + license + geography + crop + season + growth stage + authority +
ingestion date + version.

## Image & web content policy

A publicly viewable page/image does **not** imply permission to redistribute or
train on it. The license gate (`connectors/web/license_checker.py`) classifies:

| Class | Includes | Action |
| --- | --- | --- |
| **ALLOW** | explicit open licenses (CC0/CC-BY), public-domain government data, datasets with explicit ML permissions, own farmer-consented uploads | ingest + full record |
| **REVIEW** | academic repositories, blogs, extension sites, permissive forums | ingest facts + short semantic chunks + source link; retain `license`, `copyright_status` |
| **BLOCK** | social-media scraping, personal/private photos, unclear copyright, authenticated platforms | refuse by default |

For copyrighted sites we prefer **facts + short semantic chunks + source
linking**, never an uncontrolled duplicate of the publisher's corpus.

Every web-derived item stores:

```
source_url, publisher, author, published_date, retrieved_date,
license, copyright_status, content_hash
```

## Authority hierarchy

| score | Source type |
| --- | --- |
| 1.00 | Government / ICAR / SAU authoritative recommendations |
| 0.95 | Peer-reviewed agriculture research |
| 0.90 | KVK / government extension |
| 0.80 | Recognised agriculture institution |
| 0.65 | Verified domain specialist |
| 0.50 | Agriculture blog |
| 0.35 | Farmer anecdote |
| 0.20 | Anonymous social-media claim |

Seeded in `data/seeds/authority_levels.csv` and used by
`pipelines/quality.py`.

## License notes

- **data.gov.in / OGD platform**: Government Open Data License – India (GODL).
  Individual resources may carry their own terms — always retain per-resource
  license in provenance.
- **FAOSTAT**: FAO data with open terms (cite FAO); not an agronomy advice
  source, only a global statistical baseline.
- **PlantVillage/PlantDoc**: bootstrap vision corpora; insufficient for Indian
  field deployment (controlled backgrounds vs. dirty leaves, shadow, mixed
  disease, low-end phones).

## Versioning

Advisory/knowledge tables are versioned and never silently overwritten:

```
fertilizer_advisory@2026.08
crop_calendar@2026.1
disease_knowledge@2026.3
pesticide_registry@2026.08.30
```

## Lineage contract

Any Krushi Mitra answer must be traceable to `retrieved fact → document → page →
publication date`, and surface "Sources used: ICAR + IMD + Soil Health Card".
