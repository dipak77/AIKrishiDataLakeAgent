# Roadmap

## V1 — Foundation (this repository) ✅

- 100+ canonical crops + Indian-language aliases
- All states/UTs (+ representative districts), agro-climatic/ecological zones
- Kharif/Rabi/Zaid crop mapping + phenological calendars
- Disease + pathogen, pest, weed, nutrient, fertilizer, pesticide, biocontrol,
  soil ontologies
- Source registry (governance)
- Bronze → Silver → Gold medallion pipeline + data-quality scoring
- Knowledge-graph builder + validation
- Live connector plugins (KCC, data.gov.in, Agmarknet, FAOSTAT, IMD, SHC, ICAR,
  PlantVillage, PlantDoc) with offline fixtures
- Unified agriculture record + evidence-separated recommendations + lineage
  fields

## V2 — Live ingestion + lakehouse

- Kafka/Airflow ingestion schedules for KCC, Agmarknet, IMD
- MinIO + Apache Iceberg + Trino (see `infrastructure/docker-compose.yml`)
- Postgres + PostGIS for geography joins
- Qdrant vector store + first RAG corpus build
- Full district/subdistrict/block/village geography import

## V3 — Reasoning & assistants

- Knowledge graph to Neo4j/AGE
- Krushi Mitra RAG with evidence citations
- Disease/pest diagnosis engine (symptom → candidate → environment → stage →
  visual → differential)
- Fertilizer advisory engine (crop × variety × stage × soil test → nutrient
  requirement → recommendation)
- Crop plan + mandi intelligence engines

## V4 — Vision & fine-tuning

- Vision training over Tier-A datasets + first-party farmer uploads
  (crop + district + month + stage + description + image + AI hypothesis +
  expert confirmation + outcome)
- Model fine-tuning on farmer Q&A and research chunks

## Domain coverage target (55 domains)

1–10 identification/varieties/planning/calendars/nursery/land-prep/sowing/seed
treatment/germination/transplantation; 11–14 soil science/testing/fertility/
nutrient deficiency; 15–17 fertilizers/organic/biofertilizers; 18–19 irrigation/
water; 20 weed management; 21–25 diseases/pests/nematodes/biocontrol/IPM;
26–27 growth stages/physiology; 28–30 weather/agrometeorology/climate risks;
31–35 harvest/post-harvest/storage/grading/processing; 36–38 prices/MSP/commodity
markets; 39–40 machinery/precision; 41–43 horticulture/floriculture/plantation;
44–48 livestock/dairy/poultry/fisheries/beekeeping; 49–50 schemes/insurance;
51 research; 52 farmer Q&A; 53–55 computer vision/remote sensing/satellite
agriculture.
