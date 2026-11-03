"""Reputation multi-source data acquisition framework (v2)."""
from .config import ExtractionConfig, SUPPORTED_SOURCES
from .pipeline import run_pipeline, SourceResult

__all__ = ['ExtractionConfig', 'SUPPORTED_SOURCES', 'run_pipeline', 'SourceResult']
