#!/usr/bin/env python3
"""
Fetches citation stats + publication list for a Google Scholar author profile
and writes them to scholar_data.json, which index.html reads at page-load time
to auto-refresh citation counts, h-index, and newly detected publications.

Two data sources are supported:

1. SerpApi's Google Scholar Author API (recommended) — used automatically if
   the SERPAPI_KEY environment variable / secret is set. This is far more
   reliable on CI runners because Google Scholar aggressively blocks/CAPTCHAs
   requests coming from data-center IPs (which is exactly what GitHub Actions
   runners are). SerpApi has a free tier (100 searches/month), which is more
   than enough for a weekly sync.

2. The free `scholarly` Python package — used as a fallback if SERPAPI_KEY is
   not set. This talks to Google Scholar directly and works fine from a
   residential IP (e.g. running it on your own laptop), but frequently gets
   blocked/CAPTCHA'd when run from GitHub Actions' shared IP ranges. Treat it
   as a "run it locally now and then" option rather than a fully unattended one.
"""
import json
import os
import sys
from datetime import datetime, timezone

SCHOLAR_USER_ID = "pO__UocAAAAJ"  # from your profile URL
SERPAPI_KEY = os.environ.get("SERPAPI_KEY", "").strip()


def fetch_via_serpapi():
    import requests

    params = {
        "engine": "google_scholar_author",
        "author_id": SCHOLAR_USER_ID,
        "api_key": SERPAPI_KEY,
        "num": 100,
    }
    r = requests.get("https://serpapi.com/search.json", params=params, timeout=60)
    r.raise_for_status()
    data = r.json()

    cited_by = data.get("cited_by", {}).get("table", [])
    citations = h_index = i10_index = None
    for row in cited_by:
        if "citations" in row:
            citations = row["citations"].get("all")
        if "h_index" in row:
            h_index = row["h_index"].get("all")
        if "i10_index" in row:
            i10_index = row["i10_index"].get("all")

    pubs = []
    for a in data.get("articles", []):
        pubs.append({
            "title": a.get("title", "").strip(),
            "authors": a.get("authors", ""),
            "venue": a.get("publication", ""),
            "year": a.get("year", ""),
            "cited_by": (a.get("cited_by") or {}).get("value", 0),
            "link": a.get("link", ""),
        })

    return {"citations": citations, "h_index": h_index, "i10_index": i10_index, "publications": pubs}


def fetch_via_scholarly():
    from scholarly import scholarly

    author = scholarly.search_author_id(SCHOLAR_USER_ID)
    author = scholarly.fill(author, sections=["basics", "indices", "publications"])

    pubs = []
    for p in author.get("publications", []):
        bib = p.get("bib", {})
        pubs.append({
            "title": bib.get("title", "").strip(),
            "authors": bib.get("author", ""),
            "venue": bib.get("citation", ""),
            "year": bib.get("pub_year", ""),
            "cited_by": p.get("num_citations", 0),
            "link": p.get("pub_url", ""),
        })

    return {
        "citations": author.get("citedby"),
        "h_index": author.get("hindex"),
        "i10_index": author.get("i10index"),
        "publications": pubs,
    }


def main():
    try:
        if SERPAPI_KEY:
            print("Using SerpApi Google Scholar Author API...")
            result = fetch_via_serpapi()
        else:
            print("SERPAPI_KEY not set — falling back to scholarly (direct scraping).")
            result = fetch_via_scholarly()
    except Exception as e:
        print(f"ERROR fetching Scholar data: {e}", file=sys.stderr)
        sys.exit(1)

    result["updated"] = datetime.now(timezone.utc).isoformat()
    result["profile_url"] = f"https://scholar.google.com/citations?user={SCHOLAR_USER_ID}&hl=en"

    out_path = os.path.join(os.path.dirname(__file__), "..", "scholar_data.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"Wrote {out_path}")
    print(f"Citations: {result.get('citations')}, h-index: {result.get('h_index')}, "
          f"{len(result.get('publications', []))} publications found.")


if __name__ == "__main__":
    main()
