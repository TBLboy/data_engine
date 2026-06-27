"""RDDQF-oriented L3 v2 quality assessment package.

This package implements a conservative MVP migration path from the legacy
metric-card based L3 engine to a layered training-data quality report.
"""

from .engine import L3V2Engine

__all__ = ["L3V2Engine"]
