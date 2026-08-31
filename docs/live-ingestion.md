# Live ingestion

Connectors are real HTTP clients. They run unmodified in any environment with
outbound internet; in restricted sandboxes they degrade gracefully to the
bundled fixtures in `data/fixtures/`.

## Quickstart

```bash
export DATA_GOV_IN_API_KEY=<your-key>   # optional
make ingest SOURCE=agmarknet LIMIT=5
make ingest SOURCE=kcc LIMIT=5
make ingest SOURCE=faostat LIMIT=20
```

If a source is unreachable (no egress, blocked host, rate limit), the connector
logs a warning and persists the fixture record instead, tagging
`ingestion_method: "fixture"` so provenance is never faked.

## Endpoints

### data.gov.in (OGD Platform India)

```
GET https://api.data.gov.in/resource/{resource_id}
    ?api-key={key}&format=json&offset={n}&limit={m}
```

- Free API key: data.gov.in → account → "Generate API key".
- A shared demo key is tried as a fallback but is heavily rate-limited.
- KCC resources are district×month specific (e.g. resource
  `5f039cdb2e054ab5b74bfc2a6e1a860b` = Vizianagaram (AP), June 2018). The
  aggregate KCC transcript resource is used for the QA corpus.
- Agmarknet daily mandi prices: resource `9ef84268-d588-465a-a308-a864a43d0070`.

### FAOSTAT (no key)

```
GET https://fenixservices.fao.org/faostat/api/v1/en/data/QCL
    ?area=100&area_cs=FAO&element=5510&element_cs=FAO
    &item={item}&item_cs=FAO&year={year}
    &show_codes=true&show_unit=true&output_type=csv
```

- `area=100` = India; `element=5312` area harvested, `5510` production (tonnes),
  `5419` yield (hg/ha).
- `QCL` = crops & livestock production; `RL` = land use; `RFN` = fertilizer.

### Agmarknet

Primary path is the data.gov.in resource above (GODL). The portal itself is a
fallback.

## Egress notes (this sandbox)

- Direct HTTPS from Python is blocked; `pip` reaches a package mirror.
- `fetch_page` reaches `api.data.gov.in` (JSON) but the shared demo key returns
  `{"error": "Rate limit exceeded"}`.
- `fenixservices.fao.org` is unreachable from this sandbox.

Consequence: build/validate/test run fully offline; live pulls require the
deployment environment with internet + a data.gov.in key.
