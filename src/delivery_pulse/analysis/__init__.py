"""Reproducible exploratory analysis over validated DuckDB marts."""

from delivery_pulse.analysis.pipeline import AnalysisError, AnalysisResult, run_eda

__all__ = ["AnalysisError", "AnalysisResult", "run_eda"]
