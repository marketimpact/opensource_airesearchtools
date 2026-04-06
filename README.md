# Open Source AI Research Tools

An autonomous, locally-hosted OSINT research agent that searches the web in multiple languages, uses a local LLM to extract structured findings, scores them against a multi-dimensional validation matrix, and logs verified results to a master research file.

Built for tracking secondary global impacts of geopolitical events -- economic, humanitarian, political, supply chain, and security effects that ripple outward from a conflict zone.

## What It Does

- **Searches the web in 7 languages** (English, Farsi, Arabic, Turkish, Russian, Chinese, French) using DuckDuckGo with region-specific targeting
- **Extracts structured findings** using a local 31B parameter LLM (Google Gemma 4 via Ollama) -- no data sent to cloud AI services
- **Scores every finding** across 5 independent dimensions: Source Reliability, Corroboration, Specificity, Recency, and Geographic Relevance
- **Rejects low-quality findings** below a configurable threshold, preserving them in an audit trail
- **Deduplicates** across runs using content hashing
- **Builds corroboration over time** -- findings confirmed by multiple independent sources across languages climb in trust score
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

# Run
python3 -m research.agent
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
  agent.py        Main orchestrator (search > analyze > score > dedup > log)
  searcher.py     DuckDuckGo multi-language search with rate limiting
  analyzer.py     LLM extraction with optimized Gemma 4 system prompt
  scorer.py       5-dimension scoring + history management
  dedup.py        SHA-256 content-hash deduplication
  logger.py       Markdown output with score display
  config.py       YAML config loader

configs/
  research-agent.yaml      Query templates, languages, scoring weights
  source-authority.yaml    Source reliability ratings (90+ entries)
  *.plist                  macOS launchd schedule

data/
  findings.md              Master research log (scored, accumulates over time)
  findings_index.json      Dedup hash index
  findings_history.json    Historical findings for corroboration
  logs/                    Per-run stats + rejected findings audit trail
```

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

- **No cloud APIs** -- all AI runs locally via Ollama. Your research stays on your machine.
- **No framework overhead** -- direct Python + Ollama SDK. Three pip dependencies.
- **Trust through evidence** -- findings start as "Unverified" and climb to "Verified" as multiple independent sources corroborate them over time.
- **Transparency** -- every rejected finding is preserved in run logs with its score breakdown.
- **Configurable** -- queries, languages, scoring weights, and thresholds are all in YAML.

## License

MIT License. See [LICENSE](LICENSE).
