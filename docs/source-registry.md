# Source registry

Every source must be **registered before crawling** so the lake never becomes an
untraceable dump. Registration lives in `metadata/sources/*.yaml`, one file per
source, loaded by `connectors/base.py::SourceRegistry`.

## Schema (YAML)

```yaml
source_id: GOI_KCC
name: Kisan Call Centre
country: IN
source_type: [dataset, qa]
authority: government          # government | research | extension | vendor | community | social
acquisition:
  method: api                  # api | bulk_download | crawl | upload | manual
  endpoint: https://api.data.gov.in/resource/{resource_id}
  schedule: daily
  api_key_required: true
  pagination: offset_limit
domains: [crop, farmer_query, advisory]
license:
  type: GODL-India
  url: https://data.gov.in/government-open-data-license-india
quality:
  authority_score: 1.0
  freshness_score: 0.9
```

`SourceRegistry` validates these files against `connectors/base.py::SourceMetadata`
(Pydantic) and refuses unknown/duplicate `source_id`s.

## Registered sources (V1)

| source_id | Name | Authority | License | Method | Domains |
| --- | --- | --- | --- | --- | --- |
| `GOI_KCC` | Kisan Call Centre | government | GODL-India | api | crop, farmer_query, advisory |
| `GOI_DATAGOV` | data.gov.in (aggregate) | government | GODL-India | api | crop, production, market, soil, weather |
| `GOI_AGMARKNET` | Agmarknet (via data.gov.in) | government | GODL-India | api | market, mandi_price |
| `IMD_AAS` | IMD Agromet Advisory Service | government | GODL-India | bulk_download | weather, advisory |
| `GOI_SHC` | Soil Health Card | government | GODL-India | api/bulk | soil, fertilizer |
| `FAO_FAOSTAT` | FAOSTAT | research (IGO) | CC-BY (FAO T&C) | api | production, yield, fertilizer, land |
| `ICAR` | ICAR / IARI | research | institutional | bulk_download | research, practice |
| `KVK` | Krishi Vigyan Kendras | extension | institutional | crawl | practice, advisory, farmer_qa |
| `PLANTVILLAGE` | PlantVillage | research | CC0 / CC-BY (varies) | bulk_download | vision, disease |
| `PLANTDOC` | PlantDoc | research | CC-BY | bulk_download | vision, disease |

> The registry is **not** the data. It is the governance layer: license,
> authority, schedule, and acquisition method, applied to every record ingested
> from that source.

## Ingestion order (highest evidence-to-engineering ratio first)

1. Kisan Call Centre farmer Q&A
2. data.gov.in agriculture (district × crop × season × year production)
3. Agmarknet mandi prices
4. Soil Health Card
5. IMD advisories/weather
6. ICAR / IARI / KVK material
7. SAU package-of-practice documents
8. FAOSTAT (global baseline)
9. PlantDoc, PlantVillage
10. open-access research
11. carefully licensed blogs
12. first-party farmer photos/questions
