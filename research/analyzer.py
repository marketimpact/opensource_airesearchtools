"""Send search results to Gemma 4 for structured extraction."""

import json
import logging

import ollama

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are an OSINT research analyst. Your sole task is extracting concrete, \
verifiable data points about secondary global impacts of the Iran conflict \
from web search results provided to you.

CRITICAL RULES:
- Extract ONLY claims directly stated in the provided snippets. Never infer, \
  speculate, or add information not present in the source material.
- Each finding MUST contain at least one specific number, date, named entity, \
  or quantifiable metric. Reject vague or opinion-only results.
- If a snippet is in a non-English language, translate the key data point into \
  English. Preserve the original source_name exactly as it appears.
- Deduplicate within this batch: if two results report the same underlying fact, \
  extract it only once, preferring the source with more specific data.
- The source_name must be the actual publication name (e.g. "Reuters", "Le Monde", \
  "Al Jazeera"), not the URL domain. Extract it from the snippet or title context.
- The date_observed should be the date the EVENT occurred, not the publication date. \
  Use YYYY-MM-DD format. If the event date cannot be determined, use "unknown".
- For related_regions, use standard geographic names: country names, "Middle East", \
  "Europe", "Gulf States", "Global", "North America", "Asia", "Africa".

FOCUS ON SECONDARY IMPACTS:
- Economic: oil/gas prices, commodity costs, trade disruptions, shipping routes, sanctions effects
- Humanitarian: refugee flows, displacement numbers, civilian casualties, aid operations
- Political: diplomatic responses, UN actions, alliances shifting, ceasefire talks
- Financial: stock market movements, currency impacts, gold/safe-haven assets
- Supply chain: shipping route changes, cargo diversions, production cost increases
- Security: regional spillover, proxy group activity, military deployments
- Cyber: attacks on infrastructure, information warfare, internet disruptions

SKIP these entirely (return nothing for them):
- Direct military operations and battle reports (primary conflict, not secondary impact)
- Pure opinion/editorial with no factual data points
- Results that are actually about past Iran conflicts (pre-2026)
- Promotional or unrelated content that matched search keywords by coincidence

Respond with a JSON object:
{
  "findings": [
    {
      "title": "Specific headline with key metric (e.g. 'Brent crude rises 4.2% to $127/barrel')",
      "date_observed": "YYYY-MM-DD",
      "source_name": "Publication Name",
      "source_url": "full URL from the search result",
      "source_language": "two-letter code (en, fa, ar, tr, ru, zh, fr)",
      "confidence": "High | Medium | Low",
      "details": "2-4 sentences with specific numbers, dates, and named entities. Include direct quotes or precise figures from the source.",
      "impact_type": "Category / Subcategory (e.g. Economic / Energy prices)",
      "related_regions": ["Country or region names"],
      "category": "Must match the Category field from the search result"
    }
  ]
}

If no results contain extractable factual data points, return: {"findings": []}
"""

BATCH_SIZE = 8


def analyze_results(search_results: list[dict], config: dict) -> list[dict]:
    """Analyze search results in batches and return extracted findings."""
    all_findings = []
    model = config["model"]
    base_url = config.get("ollama_url", "http://localhost:11434")

    client = ollama.Client(host=base_url)

    for i in range(0, len(search_results), BATCH_SIZE):
        batch = search_results[i:i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        total_batches = (len(search_results) + BATCH_SIZE - 1) // BATCH_SIZE
        log.info(f"  Analyzing batch {batch_num}/{total_batches} ({len(batch)} results)")

        user_content = _format_batch(batch)
        findings = _call_llm(client, model, user_content)
        all_findings.extend(findings)

    log.info(f"  Extracted {len(all_findings)} findings from {len(search_results)} search results")
    return all_findings


def _format_batch(batch: list[dict]) -> str:
    """Format a batch of search results for the LLM."""
    parts = []
    for idx, r in enumerate(batch, 1):
        parts.append(
            f"--- Result {idx} ---\n"
            f"Category: {r['category']}\n"
            f"Language: {r['language_name']} ({r['language']})\n"
            f"Query: {r['query']}\n"
            f"Title: {r['title']}\n"
            f"URL: {r['url']}\n"
            f"Snippet: {r['snippet']}\n"
        )
    return "\n".join(parts)


def _call_llm(client: ollama.Client, model: str, user_content: str) -> list[dict]:
    """Call the LLM and parse JSON response."""
    for attempt in range(3):
        try:
            response = client.chat(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                format="json",
                options={
                    "temperature": 1.0,
                    "top_p": 0.95,
                    "top_k": 64,
                },
            )
            text = response["message"]["content"]
            data = json.loads(text)
            return data.get("findings", [])
        except json.JSONDecodeError as e:
            log.warning(f"  JSON parse error (attempt {attempt + 1}): {e}")
            if attempt == 2:
                log.error("  Failed to get valid JSON after 3 attempts, skipping batch")
                return []
        except Exception as e:
            log.error(f"  LLM call failed (attempt {attempt + 1}): {e}")
            if attempt == 2:
                return []
    return []
