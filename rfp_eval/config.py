"""Central configuration. Everything can be overridden with environment variables
(or Streamlit secrets, which are exported to the environment by app.py)."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("RFP_DB_PATH", BASE_DIR / "data" / "rfp_eval.db"))

# Text sent to the LLM is truncated beyond this many characters (a warning is recorded).
MAX_DOC_CHARS = 60_000
# A PDF with less extractable text than this is treated as scanned / empty.
MIN_DOC_CHARS = 300
# Attempts per supplier when the LLM returns unparseable output.
MAX_LLM_ATTEMPTS = 2

# Weight total of active criteria must equal this (percent), within WEIGHT_TOLERANCE.
WEIGHT_TOTAL = 100.0
WEIGHT_TOLERANCE = 0.01

# Experience rating scale shown in the UI.
EXPERIENCE_MIN, EXPERIENCE_MAX = 0.0, 10.0

# Rounding used ONLY for sort keys, so float noise can never change an ordering.
SORT_PRECISION = 6

DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-5-5"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
