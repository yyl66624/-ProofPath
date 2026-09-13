"""Tunable constants. No secrets here - credentials come from the environment."""
from __future__ import annotations

# --- Model -------------------------------------------------------------------
MODEL: str = "claude-opus-5"
MAX_TOKENS: int = 16_000
EFFORT: str = "high"

# Server-side refusal fallback: on a policy decline the API retries the same
# request on a suitable fallback model inside the same call.
FALLBACK_BETA: str = "server-side-fallback-2026-07-01"

# --- Evidence verification ---------------------------------------------------
# A quote shorter than this (after normalization) is not distinctive enough to
# count as evidence: "符合" would match almost any policy page.
MIN_QUOTE_CHARS: int = 6

# Longest-common-substring coverage of the quote required to call a citation
# PARTIAL rather than NOT_FOUND.
PARTIAL_THRESHOLD: float = 0.85

# --- Retrieval ---------------------------------------------------------------
BM25_K1: float = 1.5
BM25_B: float = 0.75
DEFAULT_TOP_K: int = 6

# --- Chunking ----------------------------------------------------------------
# Page-anchored chunks: every chunk keeps the page it came from so citations
# can always name a page number.
CHUNK_CHARS: int = 900
CHUNK_OVERLAP: int = 120
