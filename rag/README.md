# rag/

Vector retrieval over the gold corpus (V2+).

Plan:
- Build embeddings for `gold.research_chunk`, `gold.farmer_query`, and web RAG
  chunks (with source/license/authority metadata).
- Store in Qdrant (see `infrastructure/docker-compose.yml`).
- Retrieval returns evidence-linked facts: chunk → document → page → published,
  so Krushi Mitra can cite "Sources used: ICAR + IMD + Soil Health Card".
