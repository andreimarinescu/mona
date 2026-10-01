"""C6 knobs: the prompt version, caps, and the environment settings (C9 §6.7)."""

import os
from datetime import timedelta
from typing import Literal

PROMPT_VERSION = "c6-v2"
MAX_CANDIDATES = 40
MAX_SEED_COUNTERPARTIES = 7
MAX_QUESTIONS = 7
JOB_CAP_S = 150.0
STALE_AFTER = timedelta(minutes=10)
PASS2_TIMEOUT_S = 60.0
MAX_TARGETED = 3
TARGETED_TIMEOUT_S = 30.0

CacheMode = Literal["off", "fallback", "prefer"]


def pass1_budget_s() -> float:
    return float(os.environ.get("MONA_INTERVIEW_PASS1_BUDGET_S", "35"))


def cache_mode() -> CacheMode:
    mode = os.environ.get("MONA_DEBRIEF_CACHE", "fallback")
    return mode if mode in ("off", "fallback", "prefer") else "fallback"  # type: ignore[return-value]


def cache_after_s() -> float:
    return float(os.environ.get("MONA_DEBRIEF_CACHE_AFTER_S", "60"))
