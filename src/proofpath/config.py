"""Tunable constants. No secrets here - credentials come from the environment."""
from __future__ import annotations

# --- Model -------------------------------------------------------------------
MODEL: str = "deepseek-flash"
FALLBACK_MODEL: str = "deepseek-v4-pro"
DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
MAX_TOKENS: int = 3_000
MIN_MODEL_TOKENS: int = 2_000
MODEL_MAX_RETRIES: int = 2
MODEL_TIMEOUT_SECONDS: float = 120.0

# --- HTTP service ------------------------------------------------------------
MAX_UPLOAD_BYTES: int = 20 * 1024 * 1024
ANALYZE_TIMEOUT_SECONDS: float = 120.0

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
