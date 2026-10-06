"""Frozen-policy evaluation. No model training or outcome-dependent selection."""

__version__ = "0.2.0"

from .core import Dataset, DecisionWeight, Reference, ValidationError
from .core import evaluate, load_csv, load_json, prioritize, validate
from .report import write_report

__all__ = ["Dataset", "DecisionWeight", "Reference", "ValidationError", "evaluate",
           "load_csv", "load_json", "prioritize", "validate", "write_report"]

