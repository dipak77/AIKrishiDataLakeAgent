"""Tests for Track 10: structured logging, correlation ids, seed-drift gate."""

from __future__ import annotations

import io
import json
import logging
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipelines import logging as plog  # noqa: E402
from scripts.verify_seeds import main as verify_seeds_main  # noqa: E402


def test_json_formatter_emits_json_line():
    fmt = plog.JsonFormatter()
    record = logging.LogRecord("agrilake.test", logging.INFO, "", 0, "hello world", None, None)
    line = fmt.format(record)
    parsed = json.loads(line)
    assert parsed["message"] == "hello world"
    assert parsed["level"] == "INFO"
    assert parsed["logger"] == "agrilake.test"
    assert "ts" in parsed


def test_correlation_id_flows():
    plog.new_correlation_id()
    cid = plog.current_correlation_id()
    assert len(cid) == 12
    # A second id differs.
    assert plog.new_correlation_id() != cid


def test_log_event_payload():
    buf = io.StringIO()
    logger = logging.getLogger("agrilake.test.event")
    logger.handlers = []
    logger.propagate = False
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(buf)
    handler.setFormatter(plog.JsonFormatter())
    logger.addHandler(handler)
    plog.log_event(logger, "ingest_ok", records=3, source="agmarknet")
    parsed = json.loads(buf.getvalue().strip())
    assert parsed["message"] == "ingest_ok"
    assert parsed["records"] == 3
    assert parsed["source"] == "agmarknet"


def test_verify_seeds_passes_on_clean_tree():
    # Committed CSVs should match seed_data.py in a clean checkout.
    assert verify_seeds_main() == 0
