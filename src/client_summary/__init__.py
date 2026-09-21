"""Client-friendly six-page AI visibility summary (the LS report)."""
from .model import ReportValidationError, from_records, metrics, validate_report
from .pdf import ReportLayoutError, render_pdf

__all__ = [
    "ReportLayoutError", "ReportValidationError", "from_records", "metrics",
    "render_pdf", "validate_report",
]
