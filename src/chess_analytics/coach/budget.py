"""Configuration only; this module never reads secrets or authorizes spending.

Future live runs require personal-account acknowledgement, an explicit run
cap, the manual GitHub live-eval environment, and runtime Doppler secrets
from project chess-analytics-lab. No live runner ships in this slice.
"""

FIRST_LIVE_COACH_MODEL = "grok-4.7"
FIRST_LIVE_COACH_CAP_USD = 5.0
JUDGE_MODEL_ID = "gpt-6-luna"
