"""Shared test fixtures: golden scenarios from the design pattern doc, §21."""

import json
from pathlib import Path

import pytest

from research.store import WorkspaceStore


# --- Three golden scenarios (Pattern 21) ---


def _finding(
    *,
    title: str,
    details: str,
    source_name: str,
    source_url: str,
    source_language: str,
    category: str = "Energy & Oil Markets",
    impact_type: str = "Economic / Energy prices",
    related_regions: list[str] | None = None,
    date_observed: str = "2026-04-03",
    composite_score: float = 3.6,
    quality_tier: str = "Likely",
    scores: dict | None = None,
    content_hash: str | None = None,
    key_entities: list[str] | None = None,
) -> dict:
    """Build a finding-shaped dict that mirrors the on-disk schema."""
    return {
        "title": title,
        "details": details,
        "source_name": source_name,
        "source_url": source_url,
        "source_domain": source_url.split("//", 1)[-1].split("/", 1)[0].removeprefix("www."),
        "source_language": source_language,
        "category": category,
        "impact_type": impact_type,
        "related_regions": related_regions or ["Global", "Gulf States"],
        "date_observed": date_observed,
        "composite_score": composite_score,
        "quality_tier": quality_tier,
        "scores": scores
        or {
            "source_reliability": 5,
            "corroboration": 3,
            "specificity": 4,
            "recency": 5,
            "geographic_relevance": 3,
        },
        "content_hash": content_hash or f"hash_{title[:16]}",
        "key_entities": key_entities or [],
    }


@pytest.fixture
def scenario_corroboration() -> list[dict]:
    """Three sources, three languages, same Brent crude print within two days."""
    shared_entities = ["brent crude", "$127", "4.2%", "hormuz"]
    return [
        _finding(
            title="Brent crude rises 4.2% to $127/barrel after Hormuz tensions",
            details=(
                "Brent crude futures rose 4.2% to $127.30 on 2026-04-03 following "
                "Iranian naval exercises near the Strait of Hormuz."
            ),
            source_name="Reuters",
            source_url="https://www.reuters.com/markets/oil-2026-04-03",
            source_language="en",
            date_observed="2026-04-03",
            key_entities=shared_entities,
            content_hash="brent_en",
        ),
        _finding(
            title="Le Brent grimpe de 4,2% à 127 dollars le baril",
            details=(
                "Le pétrole Brent a progressé de 4,2% pour atteindre 127,30 dollars "
                "le baril après les manœuvres iraniennes près d'Ormuz."
            ),
            source_name="Le Monde",
            source_url="https://www.lemonde.fr/economie/petrole-2026-04-04",
            source_language="fr",
            date_observed="2026-04-04",
            key_entities=shared_entities,
            content_hash="brent_fr",
        ),
        _finding(
            title="ارتفاع خام برنت 4.2% إلى 127 دولاراً للبرميل",
            details=(
                "ارتفع خام برنت بنسبة 4.2٪ ليصل إلى 127.30 دولاراً للبرميل بعد "
                "المناورات الإيرانية قرب مضيق هرمز."
            ),
            source_name="Al Jazeera",
            source_url="https://www.aljazeera.net/business/oil-2026-04-04",
            source_language="ar",
            date_observed="2026-04-04",
            key_entities=shared_entities,
            content_hash="brent_ar",
        ),
    ]


@pytest.fixture
def scenario_contradiction() -> tuple[dict, dict]:
    """A prediction made on day 1 contradicted by a price print on day 14."""
    prediction = _finding(
        title="Analysts expect Brent crude to stabilise near $90 by April",
        details=(
            "JPMorgan analysts said on 2026-03-20 that Brent crude is likely to "
            "stabilise near $90 per barrel by April as Hormuz tensions ease."
        ),
        source_name="JPMorgan Research",
        source_url="https://www.jpmorgan.com/insights/oil-2026-03-20",
        source_language="en",
        date_observed="2026-03-20",
        composite_score=3.4,
        quality_tier="Likely",
        key_entities=["brent crude", "$90", "april", "hormuz"],
        content_hash="prediction_brent_90",
    )
    actual = _finding(
        title="Brent crude rises 4.2% to $127/barrel after Hormuz tensions",
        details=(
            "Brent crude futures rose 4.2% to $127.30 on 2026-04-03 following "
            "Iranian naval exercises near the Strait of Hormuz."
        ),
        source_name="Reuters",
        source_url="https://www.reuters.com/markets/oil-2026-04-03",
        source_language="en",
        date_observed="2026-04-03",
        composite_score=4.1,
        quality_tier="Verified",
        key_entities=["brent crude", "$127", "4.2%", "hormuz"],
        content_hash="brent_en",
    )
    return prediction, actual


@pytest.fixture
def scenario_stale() -> dict:
    """A fact corroborated 45 days ago, never re-validated."""
    return _finding(
        title="EU pledges 10 million euros for Iran refugee response",
        details=(
            "The European Commission announced 10 million euros in humanitarian "
            "aid for refugees fleeing the Iran conflict on 2026-02-20."
        ),
        source_name="Reuters",
        source_url="https://www.reuters.com/world/eu-iran-aid",
        source_language="en",
        category="Refugee & Humanitarian",
        impact_type="Humanitarian / Aid",
        related_regions=["Europe", "Middle East"],
        date_observed="2026-02-20",
        composite_score=3.8,
        quality_tier="Likely",
        key_entities=["european commission", "10 million euros", "iran"],
        content_hash="eu_aid_iran",
    )


# --- Store fixture ---


@pytest.fixture
def tmp_store(tmp_path: Path) -> WorkspaceStore:
    return WorkspaceStore(
        history_path=tmp_path / "findings_history.json",
        index_path=tmp_path / "findings_index.json",
        contradictions_path=tmp_path / "contradictions.jsonl",
        feedback_path=tmp_path / "feedback.jsonl",
    )


@pytest.fixture
def populated_store(
    tmp_store: WorkspaceStore,
    scenario_corroboration: list[dict],
    scenario_contradiction: tuple[dict, dict],
    scenario_stale: dict,
) -> WorkspaceStore:
    """Store seeded with all three golden scenarios."""
    prediction, actual = scenario_contradiction
    history: list[dict] = []
    history.extend(scenario_corroboration)
    # Avoid duplicating the Reuters Brent finding which appears in two scenarios.
    seen_hashes = {h["content_hash"] for h in history}
    if prediction["content_hash"] not in seen_hashes:
        history.append(prediction)
    if actual["content_hash"] not in seen_hashes:
        history.append(actual)
    history.append(scenario_stale)
    tmp_store.save_history(history)
    return tmp_store
