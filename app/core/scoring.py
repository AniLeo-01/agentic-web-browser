"""
Scoring system for evaluating agent browsing interactions.

Five dimensions, each 0.0–1.0:
  - Completeness: Was the information found?
  - Confidence: How confident is the agent in its answer?
  - Efficiency: How few steps did it take relative to the max?
  - Speed: How fast was the run relative to a baseline?
  - Reliability: Did it complete successfully without errors?

Overall score is a weighted average of these dimensions.
"""

WEIGHTS = {
    "completeness": 0.30,
    "confidence": 0.25,
    "efficiency": 0.15,
    "speed": 0.10,
    "reliability": 0.20,
}

# Baseline: runs under this duration (seconds) get a perfect speed score
SPEED_BASELINE_SECONDS = 60.0


def compute_scores(
    found: bool,
    confidence: float,
    steps_taken: int,
    max_steps: int,
    duration_seconds: float,
    errors_encountered: int,
) -> dict:
    completeness = 1.0 if found else 0.0

    confidence_score = max(0.0, min(1.0, confidence))

    # Fewer steps = better. 1 step = 1.0, max_steps = 0.0
    if max_steps <= 1:
        efficiency = 1.0
    else:
        efficiency = max(0.0, 1.0 - (steps_taken - 1) / (max_steps - 1))

    # Faster = better. Under baseline = 1.0, scales down linearly to 0 at 5x baseline
    if duration_seconds <= SPEED_BASELINE_SECONDS:
        speed = 1.0
    else:
        speed = max(0.0, 1.0 - (duration_seconds - SPEED_BASELINE_SECONDS) / (4 * SPEED_BASELINE_SECONDS))

    # Base reliability from code errors: each error reduces by 0.25
    reliability = max(0.0, 1.0 - errors_encountered * 0.25)
    # If the task failed (not found), cap reliability at 0.5
    if not found:
        reliability = min(reliability, 0.5)

    scores = {
        "completeness": round(completeness, 3),
        "confidence": round(confidence_score, 3),
        "efficiency": round(efficiency, 3),
        "speed": round(speed, 3),
        "reliability": round(reliability, 3),
    }

    overall = sum(scores[k] * WEIGHTS[k] for k in WEIGHTS)
    scores["overall"] = round(overall, 3)

    return scores
