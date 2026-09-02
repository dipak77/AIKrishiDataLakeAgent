# vision/

Computer-vision pipeline (V2+).

Tier A licensed research datasets (PlantDoc, PlantVillage) for:
- crop classifier, healthy/unhealthy detector, disease representation learning,
  image-quality pipeline, segmentation experiments.

Long-term most-valuable dataset: first-party farmer uploads
(crop + district + month + growth stage + description + image + AI hypothesis +
expert confirmation + final outcome).

---

## V5-C — pluggable image-diagnosis scaffold (shipped)

`vision/inference.py` is a **dependency-free** inference scaffold:

```
image bytes/path
   → decode_png()            (stdlib PNG decoder; RGB[A]/grayscale, 8/16-bit)
   → color_descriptor()      (strided HSV sampling → green/yellow/brown/black/white/red)
   → backend.predict()       (pluggable)
   → VisionCandidate[]       (keyed by gold.dim_disease / gold.dim_pest ids)
```

### Backends

| name           | status                                   |
|----------------|------------------------------------------|
| `heuristic`    | shipped — deterministic colour→symptom→ontology ranking |
| `onnx`         | stub — raises `BackendUnavailable` until weights are downloaded |
| `tflite`       | stub — `tflite-runtime` + `.tflite` weights |
| `transformers` | stub — a ViT fine-tuned on PlantVillage |

`get_backend("auto")` returns the heuristic. Real backends are an **opt-in
download** later: install the runtime (e.g. `onnxruntime`) and point a backend
at the model weights; the `VisionBackend.predict(image, crop)` contract does not
change, so `analyze_image()` keeps working unmodified.

### Usage

```python
from vision import analyze_image
res = analyze_image("leaf.png", crop="tomato")   # PNG only, out of the box
print(res.verdict)         # "healthy" | "symptomatic"
for c in res.candidates:
    print(c.entity_id, c.entity_type, c.name, c.score, c.matched)
```

```
python scripts/analyze_image.py leaf.png --crop tomato
```

PlantDoc / PlantVillage *metadata* fixtures (`data/fixtures/*_meta.json`) are
already committed; the image archives + model weights are the later opt-in
download.
