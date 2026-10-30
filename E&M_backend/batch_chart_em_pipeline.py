from __future__ import annotations

import json
import sys
from pathlib import Path

from streamlined_pipeline.em_resolution_step import EMResolutionStep
from streamlined_pipeline.module_loader import load_module
from streamlined_pipeline.paths import EVIDENCE_DIR

# ----------------------------
# Update these paths as needed.
# ----------------------------
INPUT_CHART_DIR = Path("/home/raghav/workspace/E&M_backend/data/input_text")
EM_EVIDENCE_JSON_DIR = Path("/home/raghav/workspace/E&M_backend/data/evidence_output")
EM_CODE_JSON_DIR = Path("/home/raghav/workspace/E&M_backend/data/E&M_code_output")


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _iter_chart_files(chart_dir: Path) -> list[Path]:
    if not chart_dir.exists():
        raise FileNotFoundError(f"Input chart directory not found: {chart_dir}")
    if not chart_dir.is_dir():
        raise NotADirectoryError(f"Input chart path is not a directory: {chart_dir}")
    return sorted(path for path in chart_dir.glob("*.txt") if path.is_file())


def run_pipeline(
    input_chart_dir: Path = INPUT_CHART_DIR,
    evidence_json_dir: Path = EM_EVIDENCE_JSON_DIR,
    em_code_json_dir: Path = EM_CODE_JSON_DIR,
) -> None:
    chart_files = _iter_chart_files(input_chart_dir)
    if not chart_files:
        print(f"No .txt files found in: {input_chart_dir}")
        return

    evidence_module = load_module(
        "chart_batch_evidence_model_inference_module",
        EVIDENCE_DIR / "model_inference.py",
    )
    evidence_predictor = evidence_module.generate_from_documents
    em_step = EMResolutionStep()

    for chart_file in chart_files:
        chart_text = chart_file.read_text(encoding="utf-8")
        print(f"Processing: {chart_file.name}")

        # Evidence service expects a list of documents under this shape.
        evidence_payload = evidence_predictor([{"generated_document": chart_text}])
        evidence_output_path = evidence_json_dir / f"{chart_file.stem}.json"
        _write_json(evidence_output_path, evidence_payload)
        print(f"  Saved evidence JSON: {evidence_output_path}")

        em_output = em_step.run(evidence_payload)
        em_output_path = em_code_json_dir / f"{chart_file.stem}.json"
        _write_json(em_output_path, em_output)
        print(f"  Saved E&M code JSON: {em_output_path}")

    print("Pipeline run completed successfully.")


if __name__ == "__main__":
    try:
        run_pipeline()
    except Exception as exc:  # pragma: no cover
        print(f"Pipeline failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
