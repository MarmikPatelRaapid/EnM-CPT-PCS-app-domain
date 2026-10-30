from __future__ import annotations

from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
SYNTHETIC_DIR = ROOT_DIR / "E&M_Synthetic_data_generation"
EVIDENCE_DIR = ROOT_DIR / "E&M_evidence_predictions"
EM_DIR = ROOT_DIR / "E&M"
SYNTHETIC_PIPELINE_OUTPUT_DIR = SYNTHETIC_DIR / "output" / "pipeline_runs"
EVIDENCE_PIPELINE_OUTPUT_DIR = EVIDENCE_DIR / "output" / "pipeline_runs"
EM_PIPELINE_OUTPUT_DIR = EM_DIR / "output" / "pipeline_runs"
ROOT_PIPELINE_OUTPUT_DIR = ROOT_DIR / "pipeline_output"
