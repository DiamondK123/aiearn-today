"""
fetch_news.py — AIEarn.today Daily Auto-Update Script
Run: python fetch_news.py
Requires env var: ANTHROPIC_API_KEY
Triggered daily at 08:00 UTC+8 via GitHub Actions
Injects into: news.html, index.html (English only)
"""

import os, json, re, feedparser, anthropic
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ── CONFIG ────────────────────────────────────────────────────────────────────

TZ      = timezone(timedelta(hours=8))
TODAY   = datetime.now(TZ)
DATE_EN = TODAY.strftime("%b %d, %Y")        # e.g. Mar 28, 2025
DATE_ISO= TODAY.strftime("%Y-%m-%d")
WEEKDAY = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"][TODAY.weekday()]

RSS_FEEDS = [
    # AI tools / industry
    {"url": "https://techcrunch.com/category/artificial-intelligence/feed/", "source": "TechCrunch"},
    {"url": "https://feeds.feedburner.com/venturebeat/SZYF",                "source": "VentureBeat"},
    {"url": "https://www.theverge.com/ai-artificial-intelligence/rss/index.xml", "source": "The Verge"},
    {"url": "https://openai.com/news/rss.xml",                               "source": "OpenAI"},
    {"url": "https://www.anthropic.com/news/rss",                            "source": "Anthropic"},
    # Side hustle / money
    {"url": "https://www.sidehustlenation.com/feed/",                        "source": "Side Hustle Nation"},
    {"url": "https://neilpatel.com/blog/feed/",                              "source": "Neil Patel"},
    # Prompt / tutorials
    {"url": "https://www.promptingguide.ai/feed.xml",                        "source": "Prompting Guide"},
]

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
MODEL  = "claude-sonnet-4-20250514"

CAT_MAP = {
    "tool":   {"label": "🤖 AI Tools",      "class": "art-cat-tool"},
    "money":  {"label": "💰 Side Hustle",    "class": "art-cat-money"},
    "course": {"label": "📚 Course Deal",    "class": "art-cat-course"},
    "prompt": {"label": "🔧 Prompt Tips",    "class": "art-cat-prompt"},
    "news":   {"label": "📡 Industry News",  "class": "art-cat-news"},
}

# ── 1. FETCH RSS ──────────────────────────────────────────────────────────────

def fetch_rss(max_per_feed=6):
    items = []
    for cfg in RSS_FEEDS:
        try:
            feed = feedparser.parse(cfg["url"])
            for e in feed.entries[:max_per_feed]:
                title   = e.get("title","").strip()
                summary = re.sub(r"<[^>]+>","", e.get("summary", e.get("description",""))).strip()[:300]
                link    = e.get("link","#")
                if title:
                    items.append({"title":title,"summary":summary,"link":link,"source":cfg["source"]})
        except Exception as ex:
            print(f"[RSS ERROR] {cfg['source']}: {ex}")
    print(f"[RSS] Fetched {len(items)} articles")
    return items

# ── 2. CLAUDE: CLASSIFY + SUMMARISE IN ENGLISH ───────────────────────────────

PROMPT = """You are the editor of AIEarn.today, a daily site helping people make money with AI tools.

From the RSS articles below (JSON), do the following:
1. Select the 10 most relevant articles for an English-speaking audience who want to make money with AI
2. Assign each a category — ONLY one of: tool / money / course / prompt / news
3. Write an English headline (max 12 words, punchy, include numbers where natural)
4. Write an English summary (80–110 words, explain the income/opportunity angle clearly)
5. Set affiliate: true if the article relates to a tool that has an affiliate program
6. Set hot: true for the 1–2 most important articles of the day

Return ONLY a JSON array — no preamble, no markdown fences:
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
{articles_json}
"""

def classify(items):
    slim = [{"title":x["title"],"summary":x["summary"],"source":x["source"],"link":x["link"]} for x in items]
    response = client.messages.create(
        model=MODEL, max_tokens=4000,
        messages=[{"role":"user","content": PROMPT.replace("{articles_json}", json.dumps(slim, ensure_ascii=False, indent=2))}]
    )
    raw = response.content[0].text.strip()
    raw = re.sub(r"^```json\s*","",raw); raw = re.sub(r"\s*```$","",raw)
    articles = json.loads(raw)
    print(f"[CLAUDE] Selected and summarised {len(articles)} articles")
    return articles

# ── 3. BUILD HTML BLOCKS ──────────────────────────────────────────────────────

def build_digest(articles):
    """3-column top digest — one per category: tool / money / course"""
    picks, seen = {}, set()
    priority = ["tool","money","course","news","prompt"]
    for cat in priority:
        for a in articles:
            if a["category"] == cat and cat not in seen:
                picks[cat] = a; seen.add(cat)
        if len(picks) == 3: break
    if len(picks) < 3:
        for a in articles:
            if a["category"] not in seen:
                picks[a["category"]] = a; seen.add(a["category"])
            if len(picks) == 3: break
    labels = {"tool":"🤖 AI Tools","money":"💰 Side Hustle","course":"📚 Course Deal","news":"📡 Industry","prompt":"🔧 Prompts"}
    parts  = []
    for cat, a in list(picks.items())[:3]:
        parts.append(f"""
      <div class="digest-item">
        <div class="di-cat">{labels.get(cat,cat)}</div>
        <h3><a href="{a['link']}">{a['title_en']}</a></h3>
        <p>{a['summary_en']}</p>
        <div class="di-src">Source: {a['source']} · {DATE_EN}</div>
      </div>""")
    return "\n".join(parts)


def build_card(rank, a):
    cat      = a.get("category","news")
    info     = CAT_MAP.get(cat, CAT_MAP["news"])
    hot_pill = '<span class="pill pill-new">New</span>' if a.get("hot") else ""
    af_tag   = '<span class="art-tag af">Affiliate ↗</span>' if a.get("affiliate") else ""
    hot_tag  = '<span class="art-tag hot">Today\'s Top</span>' if a.get("hot") else ""
    src_tag  = f'<span class="art-tag">{a["source"]}</span>'
    return f"""
        <div class="article-card" data-cat="{cat}">
          <div class="article-num">{rank:02d}</div>
          <div class="article-body">
            <div class="article-meta-top">
              <span class="art-cat {info['class']}">{info['label']}</span>
              {hot_pill}
              <span class="art-time">{DATE_EN}</span>
            </div>
            <h3><a href="{a['link']}">{a['title_en']}</a></h3>
            <p>{a['summary_en']}</p>
            <div class="article-tags">
              {hot_tag}{af_tag}{src_tag}
            </div>
            <div class="article-source">Source: <a href="{a['link']}">{a['source']}</a> · Curated by AIEarn</div>
          </div>
        </div>"""


def build_article_list(articles):
    return "\n".join(build_card(i+1, a) for i, a in enumerate(articles))

# ── 4. INJECT HTML FILES ──────────────────────────────────────────────────────

def inject(filepath, zones):
    """Replace content between <!-- BEGIN:id --> and <!-- END:id --> markers."""
    content = Path(filepath).read_text(encoding="utf-8")
    for eid, html in zones.items():
        begin = f"<!-- BEGIN:{eid} -->"
        end   = f"<!-- END:{eid} -->"
        if begin in content and end in content:
            import re as _re
            pattern = _re.escape(begin) + r".*?" + _re.escape(end)
            replacement = begin + "
" + html + "
" + end
            new_content, n = _re.subn(pattern, replacement, content, count=1, flags=_re.DOTALL)
            if n:
                print(f"  checkmark #{eid} injected ({filepath})")
                content = new_content
            else:
                print(f"  x #{eid} replace failed ({filepath})")
        else:
            print(f"  x #{eid} markers not found ({filepath})")
    Path(filepath).write_text(content, encoding="utf-8")


def update_homepage_news(articles):
    """Update the 4-column news grid on index.html if it has id-tagged columns."""
    hp = Path("index.html")
    if not hp.exists(): return
    def col(cat, n=4):
        items = [a for a in articles if a["category"]==cat][:n]
        out = ""
        for i, a in enumerate(items):
            pill = '<span class="pill pill-new">New</span>\n' if i==0 else ""
            out += f"""
      <div class="news-item">
        {pill}<a href="{a['link']}">{a['title_en']}</a>
        <div class="news-meta">{a['source']} · {DATE_EN}</div>
      </div>"""
        return out
    inject("index.html", {
        "col-tool":   col("tool"),
        "col-money":  col("money"),
        "col-course": col("course"),
        "col-prompt": col("prompt"),
    })

# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    print(f"\n{'='*56}")
    print(f"AIEarn.today Auto-Update — {DATE_EN} {WEEKDAY}")
    print(f"{'='*56}\n")

    items    = fetch_rss()
    if not items:
        print("[ERROR] No articles fetched. Aborting."); return

    articles = classify(items)
    digest   = build_digest(articles)
    art_list = build_article_list(articles)

    # Inject news.html
    if Path("news.html").exists():
        print("\n[news.html]")
        inject("news.html", {"digest-grid": digest, "article-list": art_list})
    else:
        print("[SKIP] news.html not found")

    # Optionally update homepage news columns
    print("\n[index.html]")
    update_homepage_news(articles)

    # Archive
    arc = Path("_archive"); arc.mkdir(exist_ok=True)
    (arc / f"{DATE_ISO}.json").write_text(
        json.dumps(articles, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n[ARCHIVE] Saved to _archive/{DATE_ISO}.json")
    print(f"\n✅ Done — {len(articles)} articles published\n")

if __name__ == "__main__":
    main()
