"""One-shot autonomous build for the Agri Intelligence Lake.

    python scripts/bootstrap.py          # configure → venv → seed → gold → validate → test
    python scripts/bootstrap.py --check  # doctor: environment + health report only
    python scripts/bootstrap.py --skip test

The script is dependency-free (stdlib only): it can bootstrap its own virtual
environment, install the package, then re-run the build steps with the venv
interpreter. Every step is a subprocess, so a failure in one step is isolated,
reported, and reflected in the exit code.

Outputs:
    data/lake/_bootstrap_report.json     machine-readable build report
"""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipelines.config import detect_capabilities, describe, load_settings  # noqa: E402
from pipelines.storage import ensure_dir, utcnow_iso, write_json  # noqa: E402

VENV_DIR = ROOT / ".venv"
VENV_PY = VENV_DIR / "bin" / "python"
if sys.platform == "win32":
    VENV_PY = VENV_DIR / "Scripts" / "python.exe"

MIN_PY = (3, 10)

# Ordered build steps. Each is (name, argv-suffix) executed with the venv python.
STEPS: list[tuple[str, list[str]]] = [
    ("seed", ["scripts/seed_lake.py"]),
    ("gold", ["scripts/build_gold.py"]),
    ("validate", ["scripts/validate.py"]),
    ("test", ["-m", "pytest", "-q"]),
]


def _running_under_venv() -> bool:
    return VENV_PY.exists() and Path(sys.executable).resolve() == VENV_PY.resolve()


def ensure_venv() -> Path:
    """Create the virtualenv and install the package if missing. Returns the python path."""
    if not VENV_PY.exists():
        print(f"[bootstrap] creating virtualenv at {VENV_DIR} …")
        subprocess.run([sys.executable, "-m", "venv", str(VENV_DIR)], check=True)
    subprocess.run(
        [str(VENV_PY), "-m", "pip", "install", "--upgrade", "pip"],
        check=False, capture_output=True,
    )
    proc = subprocess.run(
        [str(VENV_PY), "-m", "pip", "install", "-e", ".[dev]"],
        cwd=str(ROOT), capture_output=True, text=True,
    )
    if proc.returncode != 0:
        print("[bootstrap] pip install failed (offline or no PyPI access):")
        print((proc.stdout or "")[-1200:] or (proc.stderr or "")[-1200:])
        print("           build steps will report the missing dependencies.")
    return VENV_PY


def collect_environment(*, probe_net: bool) -> dict[str, Any]:
    settings = load_settings()
    return {
        "python_version": platform.python_version(),
        "python_ok": sys.version_info[:2] >= MIN_PY,
        "executable": sys.executable,
        "venv": str(VENV_DIR),
        "in_venv": _running_under_venv(),
        "config": describe(settings),
        "capabilities": detect_capabilities(settings, probe_net=probe_net),
    }


def run_steps(venv_py: Path, skip: set[str]) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    for name, argv in STEPS:
        if name in skip:
            steps.append({"name": name, "status": "skipped"})
            continue
        started = time.perf_counter()
        proc = subprocess.run(
            [str(venv_py), *argv], cwd=str(ROOT), capture_output=True, text=True
        )
        duration = round(time.perf_counter() - started, 2)
        detail = (proc.stdout or "")[-2000:] or (proc.stderr or "")[-2000:]
        step = {
            "name": name,
            "status": "ok" if proc.returncode == 0 else "failed",
            "returncode": proc.returncode,
            "duration_s": duration,
            "detail": detail.strip(),
        }
        print(f"  [{step['status']:<7}] {name:<9} {duration:>6}s")
        if proc.returncode != 0:
            print(f"           --- last output ---\n{detail}\n           --- end output ---")
        steps.append(step)
    return steps


def summarize(report: dict[str, Any]) -> str:
    lines = ["Bootstrap summary"]
    env = report["environment"]
    lines.append(f"  python {env['python_version']} (>=3.10: {'yes' if env['python_ok'] else 'no'})")
    lines.append(f"  {env['config']}")
    caps = env["capabilities"]
    pkg = caps.get("optional_packages", {})
    lines.append(
        "  packages: " + ", ".join(f"{k}={ 'ok' if v else 'missing'}" for k, v in pkg.items())
    )
    if caps.get("network") is not None:
        lines.append(f"  network: {'reachable' if caps['network'] else 'offline/blocked'}")
    if report.get("steps"):
        ok = sum(1 for s in report["steps"] if s["status"] == "ok")
        lines.append(f"  steps: {ok}/{len(report['steps'])} ok")
    lines.append(f"  overall: {'OK' if report['ok'] else 'FAILED'}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Autonomous lake build + health check")
    parser.add_argument(
        "--check", action="store_true",
        help="environment + health report only (no build steps)",
    )
    parser.add_argument(
        "--skip", nargs="*", default=[],
        choices=[name for name, _ in STEPS], help="steps to skip",
    )
    parser.add_argument(
        "--no-venv", action="store_true",
        help="do not auto-create the virtualenv",
    )
    args = parser.parse_args(argv)

    env = collect_environment(probe_net=args.check)
    print("Agri Intelligence Lake — autonomous build")
    print(f"  python {env['python_version']} | {env['config']}")

    if not env["python_ok"]:
        print(f"  [fail] Python {MIN_PY[0]}.{MIN_PY[1]}+ required.")
        return 1

    if args.check:
        print(summarize({"environment": env, "steps": [], "ok": True}))
        return 0

    # Ensure we run under the project venv (self-bootstrap).
    if not _running_under_venv() and not args.no_venv:
        print("[bootstrap] not under project venv — self-bootstrapping …")
        venv_py = ensure_venv()
        result = subprocess.run(
            [str(venv_py), str(__file__), *sys.argv[1:]], cwd=str(ROOT)
        )
        return result.returncode
    venv_py = VENV_PY if _running_under_venv() else Path(sys.executable)

    print("\n[bootstrap] running build steps …")
    steps = run_steps(venv_py, set(args.skip))
    ok = all(s["status"] in ("ok", "skipped") for s in steps)

    report = {
        "generated_at": utcnow_iso(),
        "environment": env,
        "steps": steps,
        "ok": ok,
    }
    report_path = write_json(ensure_dir(ROOT / "data" / "lake") / "_bootstrap_report.json", report)
    print(f"\n{summarize(report)}")
    print(f"report -> {report_path}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
