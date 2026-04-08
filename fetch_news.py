"""
fetch_news.py - AIEarn.today Daily Auto-Update
- Fetches 20 article ideas from RSS feeds daily
- Uses Claude API to write full 800-1000 word articles
- Generates individual article pages: articles/slug.html
- Generates paginated news index pages
- Generates category pages
- Generates sitemap.xml
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
ARTICLES_PER_RUN = 5   # write 5 full articles per day (cost-efficient)
ALL_ARCHIVE  = Path("_archive/all_articles.json")
ARTICLES_DIR = Path("articles")

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

GA_TAG = ('<script async src="https://www.googletagmanager.com/gtag/js?id=G-J29S2PGT2W"></script>'
          '<script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}'
          'gtag("js",new Date());gtag("config","G-J29S2PGT2W");</script>')

# ── 1. FETCH RSS ──────────────────────────────────────────────────────────────

def fetch_rss(max_per_feed=6):
    items = []
    for cfg in RSS_FEEDS:
        try:
            feed = feedparser.parse(cfg["url"])
            for e in feed.entries[:max_per_feed]:
                title   = e.get("title", "").strip()
                summary = re.sub(r"<[^>]+>", "", e.get("summary", e.get("description", ""))).strip()[:500]
                link    = e.get("link", "#")
                if title and link != "#":
                    items.append({"title": title, "summary": summary, "link": link, "source": cfg["source"]})
        except Exception as ex:
            print("[RSS ERROR] {}: {}".format(cfg["source"], ex))
    print("[RSS] Fetched {} articles".format(len(items)))
    return items

# ── 2. STEP 1: SELECT & CLASSIFY TOPICS ──────────────────────────────────────

SELECT_PROMPT = """You are the editor of AIEarn.today, helping people make money with AI tools.

From the RSS articles below, select the TOP {count} most relevant for people who want to make money with AI.

For each selected article:
1. category - ONLY one of: tool / money / course / prompt / news
2. title_en - punchy English headline (max 12 words, include numbers where natural)
3. summary_en - 2-sentence teaser (40-60 words)
4. slug - URL-friendly slug (lowercase, hyphens, no special chars, max 60 chars)
5. affiliate: true if relates to a tool with affiliate program
6. hot: true for the 2-3 most important articles today

Return ONLY a JSON array, no preamble, no markdown:
[
  {{
    "rank": 1,
    "category": "tool",
    "title_en": "headline",
    "summary_en": "teaser",
    "slug": "url-slug-here",
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

def select_topics(items, count=20):
    slim   = [{"title": x["title"], "summary": x["summary"], "source": x["source"], "link": x["link"]} for x in items]
    prompt = (SELECT_PROMPT
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
    print("[CLAUDE] Selected {} topics".format(len(articles)))
    return articles

# ── 3. STEP 2: WRITE FULL ARTICLES ───────────────────────────────────────────

ARTICLE_PROMPT = """You are a senior editor at AIEarn.today, a publication that helps people make money with AI tools.

Write a complete, high-quality article of 850-1000 words on this topic:

Title: {title}
Category: {category}
Source news: {source_title}
Source summary: {source_summary}
Source URL: {source_url}

Requirements:
- Write in a clear, helpful, editorial voice (like Bloomberg or The Information)
- Structure: Introduction (hook) → Background → Main insights → Practical takeaways → Conclusion
- Include at least 3 specific, actionable tips readers can use to make money or save money
- Mention specific tools, prices, or numbers where relevant
- Natural keyword usage: "make money with AI", the tool name, the category topic
- End with a clear call to action pointing to related content on our site
- Do NOT copy from the source — write original analysis and perspective
- Write ONLY the article body (no title, no metadata)
- Use HTML paragraph tags: <p>, <h2>, <h3>, <ul>, <li>, <strong>
- Minimum 4 paragraphs, at least 2 subheadings

Write the full article now:"""

def write_full_article(a):
    prompt = (ARTICLE_PROMPT
              .replace("{title}", a["title_en"])
              .replace("{category}", a["category"])
              .replace("{source_title}", a["title_en"])
              .replace("{source_summary}", a.get("summary_en", ""))
              .replace("{source_url}", a["link"]))
    response = client.messages.create(
        model=MODEL, max_tokens=2000,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text.strip()

# ── 4. ARCHIVE ────────────────────────────────────────────────────────────────

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
    print("[ARCHIVE] Added {} new, total: {}".format(added, len(existing)))
    return existing

# ── 5. BUILD HTML COMPONENTS ──────────────────────────────────────────────────

def head_tags(title, description, url_path, extra_schema=""):
    canonical = "https://www.aimoneynews.com" + url_path
    return (
        '<meta charset="UTF-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
        '<title>' + title + ' — AIEarn.today</title>'
        '<meta name="description" content="' + description + '">'
        '<link rel="canonical" href="' + canonical + '">'
        '<meta property="og:title" content="' + title + '">'
        '<meta property="og:description" content="' + description + '">'
        '<meta property="og:type" content="article">'
        '<meta property="og:url" content="' + canonical + '">'
        '<meta property="og:site_name" content="AIEarn.today">'
        '<meta name="twitter:card" content="summary_large_image">'
        '<meta name="twitter:title" content="' + title + '">'
        '<meta name="twitter:description" content="' + description + '">'
        + extra_schema +
        '<link rel="preconnect" href="https://fonts.googleapis.com">'
        '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;600&family=Playfair+Display:wght@700;800&display=swap" rel="stylesheet">'
    )


def shared_css():
    return """<style>
:root{--ink:#0a0a0a;--ink2:#333;--ink3:#666;--ink4:#999;--bg:#fff;--bg2:#f8f8f8;--bg3:#f2f2f2;--rule:#e5e5e5;--rule2:#ccc;--red:#d0021b;--blue:#0066cc;--gold:#b8860b;--green:#1a7a3c;--mono:'IBM Plex Mono',monospace;--serif:'Playfair Display',Georgia,serif;--sans:'Inter',system-ui,sans-serif;}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0;}
body{background:var(--bg);color:var(--ink);font-family:var(--sans);font-size:16px;line-height:1.7;}
.container{max-width:1200px;margin:0 auto;padding:0 32px;}
.top-banner{background:#0a0a0a;color:#fff;padding:6px 16px;font-family:var(--mono);font-size:10px;letter-spacing:.06em;display:flex;justify-content:space-between;align-items:center;border-bottom:2px solid var(--red);}
.ticker{display:flex;gap:32px;overflow:hidden;}
.ticker span{white-space:nowrap;}
.up{color:#22c55e;}.dn{color:#ef4444;}
.translate-bar{background:var(--bg2);border-bottom:1px solid var(--rule);padding:5px 24px;display:flex;align-items:center;gap:10px;font-family:var(--mono);font-size:10px;color:var(--ink3);}
.translate-bar span{text-transform:uppercase;}
.goog-te-gadget-simple{background:transparent!important;border:1px solid var(--rule2)!important;padding:2px 6px!important;font-family:var(--mono)!important;font-size:10px!important;}
.goog-te-gadget-simple span,.goog-te-gadget-simple a{color:var(--ink)!important;}
.goog-te-banner-frame{display:none!important;}
body{top:0!important;}
.masthead{border-bottom:3px solid var(--ink);padding:20px 0 14px;}
.site-name{font-family:var(--serif);font-size:50px;font-weight:800;letter-spacing:-.04em;line-height:1;color:var(--ink);text-decoration:none;display:inline-block;}
.site-name span{color:var(--red);}
.site-tagline{font-family:var(--mono);font-size:10px;color:var(--ink3);letter-spacing:.12em;text-transform:uppercase;margin-top:6px;}
.nav-bar{border-bottom:1px solid var(--ink);border-top:1px solid var(--rule);display:flex;align-items:stretch;background:var(--bg);overflow-x:auto;}
.nav-bar a{font-family:var(--mono);font-size:11px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;color:var(--ink);text-decoration:none;padding:10px 18px;white-space:nowrap;border-right:1px solid var(--rule);transition:color .15s;position:relative;}
.nav-bar a:hover{color:var(--red);}
.nav-bar a.active{color:var(--red);}
.nav-bar a.active::after{content:'';position:absolute;bottom:-1px;left:0;right:0;height:2px;background:var(--red);}
.breaking-bar{background:var(--red);color:#fff;font-family:var(--mono);font-size:11px;padding:6px 0;display:flex;align-items:center;overflow:hidden;}
.breaking-label{background:#fff;color:var(--red);font-weight:700;padding:0 12px;margin-right:16px;white-space:nowrap;flex-shrink:0;letter-spacing:.12em;}
.breaking-text{display:flex;gap:48px;animation:scroll-left 42s linear infinite;white-space:nowrap;}
@keyframes scroll-left{0%{transform:translateX(0);}100%{transform:translateX(-50%);}}
footer{border-top:3px solid var(--ink);padding:24px 32px;background:var(--ink);color:#fff;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:16px;}
.footer-brand{font-family:var(--serif);font-size:22px;font-weight:700;}
.footer-brand span{color:#e8374a;}
.footer-links{display:flex;gap:24px;flex-wrap:wrap;}
.footer-links a{font-family:var(--mono);font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:#fff;text-decoration:none;opacity:.6;}
.footer-links a:hover{opacity:1;}
.footer-copy{font-family:var(--mono);font-size:9px;opacity:.35;width:100%;}
@media(max-width:900px){.container{padding:0 20px;}.site-name{font-size:36px;}}
</style>"""


def shared_header(active="news"):
    nav_links = [
        ("/index.html", "Home"),
        ("/news.html", "Daily News"),
        ("/about.html", "About"),
    ]
    nav = '<div class="nav-bar">'
    for href, label in nav_links:
        active_class = ' class="active"' if active == href else ""
        nav += '<a href="' + href + '"' + active_class + ">" + label + "</a>"
    nav += "</div>"

    return (
        '<div class="top-banner">'
        '<div class="ticker">'
        '<span>ChatGPT Plus <span class="up">▲ Updated</span></span>'
        '<span>Claude API <span class="up">▲ Price cut</span></span>'
        '<span>Midjourney v7 <span class="up">▲ Released</span></span>'
        '<span>ChatGPT Plus <span class="up">▲ Updated</span></span>'
        '<span>Claude API <span class="up">▲ Price cut</span></span>'
        "</div>"
        '<div style="font-family:var(--mono);font-size:10px;opacity:.6">' + DATE_EN + "</div>"
        "</div>"
        '<div class="translate-bar container">'
        "<span>🌐 Translate:</span>"
        '<div id="google_translate_element"></div>'
        "</div>"
        '<div class="masthead container">'
        '<a href="/index.html" class="site-name">AI<span>Earn</span>.today</a>'
        '<div class="site-tagline">Daily Guide to Making Money with AI Tools</div>'
        "</div>"
        + nav
    )


def shared_footer():
    return (
        "<footer>"
        '<div class="footer-brand">AI<span>Earn</span>.today</div>'
        '<div class="footer-links">'
        '<a href="/index.html">Home</a>'
        '<a href="/news.html">News</a>'
        '<a href="/about.html">About</a>'
        '<a href="/affiliate-disclosure.html">Affiliate Disclosure</a>'
        '<a href="/privacy-policy.html">Privacy Policy</a>'
        '<a href="/contact.html">Contact</a>'
        "</div>"
        '<div class="footer-copy">This site contains affiliate links — we may earn a commission at no extra cost to you · Auto-updated daily</div>'
        "</footer>"
        '<script type="text/javascript">'
        "function googleTranslateElementInit(){"
        "new google.translate.TranslateElement({pageLanguage:'en',layout:google.translate.TranslateElement.InlineLayout.SIMPLE,autoDisplay:false},'google_translate_element');}"
        "</script>"
        '<script src="//translate.google.com/translate_a/element.js?cb=googleTranslateElementInit"></script>'
    )


def wrap_page(head_content, body_content, title="AIEarn.today"):
    return (
        "<!DOCTYPE html>"
        '<html lang="en">'
        "<head>"
        + head_content
        + "<!-- Google tag (gtag.js) -->"
        + GA_TAG
        + "</head>"
        "<body>"
        + body_content
        + "</body></html>"
    )

# ── 6. GENERATE INDIVIDUAL ARTICLE PAGE ──────────────────────────────────────

ARTICLE_CSS = """<style>
.article-wrap{max-width:780px;margin:0 auto;padding:40px 32px 60px;}
.article-kicker{font-family:var(--mono);font-size:10px;letter-spacing:.15em;text-transform:uppercase;color:var(--red);font-weight:700;margin-bottom:12px;}
.article-title{font-family:var(--serif);font-size:38px;font-weight:700;line-height:1.15;letter-spacing:-.02em;margin-bottom:16px;color:var(--ink);}
.article-deck{font-size:18px;color:var(--ink3);line-height:1.6;margin-bottom:20px;border-left:3px solid var(--red);padding-left:16px;}
.article-meta{font-family:var(--mono);font-size:10px;color:var(--ink4);margin-bottom:32px;padding-bottom:16px;border-bottom:1px solid var(--rule);display:flex;gap:16px;flex-wrap:wrap;}
.article-body{font-size:16px;line-height:1.8;color:var(--ink2);}
.article-body p{margin-bottom:20px;}
.article-body h2{font-family:var(--serif);font-size:24px;font-weight:700;margin:32px 0 14px;color:var(--ink);border-top:2px solid var(--rule);padding-top:20px;}
.article-body h3{font-family:var(--sans);font-size:18px;font-weight:700;margin:24px 0 10px;color:var(--ink);}
.article-body ul,.article-body ol{padding-left:24px;margin-bottom:20px;}
.article-body li{margin-bottom:8px;}
.article-body strong{color:var(--ink);font-weight:700;}
.article-source{margin-top:32px;padding:16px;background:var(--bg2);border:1px solid var(--rule);font-family:var(--mono);font-size:11px;color:var(--ink3);}
.article-source a{color:var(--red);}
.back-link{display:inline-block;font-family:var(--mono);font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:var(--ink3);text-decoration:none;margin:20px 0;padding:6px 0;}
.back-link:hover{color:var(--red);}
.related-box{margin-top:40px;padding-top:20px;border-top:3px solid var(--ink);}
.related-box h4{font-family:var(--mono);font-size:10px;font-weight:700;letter-spacing:.15em;text-transform:uppercase;margin-bottom:16px;}
.related-link{display:block;padding:12px 0;border-bottom:1px solid var(--rule);text-decoration:none;color:var(--ink);font-weight:500;}
.related-link:hover{color:var(--red);}
.related-link span{font-family:var(--mono);font-size:9px;color:var(--ink4);display:block;margin-top:2px;}
@media(max-width:900px){.article-title{font-size:28px;}.article-wrap{padding:24px 20px 40px;}}
</style>"""


def generate_article_page(a):
    ARTICLES_DIR.mkdir(exist_ok=True)
    slug     = a.get("slug", re.sub(r"[^a-z0-9]+", "-", a["title_en"].lower())[:60])
    a["slug"] = slug
    filename = "articles/" + slug + ".html"

    if Path(filename).exists():
        print("  Skipping (exists): " + filename)
        return filename

    print("  Writing article: " + filename)
    full_text = write_full_article(a)
    cat  = a.get("category", "news")
    info = CAT_MAP.get(cat, CAT_MAP["news"])

    schema = (
        '<script type="application/ld+json">'
        '{"@context":"https://schema.org","@type":"Article",'
        '"headline":"' + a["title_en"] + '",'
        '"datePublished":"' + a.get("date", DATE_ISO) + '",'
        '"dateModified":"' + DATE_ISO + '",'
        '"author":{"@type":"Organization","name":"AIEarn.today"},'
        '"publisher":{"@type":"Organization","name":"AIEarn.today","url":"https://www.aimoneynews.com"},'
        '"description":"' + a.get("summary_en", "")[:150] + '"}'
        "</script>"
    )

    head = head_tags(
        a["title_en"],
        a.get("summary_en", "")[:155],
        "/" + filename,
        schema
    ) + ARTICLE_CSS

    body = (
        shared_header()
        + '<div class="container">'
        + '<div class="article-wrap">'
        + '<a href="/news.html" class="back-link">← Back to Daily News</a>'
        + '<div class="article-kicker">' + info["emoji"] + " " + info["label"] + "</div>"
        + '<h1 class="article-title">' + a["title_en"] + "</h1>"
        + '<p class="article-deck">' + a.get("summary_en", "") + "</p>"
        + '<div class="article-meta">'
        + "<span>By AIEarn Editorial</span>"
        + "<span>" + a.get("date", DATE_ISO) + "</span>"
        + "<span>" + a["source"] + "</span>"
        + "</div>"
        + '<div class="article-body">' + full_text + "</div>"
        + '<div class="article-source">Source: <a href="' + a["link"] + '" target="_blank" rel="noopener">' + a["source"] + "</a> — This article provides original analysis and commentary based on the source news.</div>"
        + '<div class="related-box"><h4>Continue Reading</h4>'
        + '<a href="/news-cat-' + cat + '.html" class="related-link">More ' + info["label"] + ' articles<span>Browse all ' + info["label"].lower() + ' news →</span></a>'
        + '<a href="/news.html" class="related-link">Today\'s AI News Index<span>All categories · Updated daily →</span></a>'
        + "</div>"
        + "</div></div>"
        + shared_footer()
    )

    html = wrap_page(head, body, a["title_en"] + " — AIEarn.today")
    write_page(filename, html)
    return filename

# ── 7. BUILD NEWS INDEX CARDS ─────────────────────────────────────────────────

def build_card(rank, a):
    cat      = a.get("category", "news")
    info     = CAT_MAP.get(cat, CAT_MAP["news"])
    date_str = a.get("date", DATE_ISO)
    slug     = a.get("slug", "")
    article_url = ("/articles/" + slug + ".html") if slug else a["link"]
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
        + '<h3><a href="' + article_url + '">' + a["title_en"] + "</a></h3>"
        + "<p>" + a.get("summary_en", "") + "</p>"
        + '<div class="article-tags">' + hot_tag + af_tag + src_tag + "</div>"
        + '<div class="article-source">Source: <a href="' + a["link"] + '" target="_blank">' + a["source"] + "</a> · <a href=\"" + article_url + "\">Read full article →</a></div>"
        + "</div>"
        + "</div>"
    )


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
        slug = a.get("slug", "")
        url  = ("/articles/" + slug + ".html") if slug else a["link"]
        parts.append(
            '<div class="digest-item">'
            + '<div class="di-cat">' + info["emoji"] + " " + info["label"] + "</div>"
            + '<h3><a href="' + url + '">' + a["title_en"] + "</a></h3>"
            + "<p>" + a.get("summary_en", "")[:140] + "...</p>"
            + '<div class="di-src">Source: ' + a["source"] + " · " + DATE_EN + "</div>"
            + "</div>"
        )
    return "\n".join(parts)


def build_pagination(current_page, total_pages, base="news"):
    if total_pages <= 1:
        return ""
    def page_url(n):
        return "/news.html" if n == 1 else "/news-" + str(n) + ".html"
    if "cat" in base:
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

# ── 8. WRITE PAGE ─────────────────────────────────────────────────────────────

def write_page(filename, html):
    if "G-J29S2PGT2W" not in html:
        ga = "<!-- Google tag (gtag.js) -->" + GA_TAG
        html = html.replace("</head>", ga + "</head>", 1)
    Path(filename).write_text(html, encoding="utf-8")
    print("  Written: " + filename)

# ── 9. INJECT INTO TEMPLATE ───────────────────────────────────────────────────

def inject(filepath, zones):
    text = Path(filepath).read_text(encoding="utf-8")
    for zone_id, html in zones.items():
        begin = "<!-- BEGIN:" + zone_id + " -->"
        end   = "<!-- END:"   + zone_id + " -->"
        if begin in text and end in text:
            start = text.index(begin) + len(begin)
            stop  = text.index(end)
            text  = text[:start] + "\n" + html + "\n" + text[stop:]
            print("  OK: " + zone_id + " injected")
        else:
            print("  MISSING marker: " + zone_id)
    Path(filepath).write_text(text, encoding="utf-8")

# ── 10. GENERATE ALL PAGES ────────────────────────────────────────────────────

def generate_paginated_pages(all_articles, template):
    total   = len(all_articles)
    n_pages = max(1, -(-total // PER_PAGE))
    today   = [a for a in all_articles if a.get("date") == DATE_ISO]
    digest  = build_digest(today if today else all_articles[:3])

    print("\n[PAGES] {} articles → {} pages".format(total, n_pages))

    for page_num in range(1, n_pages + 1):
        chunk    = all_articles[(page_num-1)*PER_PAGE : page_num*PER_PAGE]
        cards    = "\n".join(build_card((page_num-1)*PER_PAGE + i + 1, a) for i, a in enumerate(chunk))
        pager    = build_pagination(page_num, n_pages)
        filename = "news.html" if page_num == 1 else "news-" + str(page_num) + ".html"
        page_html = template
        page_html = _inject_zone(page_html, "digest-grid",  digest)
        page_html = _inject_zone(page_html, "article-list", cards + "\n" + pager)
        write_page(filename, page_html)

    return n_pages


def generate_category_pages(all_articles, template):
    print("\n[CATEGORY PAGES]")
    for cat in CATEGORIES:
        cat_arts = [a for a in all_articles if a.get("category") == cat]
        if not cat_arts:
            continue
        info    = CAT_MAP[cat]
        n_pages = max(1, -(-len(cat_arts) // PER_PAGE))
        base    = "news-cat-" + cat
        for page_num in range(1, n_pages + 1):
            chunk    = cat_arts[(page_num-1)*PER_PAGE : page_num*PER_PAGE]
            cards    = "\n".join(build_card((page_num-1)*PER_PAGE + i + 1, a) for i, a in enumerate(chunk))
            pager    = build_pagination(page_num, n_pages, base=base)
            filename = base + ".html" if page_num == 1 else base + "-" + str(page_num) + ".html"
            digest   = ('<div class="digest-item"><div class="di-cat">' + info["emoji"] + " " + info["label"]
                        + '</div><h3>' + str(len(cat_arts)) + " " + info["label"] + " articles</h3>"
                        + "<p>All " + info["label"].lower() + " articles on AIEarn.today, updated daily.</p></div>" * 3)
            page_html = _inject_zone(template, "digest-grid",  digest)
            page_html = _inject_zone(page_html, "article-list", cards + "\n" + pager)
            write_page(filename, page_html)
        print("  {} → {} pages".format(cat, n_pages))


def _inject_zone(html, zone_id, content):
    begin = "<!-- BEGIN:" + zone_id + " -->"
    end   = "<!-- END:"   + zone_id + " -->"
    if begin in html and end in html:
        start = html.index(begin) + len(begin)
        stop  = html.index(end)
        return html[:start] + "\n" + content + "\n" + html[stop:]
    return html


def update_homepage(articles):
    hp = Path("index.html")
    if not hp.exists():
        return
    content = hp.read_text(encoding="utf-8")
    def build_col(cat, n=4):
        col_arts = [a for a in articles if a["category"] == cat][:n]
        col_html = ""
        for i, a in enumerate(col_arts):
            slug = a.get("slug", "")
            url  = ("/articles/" + slug + ".html") if slug else a["link"]
            pill = '<span class="pill pill-new">New</span>' if i == 0 else ""
            col_html += (
                '<div class="news-item">'
                + pill
                + '<a href="' + url + '">' + a["title_en"] + "</a>"
                + '<div class="news-meta">' + a["source"] + " · " + DATE_EN + "</div>"
                + "</div>"
            )
        return col_html
    for zone_id, cat in [("col-tool","tool"),("col-money","money"),("col-course","course"),("col-prompt","prompt")]:
        content = _inject_zone(content, zone_id, build_col(cat))
    hp.write_text(content, encoding="utf-8")
    print("  index.html updated")

# ── 11. SITEMAP ───────────────────────────────────────────────────────────────

def generate_sitemap(all_articles, n_main_pages):
    base  = "https://www.aimoneynews.com"
    urls  = []
    urls.append((base + "/", DATE_ISO, "daily", "1.0"))
    urls.append((base + "/news.html", DATE_ISO, "daily", "0.9"))
    for n in range(2, n_main_pages + 1):
        urls.append((base + "/news-" + str(n) + ".html", DATE_ISO, "daily", "0.8"))
    for cat in CATEGORIES:
        urls.append((base + "/news-cat-" + cat + ".html", DATE_ISO, "weekly", "0.7"))
    for a in all_articles:
        slug = a.get("slug", "")
        if slug:
            urls.append((base + "/articles/" + slug + ".html", a.get("date", DATE_ISO), "monthly", "0.6"))
    static = [("about", "monthly", "0.5"), ("contact", "monthly", "0.5"),
              ("privacy-policy", "monthly", "0.4"), ("affiliate-disclosure", "monthly", "0.4")]
    for page, freq, pri in static:
        urls.append((base + "/" + page + ".html", DATE_ISO, freq, pri))
    lines = ['<?xml version="1.0" encoding="UTF-8"?>']
    lines.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
    for url, lastmod, freq, priority in urls:
        lines.append("  <url>")
        lines.append("    <loc>" + url + "</loc>")
        lines.append("    <lastmod>" + lastmod + "</lastmod>")
        lines.append("    <changefreq>" + freq + "</changefreq>")
        lines.append("    <priority>" + priority + "</priority>")
        lines.append("  </url>")
    lines.append("</urlset>")
    Path("sitemap.xml").write_text("\n".join(lines), encoding="utf-8")
    print("  sitemap.xml → " + str(len(urls)) + " URLs")

# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("AIEarn.today Auto-Update -- {} {}".format(DATE_EN, WEEKDAY))
    print("=" * 60)

    # 1. Fetch RSS
    items = fetch_rss(max_per_feed=8)
    if not items:
        print("[ERROR] No RSS items. Aborting.")
        return

    # 2. Select & classify topics (20 items for index, 5 for full articles)
    all_topics = select_topics(items, count=20)

    # 3. Write full articles for top 5 (new ones only)
    print("\n[FULL ARTICLES] Writing {} long-form articles...".format(ARTICLES_PER_RUN))
    ARTICLES_DIR.mkdir(exist_ok=True)
    full_article_count = 0
    for a in all_topics[:ARTICLES_PER_RUN]:
        slug = a.get("slug", re.sub(r"[^a-z0-9]+", "-", a["title_en"].lower())[:60])
        a["slug"] = slug
        if not Path("articles/" + slug + ".html").exists():
            generate_article_page(a)
            full_article_count += 1
        else:
            print("  Exists: articles/" + slug + ".html")

    print("[FULL ARTICLES] {} new articles written".format(full_article_count))

    # 4. Merge with archive
    all_articles = load_all_articles()
    all_articles = merge_articles(all_articles, all_topics)
    save_all_articles(all_articles)

    # Daily archive
    Path("_archive").mkdir(exist_ok=True)
    (Path("_archive") / (DATE_ISO + ".json")).write_text(
        json.dumps(all_topics, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 5. Read news.html template and generate index pages
    if not Path("news.html").exists():
        print("[ERROR] news.html template not found")
        return
    template = Path("news.html").read_text(encoding="utf-8")

    print("\n[GENERATING INDEX PAGES]")
    n_main = generate_paginated_pages(all_articles, template)
    generate_category_pages(all_articles, template)
    generate_sitemap(all_articles, n_main)

    # 6. Update homepage
    print("\n[index.html]")
    update_homepage(all_topics)

    print("\n" + "=" * 60)
    print("Done! {} total · {} pages · {} new full articles today".format(
        len(all_articles), n_main, full_article_count))
    print("=" * 60)


if __name__ == "__main__":
    main()
