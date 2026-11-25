"""Score every model on the same questions and store an Inspect-shaped log.

Inspect, from the UK AI Security Institute, is the open-source record used here:

https://inspect.aisi.org.uk/eval-logs.html

A run has a dataset, a solver, and scorers. Each sample stores the input, the
target, the model output, and a score of C (correct) or I (incorrect). The
dataset is the six questions in pipeline.check_accuracy. The solver is
pipeline.chat.reply. The scorers are the number, quotation, and slice checks
already used under each chat answer.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from pipeline.check_accuracy import CASES
from pipeline.chat import reply

REFERENCE = "https://inspect.aisi.org.uk/eval-logs.html"
SCORERS = ("numbers", "quotations", "slice")
FILTERED = "Filtered counts"


def scenarios() -> list[dict]:
    rows = []
    for case in CASES:
        rows.append(
            {
                "id": case["id"],
                "input": case["question"],
                "target": _target(case),
            }
        )
    return rows


def scenario_by_id(scenario_id: str) -> dict | None:
    for scenario in scenarios():
        if scenario["id"] == scenario_id:
            return scenario
    return None


def run_sample(records, scenario_id: str, settings: dict, *, model: str, use_model: bool) -> dict:
    """One Inspect sample. A failed model call is incorrect, not a filtered pass."""
    scenario = scenario_by_id(scenario_id)
    if scenario is None:
        raise KeyError(scenario_id)
    started = time.perf_counter()
    started_at = _now()
    call = dict(settings)
    label = model.strip() or (call.get("model") or "")
    if use_model:
        if label:
            call["model"] = label
    else:
        call["api_key"] = ""
        label = FILTERED
    outcome = reply(records, scenario["input"], call)
    elapsed = round(time.perf_counter() - started, 3)
    text = outcome.get("text") or ""
    failed = use_model and outcome.get("source") != "model"
    note = ""
    accuracy = outcome.get("accuracy") or {}
    if failed:
        note = accuracy.get("note") or "The model did not return a summary."
    checks = {}
    for check in accuracy.get("checks") or []:
        name = str(check.get("label") or "").strip().lower()
        if name:
            checks[name] = check
    scores = {}
    for name in SCORERS:
        check = checks.get(name) or {}
        ok = bool(check.get("ok")) and not failed
        scores[name] = {
            "value": "C" if ok else "I",
            "answer": text[:500],
            "explanation": note or check.get("detail") or "This check did not run.",
        }
    if not accuracy and not failed:
        for name in scores:
            scores[name] = {
                "value": "I",
                "answer": text[:500],
                "explanation": text or "This check did not run.",
            }
    return {
        "id": f"{scenario['id']}::{label}",
        "epoch": 1,
        "input": scenario["input"],
        "target": scenario["target"],
        "output": {"completion": text, "model": label},
        "scores": scores,
        "metadata": {
            "scenario": scenario["id"],
            "model": label,
            "source": outcome.get("source") or "",
            "support": outcome.get("support"),
        },
        "started_at": started_at,
        "completed_at": _now(),
        "total_time": elapsed,
        "uuid": uuid.uuid4().hex,
        "error": note or None,
        "ok": all(item["value"] == "C" for item in scores.values()) and not failed,
    }


class EvalStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()

    def list_public(self) -> list[dict]:
        with self._lock:
            runs = self._read()
        return [self.summary(run) for run in runs]

    def get(self, run_id: str) -> dict | None:
        with self._lock:
            for run in self._read():
                if run.get("id") == run_id:
                    return run
        return None

    def start(self, models: list[dict]) -> dict:
        now = _now()
        run = {
            "version": 2,
            "status": "started",
            "id": uuid.uuid4().hex[:12],
            "expected": len(scenarios()) * len(models),
            "eval": {
                "task": "uds-advantage",
                "model": [item["name"] for item in models],
                "created": now,
                "dataset": "pipeline.check_accuracy.CASES",
                "reference": REFERENCE,
            },
            "plan": {
                "solver": "pipeline.chat.reply",
                "scorers": list(SCORERS),
                "models": models,
            },
            "results": None,
            "samples": [],
        }
        with self._lock:
            runs = self._read()
            runs.insert(0, run)
            self._write(runs[:20])
        return run

    def add_sample(self, run_id: str, sample: dict) -> dict | None:
        with self._lock:
            runs = self._read()
            run = next((item for item in runs if item.get("id") == run_id), None)
            if run is None:
                return None
            samples = [item for item in run.get("samples") or [] if item.get("id") != sample.get("id")]
            samples.append(sample)
            run["samples"] = samples
            run["results"] = _results(samples)
            if len(samples) >= int(run.get("expected") or 0):
                run["status"] = "success"
            self._write(runs)
            return run

    def summary(self, run: dict) -> dict:
        return {
            "id": run.get("id"),
            "status": run.get("status"),
            "created": (run.get("eval") or {}).get("created") or "",
            "models": (run.get("eval") or {}).get("model") or [],
            "results": run.get("results"),
            "n": len(run.get("samples") or []),
            "expected": run.get("expected") or 0,
            "reference": REFERENCE,
        }

    def _read(self) -> list:
        if not self.path.is_file():
            return []
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
        runs = payload.get("runs") if isinstance(payload, dict) else None
        return list(runs) if isinstance(runs, list) else []

    def _write(self, runs: list) -> None:
        self.path.parent.mkdir(exist_ok=True)
        self.path.write_text(json.dumps({"runs": runs}, ensure_ascii=False, indent=2), encoding="utf-8")


def _results(samples: list[dict]) -> dict:
    names = []
    for sample in samples:
        label = (sample.get("output") or {}).get("model") or ""
        if label and label not in names:
            names.append(label)
    by_model = {}
    for label in names:
        group = [sample for sample in samples if (sample.get("output") or {}).get("model") == label]
        metrics = {}
        for scorer in SCORERS:
            correct = sum(1 for sample in group if (sample.get("scores") or {}).get(scorer, {}).get("value") == "C")
            metrics[scorer] = {"correct": correct, "n": len(group)}
        by_model[label] = {
            "n": len(group),
            "correct": sum(1 for sample in group if sample.get("ok")),
            "metrics": metrics,
        }
    return {"scorers": list(SCORERS), "by_model": by_model}


def _target(case: dict) -> str:
    parts = []
    if case.get("support"):
        parts.append(f"support={case['support']}")
    if case.get("mode"):
        parts.append(f"mode={case['mode']}")
    if case.get("lead"):
        parts.append(f"lead={case['lead']}")
    if case.get("slices"):
        parts.append(f"slices={case['slices']}")
    if case.get("quotes") is True:
        parts.append("quotations required")
    if case.get("quotes") is False:
        parts.append("no quotations")
    return "; ".join(parts)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
