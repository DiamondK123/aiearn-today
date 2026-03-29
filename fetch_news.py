"""
fetch_news.py - AIEarn.today Daily Auto-Update
- Fetches 20 articles per day
- Accumulates all articles in _archive/all_articles.json
- Generates paginated news pages: news.html, news-2.html, news-3.html ...
- Generates category pages: news-cat-tool.html, news-cat-money.html ...
- 10 articles per page
Requires: ANTHROPIC_API_KEY environment variable
"""

import os
import re
import json
import feedparser
import anthropic
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ── CONFIG ────────────────────────────────────────────────────────────────────

TZ           = timezone(timedelta(hours=8))
TODAY        = datetime.now(TZ)
DATE_EN      = TODAY.strftime("%b %d, %Y")
DATE_ISO     = TODAY.strftime("%Y-%m-%d")
WEEKDAY      = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"][TODAY.weekday()]
PER_PAGE     = 10
ARTICLES_PER_RUN = 20   # fetch this many per day
ALL_ARCHIVE  = Path("_archive/all_articles.json")

RSS_FEEDS = [
    {"url": "https://techcrunch.com/category/artificial-intelligence/feed/", "source": "TechCrunch"},
    {"url": "https://feeds.feedburner.com/venturebeat/SZYF",                 "source": "VentureBeat"},
    {"url": "https://www.theverge.com/ai-artificial-intelligence/rss/index.xml", "source": "The Verge"},
    {"url": "https://openai.com/news/rss.xml",                                "source": "OpenAI"},
    {"url": "https://www.anthropic.com/news/rss",                             "source": "Anthropic"},
    {"url": "https://www.sidehustlenation.com/feed/",                         "source": "Side Hustle Nation"},
    {"url": "https://neilpatel.com/blog/feed/",                               "source": "Neil Patel"},
    {"url": "https://www.promptingguide.ai/feed.xml",                         "source": "Prompting Guide"},
    {"url": "https://aiweekly.co/issues.rss",                                 "source": "AI Weekly"},
    {"url": "https://www.artificialintelligence-news.com/feed/",              "source": "AI News"},
]

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
MODEL  = "claude-sonnet-4-20250514"

CATEGORIES = ["tool", "money", "course", "prompt", "news"]

CAT_MAP = {
    "tool":   {"label": "AI Tools",      "class": "art-cat-tool",   "emoji": "🤖"},
    "money":  {"label": "Side Hustle",   "class": "art-cat-money",  "emoji": "💰"},
    "course": {"label": "Course Deal",   "class": "art-cat-course", "emoji": "📚"},
    "prompt": {"label": "Prompt Tips",   "class": "art-cat-prompt", "emoji": "🔧"},
    "news":   {"label": "Industry News", "class": "art-cat-news",   "emoji": "📡"},
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
                if title and link != "#":
                    items.append({"title": title, "summary": summary, "link": link, "source": cfg["source"]})
        except Exception as ex:
            print("[RSS ERROR] {}: {}".format(cfg["source"], ex))
    print("[RSS] Fetched {} articles".format(len(items)))
    return items

# ── 2. CLASSIFY + SUMMARISE ───────────────────────────────────────────────────

CLASSIFY_PROMPT = """You are the editor of AIEarn.today, helping people make money with AI tools.

From the RSS articles below (JSON), do the following:
1. Select the TOP {count} most relevant articles for people who want to make money with AI
2. Assign each a category - ONLY one of: tool / money / course / prompt / news
3. Write a punchy English headline (max 12 words, include numbers where natural)
4. Write an English summary (80-110 words, focus on income/opportunity angle)
5. Set affiliate: true if the article relates to a tool that has an affiliate program
6. Set hot: true for the 2-3 most important articles today

Return ONLY a JSON array, no preamble, no markdown:
[
  {{
    "rank": 1,
    "category": "tool",
    "title_en": "headline here",
    "summary_en": "summary here",
    "source": "Source Name",
    "link": "https://...",
    "affiliate": false,
    "hot": true,
    "date": "{date}"
  }}
]

Articles:
ARTICLES_PLACEHOLDER
"""

def classify(items, count=20):
    slim   = [{"title": x["title"], "summary": x["summary"], "source": x["source"], "link": x["link"]} for x in items]
    prompt = (CLASSIFY_PROMPT
              .replace("{count}", str(count))
              .replace("{date}", DATE_ISO)
              .replace("ARTICLES_PLACEHOLDER", json.dumps(slim, ensure_ascii=False, indent=2)))
    response = client.messages.create(
        model=MODEL, max_tokens=6000,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = response.content[0].text.strip()
    raw = re.sub(r"^```json\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    articles = json.loads(raw)
    print("[CLAUDE] Classified {} articles".format(len(articles)))
    return articles

# ── 3. ARCHIVE — accumulate all articles ─────────────────────────────────────

def load_all_articles():
    if ALL_ARCHIVE.exists():
        return json.loads(ALL_ARCHIVE.read_text(encoding="utf-8"))
    return []

def save_all_articles(all_articles):
    ALL_ARCHIVE.parent.mkdir(exist_ok=True)
    ALL_ARCHIVE.write_text(json.dumps(all_articles, ensure_ascii=False, indent=2), encoding="utf-8")

def merge_articles(existing, new_today):
    existing_links = {a["link"] for a in existing}
    added = 0
    for a in new_today:
        if a["link"] not in existing_links:
            existing.insert(0, a)
            added += 1
    print("[ARCHIVE] Added {} new articles, total: {}".format(added, len(existing)))
    return existing

# ── 4. BUILD HTML COMPONENTS ──────────────────────────────────────────────────

def build_nav(active_page="home"):
    links = [
        ("index.html",      "Home"),
        ("news.html",       "All News"),
        ("news-cat-tool.html",   "AI Tools"),
        ("news-cat-money.html",  "Side Hustles"),
        ("news-cat-course.html", "Courses"),
        ("news-cat-prompt.html", "Prompt Tips"),
        ("news-cat-news.html",   "Industry"),
    ]
    nav_html = '<div class="nav-bar">'
    for href, label in links:
        active_class = " active" if active_page == href else ""
        nav_html += '<a href="/{}" class="nav-link{}">{}</a>'.format(href, active_class, label)
    nav_html += "</div>"
    return nav_html


def build_card(rank, a):
    cat      = a.get("category", "news")
    info     = CAT_MAP.get(cat, CAT_MAP["news"])
    date_str = a.get("date", DATE_ISO)
    hot_pill = '<span class="pill pill-new">New</span>' if a.get("hot") else ""
    af_tag   = '<span class="art-tag af">Affiliate</span>' if a.get("affiliate") else ""
    hot_tag  = '<span class="art-tag hot">Top Pick</span>' if a.get("hot") else ""
    src_tag  = '<span class="art-tag">' + a["source"] + "</span>"
    return (
        '<div class="article-card" data-cat="' + cat + '">'
        + '<div class="article-num">' + str(rank).zfill(2) + "</div>"
        + '<div class="article-body">'
        + '<div class="article-meta-top">'
        + '<span class="art-cat ' + info["class"] + '">' + info["emoji"] + " " + info["label"] + "</span>"
        + hot_pill
        + '<span class="art-time">' + date_str + "</span>"
        + "</div>"
        + '<h3><a href="' + a["link"] + '" target="_blank" rel="noopener">' + a["title_en"] + "</a></h3>"
        + "<p>" + a["summary_en"] + "</p>"
        + '<div class="article-tags">' + hot_tag + af_tag + src_tag + "</div>"
        + '<div class="article-source">Source: <a href="' + a["link"] + '" target="_blank">' + a["source"] + "</a> &middot; Curated by AIEarn</div>"
        + "</div>"
        + "</div>"
    )


def build_pagination(current_page, total_pages, base="news"):
    if total_pages <= 1:
        return ""
    def page_url(n):
        return "/" + base + ".html" if n == 1 else "/" + base + "-" + str(n) + ".html"
    html = '<div class="pagination">'
    if current_page > 1:
        html += '<a href="' + page_url(current_page - 1) + '" class="page-btn">← Prev</a>'
    for n in range(1, total_pages + 1):
        if n == current_page:
            html += '<span class="page-btn active">' + str(n) + "</span>"
        elif abs(n - current_page) <= 2 or n == 1 or n == total_pages:
            html += '<a href="' + page_url(n) + '" class="page-btn">' + str(n) + "</a>"
        elif abs(n - current_page) == 3:
            html += '<span class="page-btn disabled">···</span>'
    if current_page < total_pages:
        html += '<a href="' + page_url(current_page + 1) + '" class="page-btn">Next →</a>'
    html += "</div>"
    return html


def build_digest(articles):
    picks, seen = {}, set()
    for cat in ["tool", "money", "course", "news", "prompt"]:
        for a in articles:
            if a["category"] == cat and cat not in seen:
                picks[cat] = a
                seen.add(cat)
        if len(picks) == 3:
            break
    parts = []
    for cat, a in list(picks.items())[:3]:
        info = CAT_MAP.get(cat, CAT_MAP["news"])
        parts.append(
            '<div class="digest-item">'
            + '<div class="di-cat">' + info["emoji"] + " " + info["label"] + "</div>"
            + '<h3><a href="' + a["link"] + '" target="_blank">' + a["title_en"] + "</a></h3>"
            + "<p>" + a["summary_en"][:150] + "...</p>"
            + '<div class="di-src">Source: ' + a["source"] + " &middot; " + DATE_EN + "</div>"
            + "</div>"
        )
    return "\n".join(parts)

# ── 5. READ NEWS.HTML TEMPLATE ────────────────────────────────────────────────

def read_template():
    return Path("news.html").read_text(encoding="utf-8")


def inject_zone(html, zone_id, content):
    begin = "<!-- BEGIN:" + zone_id + " -->"
    end   = "<!-- END:"   + zone_id + " -->"
    if begin in html and end in html:
        start = html.index(begin) + len(begin)
        stop  = html.index(end)
        return html[:start] + "\n" + content + "\n" + html[stop:]
    print("  MISSING marker: " + zone_id)
    return html


def write_page(filename, html):
    if 'G-JCQ4FTHHMZ' not in html:
        ga = ('<script async src="https://www.googletagmanager.com/gtag/js?id=G-JCQ4FTHHMZ"></script>'
              '<script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}'
              'gtag("js",new Date());gtag("config","G-JCQ4FTHHMZ");</script>')
        html = html.replace('</head>', ga + '</head>', 1)
    Path(filename).write_text(html, encoding='utf-8')
    print('  Written: ' + filename)

# ── 6. GENERATE ALL PAGES ─────────────────────────────────────────────────────

def generate_paginated_pages(all_articles, template):
    total     = len(all_articles)
    n_pages   = max(1, -(-total // PER_PAGE))  # ceiling division
    today_top = [a for a in all_articles if a.get("date") == DATE_ISO]
    digest    = build_digest(today_top if today_top else all_articles[:3])

    print("\n[PAGES] Generating {} paginated pages ({} articles total)".format(n_pages, total))

    for page_num in range(1, n_pages + 1):
        start    = (page_num - 1) * PER_PAGE
        chunk    = all_articles[start: start + PER_PAGE]
        cards    = "\n".join(build_card(start + i + 1, a) for i, a in enumerate(chunk))
        pager    = build_pagination(page_num, n_pages, base="news")
        filename = "news.html" if page_num == 1 else "news-{}.html".format(page_num)

        page_html = template
        page_html = inject_zone(page_html, "digest-grid",  digest)
        page_html = inject_zone(page_html, "article-list", cards + "\n" + pager)
        write_page(filename, page_html)

    return n_pages


def generate_category_pages(all_articles, template):
    print("\n[CATEGORY PAGES]")
    for cat in CATEGORIES:
        cat_articles = [a for a in all_articles if a.get("category") == cat]
        if not cat_articles:
            continue
        info      = CAT_MAP[cat]
        total     = len(cat_articles)
        n_pages   = max(1, -(-total // PER_PAGE))
        base      = "news-cat-" + cat

        for page_num in range(1, n_pages + 1):
            start    = (page_num - 1) * PER_PAGE
            chunk    = cat_articles[start: start + PER_PAGE]
            cards    = "\n".join(build_card(start + i + 1, a) for i, a in enumerate(chunk))
            pager    = build_pagination(page_num, n_pages, base=base)
            filename = base + ".html" if page_num == 1 else base + "-" + str(page_num) + ".html"

            # build a simple digest for this category
            cat_digest = "<div class=\"digest-item\"><div class=\"di-cat\">" + info["emoji"] + " " + info["label"] + "</div><h3>All " + info["label"] + " articles — " + str(total) + " total</h3><p>Browse all " + info["label"].lower() + " articles curated by AIEarn.today. Updated daily.</p></div>"
            cat_digest = cat_digest + cat_digest + cat_digest  # pad to 3 cols

            page_html = template
            page_html = inject_zone(page_html, "digest-grid",  cat_digest)
            page_html = inject_zone(page_html, "article-list", cards + "\n" + pager)
            write_page(filename, page_html)

        print("  {} → {} pages ({} articles)".format(cat, n_pages, total))

# ── 7. UPDATE HOMEPAGE NEWS COLUMNS ──────────────────────────────────────────

def update_homepage(articles):
    hp = Path("index.html")
    if not hp.exists():
        print("[SKIP] index.html not found")
        return
    content = hp.read_text(encoding="utf-8")

    def build_col(cat, n=4):
        col_articles = [a for a in articles if a["category"] == cat][:n]
        col_html = ""
        for i, a in enumerate(col_articles):
            pill = '<span class="pill pill-new">New</span>' if i == 0 else ""
            col_html += (
                '<div class="news-item">'
                + pill
                + '<a href="' + a["link"] + '" target="_blank">' + a["title_en"] + "</a>"
                + '<div class="news-meta">' + a["source"] + " &middot; " + DATE_EN + "</div>"
                + "</div>"
            )
        return col_html

    for zone_id, cat in [("col-tool","tool"),("col-money","money"),("col-course","course"),("col-prompt","prompt")]:
        content = inject_zone(content, zone_id, build_col(cat))

    hp.write_text(content, encoding="utf-8")
    print("  index.html updated")

# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("AIEarn.today Auto-Update -- {} {}".format(DATE_EN, WEEKDAY))
    print("=" * 60)

    # 1. Fetch & classify new articles
    items    = fetch_rss(max_per_feed=8)
    if not items:
        print("[ERROR] No articles fetched. Aborting.")
        return
    new_articles = classify(items, count=ARTICLES_PER_RUN)

    # 2. Merge with full archive
    all_articles = load_all_articles()
    all_articles = merge_articles(all_articles, new_articles)
    save_all_articles(all_articles)

    # Daily archive
    Path("_archive").mkdir(exist_ok=True)
    (Path("_archive") / (DATE_ISO + ".json")).write_text(
        json.dumps(new_articles, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 3. Read template
    if not Path("news.html").exists():
        print("[ERROR] news.html template not found")
        return
    template = read_template()

    # 4. Generate all pages
    print("\n[GENERATING PAGES]")
    n_main = generate_paginated_pages(all_articles, template)
    generate_category_pages(all_articles, template)

    # 5. Update homepage
    print("\n[index.html]")
    update_homepage(new_articles)

    print("\n" + "=" * 60)
    print("Done! {} total articles | {} main pages generated".format(len(all_articles), n_main))
    print("Category pages: " + ", ".join("news-cat-{}.html".format(c) for c in CATEGORIES))
    print("=" * 60)


if __name__ == "__main__":
    main()
