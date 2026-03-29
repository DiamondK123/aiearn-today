"""
fetch_news.py - AIEarn.today Daily Auto-Update
Requires: ANTHROPIC_API_KEY environment variable
Run: python fetch_news.py
"""

import os
import re
import json
import feedparser
import anthropic
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ── CONFIG ────────────────────────────────────────────────────────────────────

TZ       = timezone(timedelta(hours=8))
TODAY    = datetime.now(TZ)
DATE_EN  = TODAY.strftime("%b %d, %Y")
DATE_ISO = TODAY.strftime("%Y-%m-%d")
WEEKDAY  = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"][TODAY.weekday()]

RSS_FEEDS = [
    {"url": "https://techcrunch.com/category/artificial-intelligence/feed/", "source": "TechCrunch"},
    {"url": "https://feeds.feedburner.com/venturebeat/SZYF",                 "source": "VentureBeat"},
    {"url": "https://www.theverge.com/ai-artificial-intelligence/rss/index.xml", "source": "The Verge"},
    {"url": "https://openai.com/news/rss.xml",                                "source": "OpenAI"},
    {"url": "https://www.anthropic.com/news/rss",                             "source": "Anthropic"},
    {"url": "https://www.sidehustlenation.com/feed/",                         "source": "Side Hustle Nation"},
    {"url": "https://neilpatel.com/blog/feed/",                               "source": "Neil Patel"},
    {"url": "https://www.promptingguide.ai/feed.xml",                         "source": "Prompting Guide"},
]

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
MODEL  = "claude-sonnet-4-20250514"

CAT_MAP = {
    "tool":   {"label": "AI Tools",      "class": "art-cat-tool"},
    "money":  {"label": "Side Hustle",   "class": "art-cat-money"},
    "course": {"label": "Course Deal",   "class": "art-cat-course"},
    "prompt": {"label": "Prompt Tips",   "class": "art-cat-prompt"},
    "news":   {"label": "Industry News", "class": "art-cat-news"},
}

CAT_EMOJI = {
    "tool":   "AI Tools",
    "money":  "Side Hustle",
    "course": "Course Deal",
    "news":   "Industry News",
    "prompt": "Prompt Tips",
}

# ── 1. FETCH RSS ──────────────────────────────────────────────────────────────

def fetch_rss(max_per_feed=6):
    items = []
    for cfg in RSS_FEEDS:
        try:
            feed = feedparser.parse(cfg["url"])
            for e in feed.entries[:max_per_feed]:
                title   = e.get("title", "").strip()
                summary = re.sub(r"<[^>]+>", "", e.get("summary", e.get("description", ""))).strip()[:300]
                link    = e.get("link", "#")
                if title:
                    items.append({
                        "title":   title,
                        "summary": summary,
                        "link":    link,
                        "source":  cfg["source"],
                    })
        except Exception as ex:
            print("[RSS ERROR] {}: {}".format(cfg["source"], ex))
    print("[RSS] Fetched {} articles".format(len(items)))
    return items

# ── 2. CLASSIFY + SUMMARISE ───────────────────────────────────────────────────

CLASSIFY_PROMPT = """You are the editor of AIEarn.today, a daily site helping people make money with AI tools.

From the RSS articles below (JSON), do the following:
1. Select the 10 most relevant articles for people who want to make money with AI
2. Assign each a category - ONLY one of: tool / money / course / prompt / news
3. Write an English headline (max 12 words, punchy, include numbers where natural)
4. Write an English summary (80-110 words, explain the income/opportunity angle clearly)
5. Set affiliate: true if the article relates to a tool with an affiliate program
6. Set hot: true for the 1-2 most important articles today

Return ONLY a JSON array, no preamble, no markdown fences:
[
  {
    "rank": 1,
    "category": "tool",
    "title_en": "English headline here",
    "summary_en": "English summary 80-110 words here",
    "source": "Source Name",
    "link": "https://...",
    "affiliate": false,
    "hot": true
  }
]

Articles:
ARTICLES_PLACEHOLDER
"""

def classify(items):
    slim = [{"title": x["title"], "summary": x["summary"], "source": x["source"], "link": x["link"]} for x in items]
    prompt = CLASSIFY_PROMPT.replace("ARTICLES_PLACEHOLDER", json.dumps(slim, ensure_ascii=False, indent=2))
    response = client.messages.create(
        model=MODEL,
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = response.content[0].text.strip()
    raw = re.sub(r"^```json\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    articles = json.loads(raw)
    print("[CLAUDE] Selected and summarised {} articles".format(len(articles)))
    return articles

# ── 3. BUILD HTML ─────────────────────────────────────────────────────────────

def build_digest(articles):
    picks = {}
    seen  = set()
    for cat in ["tool", "money", "course", "news", "prompt"]:
        for a in articles:
            if a["category"] == cat and cat not in seen:
                picks[cat] = a
                seen.add(cat)
        if len(picks) == 3:
            break
    if len(picks) < 3:
        for a in articles:
            if a["category"] not in seen:
                picks[a["category"]] = a
                seen.add(a["category"])
            if len(picks) == 3:
                break

    parts = []
    for cat, a in list(picks.items())[:3]:
        label = CAT_EMOJI.get(cat, cat)
        part  = (
            '<div class="digest-item">'
            + '<div class="di-cat">' + label + '</div>'
            + '<h3><a href="' + a["link"] + '">' + a["title_en"] + '</a></h3>'
            + '<p>' + a["summary_en"] + '</p>'
            + '<div class="di-src">Source: ' + a["source"] + ' &middot; ' + DATE_EN + '</div>'
            + '</div>'
        )
        parts.append(part)
    return "\n".join(parts)


def build_card(rank, a):
    cat      = a.get("category", "news")
    info     = CAT_MAP.get(cat, CAT_MAP["news"])
    hot_pill = '<span class="pill pill-new">New</span>' if a.get("hot") else ""
    af_tag   = '<span class="art-tag af">Affiliate</span>' if a.get("affiliate") else ""
    hot_tag  = '<span class="art-tag hot">Today Top</span>' if a.get("hot") else ""
    src_tag  = '<span class="art-tag">' + a["source"] + '</span>'
    card = (
        '<div class="article-card" data-cat="' + cat + '">'
        + '<div class="article-num">' + str(rank).zfill(2) + '</div>'
        + '<div class="article-body">'
        + '<div class="article-meta-top">'
        + '<span class="art-cat ' + info["class"] + '">' + info["label"] + '</span>'
        + hot_pill
        + '<span class="art-time">' + DATE_EN + '</span>'
        + '</div>'
        + '<h3><a href="' + a["link"] + '">' + a["title_en"] + '</a></h3>'
        + '<p>' + a["summary_en"] + '</p>'
        + '<div class="article-tags">' + hot_tag + af_tag + src_tag + '</div>'
        + '<div class="article-source">Source: <a href="' + a["link"] + '">' + a["source"] + '</a> &middot; Curated by AIEarn</div>'
        + '</div>'
        + '</div>'
    )
    return card


def build_article_list(articles):
    return "\n".join(build_card(i + 1, a) for i, a in enumerate(articles))

# ── 4. INJECT INTO HTML ───────────────────────────────────────────────────────

def inject(filepath, zones):
    """
    Replace content between comment markers in HTML files.
    Markers format:
      <!-- BEGIN:zone_id -->
      ...content...
      <!-- END:zone_id -->
    """
    text = Path(filepath).read_text(encoding="utf-8")
    for zone_id, html in zones.items():
        begin_marker = "<!-- BEGIN:" + zone_id + " -->"
        end_marker   = "<!-- END:"   + zone_id + " -->"
        if begin_marker in text and end_marker in text:
            start_pos = text.index(begin_marker) + len(begin_marker)
            end_pos   = text.index(end_marker)
            text = text[:start_pos] + "\n" + html + "\n" + text[end_pos:]
            print("  OK: {} injected ({})".format(zone_id, filepath))
        else:
            print("  MISSING: {} markers not found in {}".format(zone_id, filepath))
    Path(filepath).write_text(text, encoding="utf-8")


def update_homepage(articles):
    hp = Path("index.html")
    if not hp.exists():
        print("[SKIP] index.html not found")
        return

    def build_col(cat, n=4):
        col_articles = [a for a in articles if a["category"] == cat][:n]
        col_html = ""
        for i, a in enumerate(col_articles):
            pill = '<span class="pill pill-new">New</span>' if i == 0 else ""
            col_html += (
                '<div class="news-item">'
                + pill
                + '<a href="' + a["link"] + '">' + a["title_en"] + '</a>'
                + '<div class="news-meta">' + a["source"] + " &middot; " + DATE_EN + "</div>"
                + "</div>"
            )
        return col_html

    inject("index.html", {
        "col-tool":   build_col("tool"),
        "col-money":  build_col("money"),
        "col-course": build_col("course"),
        "col-prompt": build_col("prompt"),
    })

# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 56)
    print("AIEarn.today Auto-Update -- {} {}".format(DATE_EN, WEEKDAY))
    print("=" * 56)

    items = fetch_rss()
    if not items:
        print("[ERROR] No articles fetched. Aborting.")
        return

    articles     = classify(items)
    digest_html  = build_digest(articles)
    article_html = build_article_list(articles)

    if Path("news.html").exists():
        print("\n[news.html]")
        inject("news.html", {
            "digest-grid":  digest_html,
            "article-list": article_html,
        })
    else:
        print("[SKIP] news.html not found")

    print("\n[index.html]")
    update_homepage(articles)

    arc = Path("_archive")
    arc.mkdir(exist_ok=True)
    (arc / (DATE_ISO + ".json")).write_text(
        json.dumps(articles, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print("\n[ARCHIVE] Saved _archive/{}.json".format(DATE_ISO))
    print("\nDone -- {} articles published".format(len(articles)))


if __name__ == "__main__":
    main()
