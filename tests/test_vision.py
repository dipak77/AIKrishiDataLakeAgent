"""Tests for V5-C: dependency-free vision inference scaffold."""

from __future__ import annotations

import struct
import sys
import zlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from vision.inference import (  # noqa: E402
    BackendUnavailable,
    HeuristicColorBackend,
    Image,
    _paeth,
    _unfilter_scanline,
    analyze_image,
    color_descriptor,
    decode_png,
    get_backend,
    rgb_to_hsv,
    score_ontology,
)


# ── minimal PNG encoder for tests ─────────────────────────────────────────────
def _chunk(typ: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + typ
        + data
        + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF)
    )


def _png_rgb(w: int, h: int, pixel_fn) -> bytes:
    raw = bytearray()
    for y in range(h):
        raw.append(0)  # filter type 0 (None)
        for x in range(w):
            raw.extend(pixel_fn(x, y))
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", zlib.compress(bytes(raw)))
        + _chunk(b"IEND", b"")
    )


def _solid(rgb: tuple[int, int, int], w: int = 16, h: int = 16) -> Image:
    return Image.from_bytes(_png_rgb(w, h, lambda x, y: rgb))


# ── PNG decode ────────────────────────────────────────────────────────────────
def test_png_roundtrip():
    img = _solid((12, 200, 34), 5, 4)
    assert (img.width, img.height, img.channels) == (5, 4, 3)
    assert img.pixel(0, 0) == (12, 200, 34)
    assert img.pixel(4, 3) == (12, 200, 34)


def test_png_multi_pixel_pattern():
    img = Image.from_bytes(
        _png_rgb(3, 2, lambda x, y: (x * 100, y * 100, 255 - x * 50))
    )
    assert img.pixel(0, 0) == (0, 0, 255)
    assert img.pixel(2, 1) == (200, 100, 155)


def test_png_rejects_non_png():
    with pytest.raises(Exception):
        Image.from_bytes(b"not a png at all")


def test_paeth_identity():
    for a in range(0, 256, 17):
        assert _paeth(a, a, a) == a


def test_unfilter_sub():
    # Sub: cur[i] += cur[i-bpp]; craft a 1-pixel-wide 3-channel line
    cur = bytearray([10, 20, 30, 40])
    out = _unfilter_scanline(1, cur, bytes(4), 3)
    assert bytes(out) == bytes([10, 20, 30, 40 + 10])


def test_unfilter_up():
    prior = bytes([1, 2, 3, 4])
    cur = bytearray([10, 10, 10, 10])
    out = _unfilter_scanline(2, cur, prior, 4)
    assert bytes(out) == bytes([11, 12, 13, 14])


# ── resize / sampling ─────────────────────────────────────────────────────────
def test_resize_downsample():
    img = _solid((255, 0, 0), 4, 4).resize(2, 2)
    assert (img.width, img.height) == (2, 2)
    assert img.pixel(0, 0) == (255, 0, 0)
    assert img.pixel(1, 1) == (255, 0, 0)


# ── colour descriptor ─────────────────────────────────────────────────────────
def test_rgb_to_hsv_basic():
    h, s, v = rgb_to_hsv(255, 0, 0)
    assert abs(h - 0) < 1e-6 and s == 1.0 and v == 1.0
    h, s, v = rgb_to_hsv(0, 255, 0)
    assert abs(h - 120) < 1e-6


def test_descriptor_green_is_healthy():
    d = color_descriptor(_solid((20, 180, 40)))
    assert d["green"] > 0.9
    assert d["yellow"] < 0.05 and d["brown"] < 0.05


def test_descriptor_yellow():
    d = color_descriptor(_solid((250, 230, 30)))
    assert d["yellow"] > 0.5


def test_descriptor_black():
    d = color_descriptor(_solid((5, 5, 5)))
    assert d["black"] > 0.9


# ── ontology scoring / orchestration ──────────────────────────────────────────
def test_healthy_image_has_no_candidates():
    res = analyze_image(_png_rgb(12, 12, lambda x, y: (20, 180, 40)))
    assert res.verdict == "healthy"
    assert res.candidates == []
    assert res.backend == "heuristic"


def test_yellow_image_surfaces_yellowing_entities():
    res = analyze_image(_png_rgb(12, 12, lambda x, y: (250, 230, 30)))
    assert res.verdict == "symptomatic"
    assert res.candidates, "yellow/chlorosis image should match ontology entries"
    top = res.candidates[0]
    assert top.entity_id and top.entity_type in {"disease", "pest", "deficiency"}
    assert any("yellow" in m for m in top.matched)


def test_brown_spots_image_matches_brown():
    img = _png_rgb(12, 12, lambda x, y: (120, 60, 20) if x < 8 else (20, 160, 40))
    res = analyze_image(img)
    assert res.verdict == "symptomatic"
    assert any("brown" in m or "spots" in m for c in res.candidates for m in c.matched)


def test_crop_filter():
    res = analyze_image(
        _png_rgb(12, 12, lambda x, y: (250, 230, 30)), crop="tomato"
    )
    assert res.crop == "tomato"
    # every candidate must be tomato-scoped (ids embed the crop, e.g. DIS_TOMATO_*)
    assert res.candidates, "expected tomato-scoped candidates"
    assert all("tomato" in c.entity_id.lower() for c in res.candidates)


def test_score_ontology_crop_scoped():
    d = color_descriptor(_solid((250, 230, 30)))
    all_cands = score_ontology(d)
    tomato_cands = score_ontology(d, crop="tomato")
    assert len(tomato_cands) <= len(all_cands)


def test_result_serializes():
    res = analyze_image(_png_rgb(8, 8, lambda x, y: (250, 230, 30)))
    d = res.as_dict()
    assert set(d) >= {"verdict", "descriptor", "candidates", "backend", "width", "height"}


# ── backend registry ──────────────────────────────────────────────────────────
def test_backend_registry():
    assert isinstance(get_backend("heuristic"), HeuristicColorBackend)
    assert isinstance(get_backend("auto"), HeuristicColorBackend)
    assert get_backend(None).name == "heuristic"


def test_backend_unavailable_stubs():
    for name in ("onnx", "tflite", "transformers"):
        with pytest.raises(BackendUnavailable):
            get_backend(name).predict(_solid((0, 0, 0)))
    with pytest.raises(BackendUnavailable):
        get_backend("does-not-exist")
