"""Vision inference scaffold (V5-C) — dependency-free image diagnosis.

The real ML backends (ONNX / TFLite / transformers) are *detachable*: the
interface below is stable, the weights are a later opt-in download. Until then
a **deterministic heuristic backend** is shipped and fully tested offline:

    1. decode an image (pure-Python PNG decoder — stdlib ``zlib``/``struct``)
    2. sample pixels → HSV colour descriptor (green/yellow/brown/black/white/red)
    3. map the descriptor to symptom keywords and rank the seed ontology
       (``DISEASES`` / ``PESTS`` / ``NUTRIENT_DEFICIENCIES``) by symptom overlap
    4. return ``VisionCandidate``s keyed by the same ids as ``gold.dim_disease``
       / ``gold.dim_pest``, each with provenance.

JPEG and other formats require an optional backend; PNG works out of the box.
"""

from __future__ import annotations

import os
import re
import struct
import zlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from domain.seed_data import DISEASES, NUTRIENT_DEFICIENCIES, PESTS

_PNG_SIG = b"\x89PNG\r\n\x1a\n"


class VisionError(Exception):
    """Base error for the vision pipeline."""


class BackendUnavailable(VisionError):
    """A real model backend is requested but its weights/dependency are absent."""


# ── PNG decoding (stdlib only) ────────────────────────────────────────────────
def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def _unfilter_scanline(
    ftype: int, cur: bytearray, prior: bytes, bpp: int
) -> bytearray:
    """Reverse one PNG scanline filter in place (bpp = bytes per pixel)."""
    if ftype == 0:
        return cur
    if ftype == 1:  # Sub
        for i in range(bpp, len(cur)):
            cur[i] = (cur[i] + cur[i - bpp]) & 0xFF
    elif ftype == 2:  # Up
        for i in range(len(cur)):
            cur[i] = (cur[i] + prior[i]) & 0xFF
    elif ftype == 3:  # Average
        for i in range(len(cur)):
            left = cur[i - bpp] if i >= bpp else 0
            cur[i] = (cur[i] + ((left + prior[i]) >> 1)) & 0xFF
    elif ftype == 4:  # Paeth
        for i in range(len(cur)):
            a = cur[i - bpp] if i >= bpp else 0
            b = prior[i]
            c = prior[i - bpp] if i >= bpp else 0
            cur[i] = (cur[i] + _paeth(a, b, c)) & 0xFF
    else:
        raise VisionError(f"unsupported PNG filter type {ftype}")
    return cur


def decode_png(data: bytes) -> tuple[int, int, int, bytes]:
    """Return (width, height, channels, raw RGB[A] bytes) for a non-interlaced PNG.

    Supports 8/16-bit grayscale, RGB, and RGBA. Indexed + interlaced PNGs are
    rejected with a clear message (rare in practice; decode via a backend).
    """
    if not data.startswith(_PNG_SIG):
        raise VisionError("not a PNG file")
    pos = len(_PNG_SIG)
    width = height = bit_depth = color_type = 0
    interlace = 0
    idat = bytearray()
    while pos < len(data):
        (length,) = struct.unpack(">I", data[pos : pos + 4])
        ctype = data[pos + 4 : pos + 8]
        cdata = data[pos + 8 : pos + 8 + length]
        pos += 12 + length
        if ctype == b"IHDR":
            (width, height, bit_depth, color_type, _comp, _filt, interlace) = struct.unpack(
                ">IIBBBBB", cdata
            )
        elif ctype == b"IDAT":
            idat.extend(cdata)
        elif ctype == b"IEND":
            break

    if interlace:
        raise VisionError("interlaced PNG not supported by the stdlib decoder")
    channels = {0: 1, 2: 3, 4: 2, 6: 4}.get(color_type)
    if channels is None:
        raise VisionError(f"unsupported PNG color type {color_type} (indexed?)")
    if bit_depth not in (8, 16):
        raise VisionError(f"unsupported PNG bit depth {bit_depth}")
    bpp = channels * (bit_depth // 8)

    try:
        raw = zlib.decompress(bytes(idat))
    except zlib.error as exc:  # pragma: no cover - malformed input
        raise VisionError(f"PNG IDAT decompression failed: {exc}") from exc

    stride = width * bpp
    expected = height * (1 + stride)
    if len(raw) < expected:
        raise VisionError("truncated PNG data")
    out = bytearray()
    prior = bytearray(stride)
    for y in range(height):
        ftype = raw[y * (1 + stride)]
        line = bytearray(raw[y * (1 + stride) + 1 : (y + 1) * (1 + stride)])
        out.extend(_unfilter_scanline(ftype, line, prior, bpp))
        prior = line

    # 16-bit → keep high byte; drop alpha (keep RGB or replicate gray → RGB).
    if bit_depth == 16:
        rgb = bytearray()
        if channels in (1, 2):
            for i in range(0, len(out), 2 * channels):
                rgb.append(out[i])
        else:
            for i in range(0, len(out), 2 * channels):
                rgb.extend(out[i : i + 3 : 2])
        out = rgb
        channels = 3
    if color_type in (0, 4):  # grayscale → RGB
        out = bytearray(b for b in out for _ in range(3))
        channels = 3
    elif color_type == 6:  # RGBA → RGB
        rgb = bytearray()
        for i in range(0, len(out), 4):
            rgb.extend(out[i : i + 3])
        out = rgb
        channels = 3
    return width, height, channels, bytes(out)


# ── Image abstraction ─────────────────────────────────────────────────────────
@dataclass
class Image:
    width: int
    height: int
    channels: int
    pixels: bytes  # RGB row-major

    @classmethod
    def from_bytes(cls, data: bytes) -> "Image":
        # If Pillow is installed, use it to support JPEG, WebP, PNG, etc.
        try:
            import io
            from PIL import Image as PILImage
            with PILImage.open(io.BytesIO(data)) as pimg:
                rgb_img = pimg.convert("RGB")
                w, h = rgb_img.size
                px = rgb_img.tobytes()
                return cls(w, h, 3, px)
        except ImportError:
            pass
        except Exception as exc:
            # Fall back to custom PNG decoder if PIL fails
            pass

        # Standalone stdlib PNG decoder fallback
        w, h, c, px = decode_png(data)
        return cls(w, h, c, px)

    @classmethod
    def from_path(cls, path: str | Path) -> "Image":
        return cls.from_bytes(Path(path).read_bytes())

    def pixel(self, x: int, y: int) -> tuple[int, int, int]:
        i = (y * self.width + x) * 3
        return self.pixels[i], self.pixels[i + 1], self.pixels[i + 2]

    def resize(self, new_w: int, new_h: int) -> "Image":
        """Nearest-neighbour resize (used by tests / small thumbnails)."""
        out = bytearray(new_w * new_h * 3)
        for y in range(new_h):
            sy = min(int(y * self.height / new_h), self.height - 1)
            for x in range(new_w):
                sx = min(int(x * self.width / new_w), self.width - 1)
                r, g, b = self.pixel(sx, sy)
                i = (y * new_w + x) * 3
                out[i : i + 3] = bytes((r, g, b))
        return Image(new_w, new_h, 3, bytes(out))

    def sample(self, max_pixels: int = 4096) -> list[tuple[int, int, int]]:
        """Strided pixel sampling — O(max_pixels), independent of image size."""
        stride = max(1, int((self.width * self.height / max_pixels) ** 0.5))
        out: list[tuple[int, int, int]] = []
        for y in range(0, self.height, stride):
            for x in range(0, self.width, stride):
                out.append(self.pixel(x, y))
        return out


# ── colour descriptor ─────────────────────────────────────────────────────────
def rgb_to_hsv(r: int, g: int, b: int) -> tuple[float, float, float]:
    rn, gn, bn = r / 255.0, g / 255.0, b / 255.0
    mx, mn = max(rn, gn, bn), min(rn, gn, bn)
    d = mx - mn
    h = 0.0
    if d:
        if mx == rn:
            h = 60 * (((gn - bn) / d) % 6)
        elif mx == gn:
            h = 60 * (((bn - rn) / d) + 2)
        else:
            h = 60 * (((rn - gn) / d) + 4)
    s = 0.0 if mx == 0 else d / mx
    return h % 360, s, mx


def color_descriptor(img: Image, max_pixels: int = 4096) -> dict[str, float]:
    """Fraction of sampled pixels in each symptom-relevant colour bucket."""
    n = 0
    buckets = {"green": 0, "yellow": 0, "brown": 0, "black": 0, "white": 0, "red": 0, "dark": 0}
    for r, g, b in img.sample(max_pixels):
        h, s, v = rgb_to_hsv(r, g, b)
        n += 1
        if v < 0.15:
            buckets["black"] += 1
        elif v > 0.75 and s < 0.25:
            buckets["white"] += 1
        elif 45 <= h < 70 and s > 0.30 and v > 0.40:
            buckets["yellow"] += 1
        elif 20 <= h < 45 and s > 0.25 and 0.20 <= v <= 0.65:
            buckets["brown"] += 1
        elif (h < 20 or h >= 340) and s > 0.30:
            buckets["red"] += 1
        elif 70 <= h < 160 and s > 0.12:
            buckets["green"] += 1
        if v < 0.30:
            buckets["dark"] += 1
    return {k: v / n if n else 0.0 for k, v in buckets.items()}


def _descriptor_keywords(d: dict[str, float]) -> set[str]:
    kw: set[str] = set()
    if d["green"] > 0.5 and d["yellow"] < 0.15 and d["brown"] < 0.1 and d["black"] < 0.08:
        kw.add("healthy")
    if d["yellow"] > 0.25:
        kw.update(("yellow", "yellowing", "chlorosis"))
    if d["brown"] > 0.12:
        kw.update(("brown", "spots", "necrosis", "rust"))
    if d["black"] > 0.10:
        kw.update(("black", "sooty", "spots"))
    if d["white"] > 0.18:
        kw.update(("white", "powdery", "mildew"))
    if d["red"] > 0.12:
        kw.update(("red", "spots"))
    return kw


# ── ontology scoring ──────────────────────────────────────────────────────────
@dataclass
class VisionCandidate:
    entity_id: str
    entity_type: str  # "disease" | "pest" | "deficiency"
    name: str
    score: int
    matched: list[str]
    source: str


def _score_text(kw: Iterable[str], text: str) -> tuple[int, list[str]]:
    t = (text or "").lower()
    score, matched = 0, []
    for k in kw:
        if re.search(rf"\b{re.escape(k)}\b", t):
            score += 2
            matched.append(k)
        elif k in t:
            score += 1
    return score, matched


def _ontology_rows() -> list[tuple[str, str, str, str | None, str, str]]:
    """(entity_id, entity_type, name, crop_id, crop_name, symptom_text)."""
    rows: list[tuple[str, str, str, str | None, str, str]] = []
    for d in DISEASES:
        rows.append((d["disease_id"], "disease", d["name"], d.get("crop_id"), d["crop"], d["symptoms"]))
    for p in PESTS:
        rows.append((p["pest_id"], "pest", p["name"], None, p.get("crop_hosts", ""), p["damage_symptoms"]))
    for d in NUTRIENT_DEFICIENCIES:
        name = d.get("name") or d.get("nutrient_id", "")
        rows.append((d["deficiency_id"], "deficiency", name, d.get("crop_id"), d["crop"], d["symptoms"]))
    return rows


def _resolve_crop_arg(crop: str | None) -> tuple[str | None, str | None]:
    """Return (crop_id, canonical_name) for a crop mention, if any."""
    if not crop:
        return None, None
    from pipelines.entities import resolve_crop

    row = resolve_crop(crop)
    if row:
        return row.get("crop_id"), row.get("canonical_en")
    return None, str(crop)


def score_ontology(descriptor: dict[str, float], crop: str | None = None) -> list[VisionCandidate]:
    kw = _descriptor_keywords(descriptor)
    crop_id, crop_name = _resolve_crop_arg(crop)

    def crop_matches(e_crop_id: str | None, e_crop_name: str) -> bool:
        if crop_id is None and crop_name is None:
            return True
        if e_crop_id and crop_id and e_crop_id == crop_id:
            return True
        if crop_name and e_crop_name:
            return bool(re.search(rf"\b{re.escape(crop_name.lower())}\b", e_crop_name.lower()))
        return False

    results: list[VisionCandidate] = []
    for eid, etype, name, e_crop_id, e_crop_name, text in _ontology_rows():
        if not crop_matches(e_crop_id, e_crop_name):
            continue
        score, matched = _score_text(kw, text + " " + name)
        if score > 0:
            results.append(
                VisionCandidate(
                    entity_id=eid,
                    entity_type=etype,
                    name=name,
                    score=score,
                    matched=sorted(set(matched)),
                    source="seed ontology (ICAR/extension-derived symptom text)",
                )
            )
    results.sort(key=lambda c: (-c.score, c.entity_type, c.name))
    return results


# ── pluggable backends ────────────────────────────────────────────────────────
class VisionBackend(ABC):
    name: str = "base"

    @abstractmethod
    def predict(self, image: Image, crop: str | None = None) -> list[VisionCandidate]:
        """Return ranked ontology candidates for a decoded image."""


class HeuristicColorBackend(VisionBackend):
    name = "heuristic"

    def predict(self, image: Image, crop: str | None = None) -> list[VisionCandidate]:
        return score_ontology(color_descriptor(image), crop=crop)


def _preprocess(image: Image, size: int = 224) -> list[float]:
    """Resize to (size×size) and normalize RGB → [0,1] flat float list."""
    img = image if (image.width, image.height) == (size, size) else image.resize(size, size)
    out: list[float] = []
    for y in range(size):
        for x in range(size):
            r, g, b = img.pixel(x, y)
            out.extend((r / 255.0, g / 255.0, b / 255.0))
    return out


def _labels() -> list[dict[str, str]] | None:
    """Load an optional class-label map (index → entity id/type/name) from JSON.

    ``AGRI_VISION_LABELS`` points to a JSON list of {"id", "type", "name"}.
    When absent, class indices map positionally onto the seed ontology rows.
    """
    import json

    labels_path = os.environ.get("AGRI_VISION_LABELS")
    if labels_path and Path(labels_path).is_file():
        return json.loads(Path(labels_path).read_text(encoding="utf-8"))
    return None


def _probs_to_candidates(probs: list[float], crop: str | None = None, top_k: int = 5) -> list[VisionCandidate]:
    """Map a probability vector to ranked ontology candidates."""
    labels = _labels()
    rows = _ontology_rows() if labels is None else None
    indexed = sorted(enumerate(probs), key=lambda p: -p[1])[:top_k]
    out: list[VisionCandidate] = []
    for idx, prob in indexed:
        if labels is not None and idx < len(labels):
            lab = labels[idx]
            eid, etype, name = lab.get("id", f"cls-{idx}"), lab.get("type", "disease"), lab.get("name", f"class {idx}")
        elif rows is not None and idx < len(rows):
            eid, etype, name, _ecid, _ecrop, _text = rows[idx]
        else:
            continue
        out.append(
            VisionCandidate(
                entity_id=eid,
                entity_type=etype,
                name=name,
                score=round(prob * 100, 2),
                matched=[name],
                source=f"{BackendUnavailable.__module__.split('.')[0]} model backend",
            )
        )
    return out


class OnnxBackend(VisionBackend):
    name = "onnx"
    hint = "install onnxruntime + set AGRI_VISION_MODEL (.onnx) — opt-in."

    def predict(self, image: Image, crop: str | None = None) -> list[VisionCandidate]:
        import importlib.util

        model_path = os.environ.get("AGRI_VISION_MODEL")
        if importlib.util.find_spec("onnxruntime") is None or not model_path:
            raise BackendUnavailable(f"{self.name} backend unavailable: {self.hint}")
        try:
            import numpy as np
            import onnxruntime as ort

            sess = ort.InferenceSession(model_path)
            input_name = sess.get_inputs()[0].name
            size = 224
            x = np.array(_preprocess(image, size), dtype=np.float32).reshape(1, size, size, 3)
            probs = sess.run(None, {input_name: x})[0].reshape(-1).tolist()
            return _probs_to_candidates(probs, crop)
        except BackendUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001
            raise BackendUnavailable(f"{self.name} inference failed: {exc}") from exc


class TfliteBackend(VisionBackend):
    name = "tflite"
    hint = "install tflite-runtime + set AGRI_VISION_MODEL (.tflite) — opt-in."

    def predict(self, image: Image, crop: str | None = None) -> list[VisionCandidate]:
        import importlib.util

        model_path = os.environ.get("AGRI_VISION_MODEL")
        if importlib.util.find_spec("tflite_runtime") is None or not model_path:
            raise BackendUnavailable(f"{self.name} backend unavailable: {self.hint}")
        try:
            import numpy as np
            from tflite_runtime.interpreter import Interpreter  # type: ignore

            interp = Interpreter(model_path=model_path)
            interp.allocate_tensors()
            in_details = interp.get_input_details()[0]
            out_details = interp.get_output_details()[0]
            size = in_details["shape"][1]
            x = np.array(_preprocess(image, size), dtype=np.float32).reshape(in_details["shape"])
            interp.set_tensor(in_details["index"], x)
            interp.invoke()
            probs = interp.get_tensor(out_details["index"]).reshape(-1).tolist()
            return _probs_to_candidates(probs, crop)
        except BackendUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001
            raise BackendUnavailable(f"{self.name} inference failed: {exc}") from exc


class TransformersBackend(VisionBackend):
    name = "transformers"
    hint = "install transformers+torch and set AGRI_VISION_MODEL (HF model id) — opt-in."

    def predict(self, image: Image, crop: str | None = None) -> list[VisionCandidate]:
        import importlib.util

        model_id = os.environ.get("AGRI_VISION_MODEL")
        if importlib.util.find_spec("transformers") is None or not model_id:
            raise BackendUnavailable(f"{self.name} backend unavailable: {self.hint}")
        try:
            from PIL import Image as PILImage  # type: ignore
            from transformers import pipeline  # type: ignore

            size = 224
            img = image if (image.width, image.height) == (size, size) else image.resize(size, size)
            pil = PILImage.frombytes("RGB", (img.width, img.height), img.pixels)
            classifier = pipeline("image-classification", model=model_id)
            scored = classifier(pil, top_k=5)
            # HF returns {"label": ..., "score": ...}; map label → ontology by name.
            labels = _labels()
            rows = _ontology_rows() if labels is None else None
            out: list[VisionCandidate] = []
            for item in scored:
                label = item["label"]
                eid = etype = name = None
                if labels is not None:
                    lab = next((l for l in labels if l.get("name") == label), None)
                    if lab:
                        eid, etype, name = lab["id"], lab.get("type", "disease"), label
                else:
                    row = next((r for r in rows or [] if r[2] == label), None)
                    if row:
                        eid, etype, name = row[0], row[1], row[2]
                if eid:
                    out.append(
                        VisionCandidate(
                            entity_id=eid, entity_type=etype, name=name,
                            score=round(item["score"] * 100, 2), matched=[name],
                            source="transformers model backend",
                        )
                    )
            return out
        except BackendUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001
            raise BackendUnavailable(f"{self.name} inference failed: {exc}") from exc


_BACKENDS: dict[str, type[VisionBackend]] = {
    "heuristic": HeuristicColorBackend,
    "onnx": OnnxBackend,
    "tflite": TfliteBackend,
    "transformers": TransformersBackend,
}


def get_backend(name: str | None = "auto") -> VisionBackend:
    """Resolve a backend by name. 'auto'/None → the deterministic heuristic."""
    if name in ("auto", "heuristic", None):
        return HeuristicColorBackend()
    cls = _BACKENDS.get(name)
    if cls is None:
        raise BackendUnavailable(
            f"unknown backend {name!r}; available: {sorted(_BACKENDS)}"
        )
    return cls()


# ── orchestrator ──────────────────────────────────────────────────────────────
@dataclass
class VisionResult:
    source: str
    width: int
    height: int
    channels: int
    backend: str
    descriptor: dict[str, float]
    verdict: str  # "healthy" | "symptomatic"
    crop: str | None
    candidates: list[VisionCandidate] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "width": self.width,
            "height": self.height,
            "channels": self.channels,
            "backend": self.backend,
            "descriptor": self.descriptor,
            "verdict": self.verdict,
            "crop": self.crop,
            "candidates": [
                {
                    "entity_id": c.entity_id,
                    "entity_type": c.entity_type,
                    "name": c.name,
                    "score": c.score,
                    "matched": c.matched,
                    "source": c.source,
                }
                for c in self.candidates
            ],
        }


def analyze_image(
    source: str | Path | bytes,
    *,
    crop: str | None = None,
    backend: str = "auto",
    top_k: int = 5,
) -> VisionResult:
    """Decode an image and return a structured, provenance-carrying diagnosis.

    ``source`` is a PNG path or raw PNG bytes (other formats need a backend).
    """
    if isinstance(source, (str, Path)):
        img = Image.from_path(source)
        src_label = str(source)
    else:
        img = Image.from_bytes(source)
        src_label = "<bytes>"

    backend_obj = get_backend(backend)
    descriptor = color_descriptor(img)
    candidates = backend_obj.predict(img, crop=crop)[:top_k]
    verdict = "healthy" if "healthy" in _descriptor_keywords(descriptor) and not candidates else "symptomatic"
    return VisionResult(
        source=src_label,
        width=img.width,
        height=img.height,
        channels=img.channels,
        backend=backend_obj.name,
        descriptor={k: round(v, 4) for k, v in descriptor.items()},
        verdict=verdict,
        crop=crop,
        candidates=candidates,
    )
