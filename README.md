# Open Source AI Research Tools

An autonomous, locally-hosted OSINT research agent that searches the web in multiple languages, uses a local LLM to extract structured findings, scores them against a multi-dimensional validation matrix, detects contradictions across time, and surfaces what to look at first via a daily briefing.

Built for tracking secondary global impacts of geopolitical events -- economic, humanitarian, political, supply chain, and security effects that ripple outward from a conflict zone.

The system follows the *Distributed Interpreter Workflows* pattern language: a durable substrate of structured memory, specialised modules for each concern, and an interpreter surface (the briefing) that synthesises rather than commands. Humans stay accountable for decisions; the agent is read-mostly.

## What It Does

- **Searches the web in 7 languages** (English, Farsi, Arabic, Turkish, Russian, Chinese, French) using DuckDuckGo with region-specific targeting
- **Extracts structured findings** using a local 31B parameter LLM (Google Gemma 4 via Ollama) -- no data sent to cloud AI services
- **Scores every finding** across 5 independent dimensions: Source Reliability, Corroboration, Specificity, Recency, and Geographic Relevance
- **Rejects low-quality findings** below a configurable threshold, preserving them in an audit trail
- **Deduplicates** across runs using content hashing
- **Builds corroboration over time** -- findings confirmed by multiple independent sources across languages climb in trust score
- **Detects contradictions** -- when a new finding shares entities with a prior one but disagrees on direction, magnitude, or negation, an alert is recorded
- **Renders a daily briefing** -- read-only synthesis with salience ranking, open contradictions, stale claims, and an anti-confabulation envelope (coverage, gaps, confidence)
- **Runs autonomously** on a schedule (macOS launchd) with no manual intervention

## Scoring Matrix

Each finding receives a composite score (1.0-5.0) from five weighted dimensions:

| Dimension | Weight | What It Measures |
|-----------|--------|-----------------|
| Source Reliability | 30% | Curated authority database of 90+ news sources across 7 languages |
| Corroboration | 25% | Multiple independent sources reporting the same claim (within-run + historical) |
| Specificity | 20% | Concrete data markers: numbers, dates, named entities (regex-based) |
| Recency | 15% | How fresh the finding is relative to the run date |
| Geographic Relevance | 10% | Source region alignment with the finding's affected regions |

**Quality Tiers:**
- **Verified** (>=4.0) -- Multiple corroborating sources, high reliability
- **Likely** (3.0-3.9) -- Good source with some corroboration
- **Unverified** (2.0-2.9) -- Logged with caveat
- **Unreliable** (<2.0) -- Rejected, audit trail only

All scoring is regex + dictionary lookups + set operations. Zero additional LLM calls. <1 second overhead per run.

## Requirements

- **Hardware**: Apple Silicon Mac with 24GB+ unified memory (36GB recommended for 31B model)
- **Ollama**: v0.20.0+ with Gemma 4 31B pulled (`ollama pull gemma4:31b`)
- **Python**: 3.12+
- **Dependencies**: `ollama`, `duckduckgo-search`, `pyyaml` (3 packages total)

## Quick Start

```bash
# Clone
git clone https://github.com/marketimpact/opensource_airesearchtools.git
cd opensource_airesearchtools

# Setup
python3 -m venv .venv
source .venv/bin/activate
pip install ollama duckduckgo-search pyyaml

# Pull the model (19GB download)
ollama pull gemma4:31b

# Edit configs/research-agent.yaml to customize your queries and categories

# Run a research cycle (search + extract + score + dedup + contradiction sweep)
python3 -m research.agent

# Read today's briefing (read-only, never writes to history)
python3 -m research.brief

# Backfill contradictions over existing history
python3 -m research.contradictions

# Mark a finding useful / noise / pinned / snoozed / resolved
python3 -m research.feedback add <content_hash> useful
python3 -m research.feedback list
```

## Configuration

### `configs/research-agent.yaml`
Main configuration: model, search queries (119 templates across 7 languages and 7 categories), scoring weights, and scheduling options. **Edit the queries and categories to match your research topic.**

### `configs/source-authority.yaml`
Curated database of 90+ news source domains with reliability tiers (1-5). Covers major outlets across English, French, Arabic, Turkish, Russian, Chinese, and Farsi, plus international organizations (UN, IMF, IAEA, etc.).

### Scheduling (macOS)
```bash
# Edit the plist to set your project path
vim configs/com.localai.research-agent.plist

# Install (runs every 4 hours)
cp configs/com.localai.research-agent.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.localai.research-agent.plist

# Trigger manually
launchctl kickstart gui/$(id -u)/com.localai.research-agent
```

## Project Structure

```
research/
  agent.py            Main orchestrator (search > analyze > score > dedup > contradict > log)
  searcher.py         DuckDuckGo multi-language search with rate limiting
  analyzer.py         LLM extraction with optimized Gemma 4 system prompt
  scorer.py           5-dimension scoring + history management
  dedup.py            SHA-256 content-hash deduplication
  logger.py           Markdown output with score display
  config.py           YAML config loader
  constants.py        Shared scoring constants (tier thresholds, weights)
  store.py            Substrate: history / dedup index / contradictions / feedback
  contradictions.py   Detects directional, numeric, and negation disagreements
  salience.py         Transparent ranking with explainable breakdown
  brief.py            Daily briefing (read-only synthesis surface)
  feedback.py         Human feedback CLI (useful/noise/pinned/snoozed/resolved)

configs/
  research-agent.yaml      Query templates, languages, scoring weights
  source-authority.yaml    Source reliability ratings (90+ entries)
  salience.yaml            Briefing salience weights (transparent, tunable)
  *.plist                  macOS launchd schedule

data/
  findings.md              Master research log (scored, accumulates over time)
  findings_index.json      Dedup hash index
  findings_history.json    Historical findings for corroboration
  contradictions.jsonl     Append-only log of detected contradictions
  feedback.jsonl           Append-only feedback records
  logs/                    Per-run stats + rejected findings audit trail

tests/
  test_*.py                Golden-scenario tests (corroboration / contradiction / stale)
```

## How the briefing works

`python3 -m research.brief` reads the substrate and renders six sections plus an envelope:

1. **Headline** — new today, top contradiction, top stale claim
2. **New today** — items dated today, ranked by salience
3. **Verified tier** — composite score ≥ 4.0
4. **Likely tier** — composite score 3.0–3.9
5. **Open contradictions** — directional / numeric / negation disagreements with rationale and confidence
6. **Stale or review-overdue** — facts whose review window has passed
7. **Coverage** — counts by category and language; categories with zero findings are listed as gaps
8. **Anti-confabulation envelope** — what was checked, what is missing, confidence assessment, tool actions taken (always `none` — the briefing never writes)

Salience scoring is transparent: every ranked item shows its component breakdown (composite_score, recency, corroboration, contradiction_pressure, stale_review_overdue) plus boosts (pinned, cross_language_corroborated) and penalties (noise, unreliable_tier). Weights live in `configs/salience.yaml` — never magic numbers in code.

## How contradiction detection works

The detector is rule-based, deterministic, and runs without an LLM call. For each new finding it compares against history items in the same category that share entities (Jaccard ≥ 0.30) but live on a different domain. A contradiction fires when:

- **Directional disagreement** — one says `rises`/`surges`/`spikes` while the other says `falls`/`stabilises`/`eases`
- **Negation flip** — one says `agreed`/`approved` while the other says `rejected`/`vetoed`; or `escalation` vs `ceasefire`
- **Numeric divergence** — both quote a price in the same currency and the max/min ratio exceeds 1.30 (configurable), with no shared value within 5%
- **Percentage divergence** — both quote a percentage and the gap exceeds 2 percentage points

False positives are surfaced as "possible contradictions" with confidence scores and rationales — the briefing exposes the rule that fired so the human can see why.

## Running the tests

```bash
pip install pytest pyyaml
pytest tests/ -v
```

The tests exercise three golden scenarios (cross-language corroboration, contradicted prediction, stale fact) end-to-end through scorer, contradiction detector, salience workflow, and briefing renderer. No Ollama or network access required.

## Output Format

Each finding in `data/findings.md`:

```markdown
#### Brent crude rises 4.2% to $127/barrel
- **Date observed:** 2026-04-03
- **Source:** Reuters (en) -- https://reuters.com/...
- **Quality:** Likely (3.6/5.0)
- **Scores:** Sou: 5 | Cor: 3 | Spe: 4 | Rec: 5 | Geo: 3
- **Details:** Brent crude futures rose 4.2% to $127.30 following
  Iranian naval exercises near Hormuz.
- **Impact type:** Economic / Energy prices
- **Related regions:** Global, Gulf States, Europe
```

## Adapting for Your Research Topic

This tool was built for tracking Iran conflict impacts but can be adapted to any research topic:

1. **Edit `configs/research-agent.yaml`**: Replace the categories and search queries with your topic
2. **Edit `configs/source-authority.yaml`**: Add/remove sources relevant to your domain
3. **Edit the system prompt in `research/analyzer.py`**: Update the SYSTEM_PROMPT to describe your research focus and what types of findings to extract/skip
4. **Adjust scoring weights**: Tune the dimension weights in the YAML config based on what matters most for your use case

## Design Philosophy

Architecture follows the *Distributed Interpreter Workflows* pattern language:

- **Substrate / routine split** — the store enforces persistence, identity, and append-only audit; routines (briefing, contradiction detector, salience) interpret. Neither owns the other's job.
- **No god tool** — no single component does search, ranking, synthesis, and writes. The agent.py orchestrator coordinates small, named modules that own one concern each.
- **Anti-confabulation envelope** — the briefing always reports what was checked, what is missing, confidence, and tool actions. Polish without provenance is not allowed.
- **Human accountability boundary** — the briefing is read-only. The agent only writes findings, contradictions, and feedback that are explicitly captured. Outcomes are recorded; nothing acts autonomously.
- **Transparent ranking** — salience is a weighted sum of named components, every ranked item explains its score, and tunables live in YAML.
- **No cloud APIs** — all AI runs locally via Ollama. Your research stays on your machine.
- **No framework overhead** — direct Python + stdlib. Three pip dependencies (`ollama`, `duckduckgo-search`, `pyyaml`); `pytest` and `pyyaml` for tests.
- **Trust through evidence** — findings start as "Unverified" and climb to "Verified" as multiple independent sources corroborate them over time.
- **Configurable** — queries, languages, scoring weights, salience weights, and thresholds are all in YAML.

## License

MIT License. See [LICENSE](LICENSE).
