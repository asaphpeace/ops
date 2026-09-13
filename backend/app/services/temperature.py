"""
Temperature score engine.

Scale: 0 (cool / healthy) → 100 (hot / critical).
A rising temperature means the customer needs attention.

Weights:
  25%  Version age          — releases behind latest
  25%  Open critical cases  — High-priority open count
  15%  Training recurrence  — recurring gap patterns
  15%  Upgrade recency      — days since last verified upgrade
  10%  Infrastructure type  — Old / Mixed / New
  10%  Sentiment            — Frustrated / Neutral / Happy
"""


def _parse_version(v: str) -> tuple[int, ...]:
    """'8.14.2-R' → (8, 14, 2)"""
    try:
        return tuple(int(x) for x in v.split("-")[0].split(".") if x.isdigit())
    except Exception:
        return (0,)


def _version_age(prod: str | None, latest: str | None) -> float:
    """0.0 = on latest, 1.0 = very far behind."""
    if not prod or not latest:
        return 0.5
    pv, lv = _parse_version(prod), _parse_version(latest)
    if pv >= lv:
        return 0.0
    if len(pv) < 2 or len(lv) < 2:
        return 0.5
    # Each minor version behind Dataloy ≈ 2–4 weeks of risk
    minor_diff = max(0, lv[1] - pv[1]) + max(0, lv[0] - pv[0]) * 20
    return min(1.0, minor_diff * 0.08)


def _open_criticals(high_count: int) -> float:
    """0 → 0.0  |  1 → 0.4  |  2 → 0.7  |  3+ → 1.0"""
    return (0.0, 0.4, 0.7)[min(high_count, 2)] if high_count < 3 else 1.0


def _training_gaps(gap_count: int) -> float:
    return min(1.0, gap_count / 3.0)


def _upgrade_recency(days_since: int | None) -> float:
    """None (never upgraded) → 1.0.  ≤90d → 0.0.  >180d → 1.0."""
    if days_since is None:
        return 1.0
    if days_since <= 90:
        return 0.0
    if days_since <= 180:
        return 0.5
    return 1.0


def _infra(infra: str) -> float:
    return {"Old": 1.0, "Mixed": 0.5, "New": 0.0}.get(infra, 0.5)


def _sentiment(s: str) -> float:
    return {"Frustrated": 1.0, "Neutral": 0.5, "Happy": 0.0}.get(s, 0.5)


def compute(
    prod_version: str | None,
    latest_version: str | None,
    high_priority_open: int,
    training_gap_count: int,
    days_since_upgrade: int | None,
    infra: str,
    sentiment: str,
) -> int:
    """Return temperature score 0–100."""
    score = (
        _version_age(prod_version, latest_version) * 0.25
        + _open_criticals(high_priority_open) * 0.25
        + _training_gaps(training_gap_count) * 0.15
        + _upgrade_recency(days_since_upgrade) * 0.15
        + _infra(infra) * 0.10
        + _sentiment(sentiment) * 0.10
    )
    return round(score * 100)
