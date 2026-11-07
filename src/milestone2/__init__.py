"""Milestone 2 plugin for the unchanged Milestone 1 crawler and on-disk corpus."""
from .pipeline import Milestone2Parser, Milestone2MemorySampler
__all__ = ['Milestone2Parser', 'Milestone2MemorySampler']
