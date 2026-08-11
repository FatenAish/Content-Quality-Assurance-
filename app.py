
import re
import json
import time
import html as html_lib
from collections import Counter
from difflib import SequenceMatcher
from urllib.parse import urljoin, urlparse

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup

# =========================================================
# BAYUT URL QUALITY AUDITOR
# Single URL audit: Spam + SEO + Content
# =========================================================

BAYUT_GREEN = "#28B16D"
BAYUT_DARK = "#1F2D2A"
BAYUT_LIGHT = "#F4FBF7"
BORDER = "#E4E9E7"
TEXT_MUTED = "#66736F"
FAIL = "FAIL"
REVIEW = "REVIEW"
PASS = "PASS"

CURRENT_YEAR = 2026

st.set_page_config(
    page_title="Bayut URL Quality Auditor",
    page_icon="🔎",
    layout="wide",
)

st.markdown(
    f"""
    <style>
    .stApp {{
        background: #ffffff;
        color: {BAYUT_DARK};
    }}
    .block-container {{
        padding-top: 1.4rem;
        padding-bottom: 3rem;
        max-width: 1380px;
    }}
    .bayut-header {{
        display:flex;
        align-items:center;
        justify-content:space-between;
        padding: 18px 22px;
        border: 1px solid {BORDER};
        border-radius: 16px;
        background: linear-gradient(135deg, #ffffff 0%, {BAYUT_LIGHT} 100%);
        margin-bottom: 18px;
    }}
    .brand {{
        font-size: 31px;
        font-weight: 800;
        letter-spacing: -0.8px;
        color: {BAYUT_GREEN};
    }}
    .subtitle {{
        font-size: 14px;
        color: {TEXT_MUTED};
        margin-top: 2px;
    }}
    .pill {{
        border: 1px solid {BORDER};
        border-radius: 999px;
        padding: 8px 12px;
        font-size: 12px;
        font-weight: 700;
        background:#fff;
    }}
    .metric-card {{
        border: 1px solid {BORDER};
        border-radius: 14px;
        padding: 15px 16px;
        background:#fff;
        min-height: 105px;
    }}
    .metric-label {{
        color:{TEXT_MUTED};
        font-size:12px;
        font-weight:700;
        text-transform:uppercase;
        letter-spacing:.4px;
    }}
    .metric-value {{
        font-size:25px;
        font-weight:800;
        margin-top:5px;
    }}
    .metric-note {{
        color:{TEXT_MUTED};
        font-size:12px;
        margin-top:5px;
    }}
    .status-pass {{ color: {BAYUT_GREEN}; font-weight:800; }}
    .status-review {{ color: #B7791F; font-weight:800; }}
    .status-fail {{ color: #C53030; font-weight:800; }}
    div.stButton > button {{
        background:{BAYUT_GREEN};
        color:white;
        border:0;
        border-radius:10px;
        font-weight:750;
        padding:.65rem 1.2rem;
    }}
    div.stButton > button:hover {{
        background:#21965D;
        color:white;
        border:0;
    }}
    div[data-baseweb="input"] > div {{
        border-radius:10px;
    }}
    .section-title {{
        font-size:21px;
        font-weight:800;
        margin-top:6px;
        margin-bottom:2px;
    }}
    .small-note {{
        color:{TEXT_MUTED};
        font-size:12px;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

# -----------------------------
# Rule library
# -----------------------------

SPAM_RULES = [
    ("Cloaking", "Compare normal-user and Googlebot responses. FAIL when materially different content is served specifically to search crawlers."),
    ("Sneaky Redirect", "FAIL when crawler and user are sent to materially different destinations or users are deceptively redirected."),
    ("Device Spam Redirect", "FAIL when mobile/device users are redirected to unrelated or spam destinations while other visitors are not."),
    ("Hidden Text", "FAIL when substantial SEO-oriented text is intentionally hidden from users. Legitimate UI/accessibility hiding is not spam."),
    ("Hidden Links", "FAIL when links are deliberately invisible, tiny, off-screen or otherwise concealed for ranking manipulation."),
    ("Keyword Stuffing", "FAIL when keywords, locations or query phrases are repeated unnaturally for rankings."),
    ("Scraped Content", "FAIL when substantial external content is copied or lightly transformed with little original value. Requires external comparison."),
    ("Link Spam", "FAIL when links are clearly created or inserted primarily to manipulate rankings."),
    ("Paid Links", "FAIL when identifiable paid/sponsored links pass ranking credit without appropriate sponsored/nofollow qualification."),
    ("Hacked Content", "FAIL when unauthorized spam text, pages, links or redirects are injected."),
    ("Spam JavaScript", "FAIL when scripts inject spam content, hidden links or deceptive redirects."),
    ("Spam Iframes", "FAIL when unauthorized/suspicious iframes introduce deceptive or spam content."),
    ("Site Reputation Abuse", "FAIL when unrelated third-party content primarily exploits the host site's ranking signals. Often needs manual context."),
    ("User-Generated Spam", "FAIL when comments/profiles/UGC contain mass spam or manipulative links."),
    ("Back Button Hijacking", "FAIL when scripts manipulate browser history to prevent users from returning to the previous page."),
    ("Malware / Scam Behaviour", "FAIL when malicious downloads, harmful scripts, impersonation or deliberately deceptive functionality is detected."),
]

SEO_RULES = [
    ("HTTP Status", "PASS when the canonical live article returns HTTP 200."),
    ("Indexability", "FAIL when an intended indexable article contains noindex."),
    ("Robots", "FAIL when Googlebot is unintentionally blocked by page-level robots directives."),
    ("Canonical", "PASS when a valid canonical points to the correct preferred URL."),
    ("Title Tag", "PASS when a relevant, non-empty title exists and is not excessively long or stuffed."),
    ("Meta Description", "PASS when a useful, relevant meta description exists."),
    ("H1", "PASS when a clear relevant H1 exists."),
    ("Heading Structure", "REVIEW when headings are empty, highly repetitive, or structurally confusing."),
    ("URL Structure", "REVIEW when the URL is malformed, misleading, or dominated by unnecessary parameters."),
    ("Internal Links", "REVIEW/FAIL when important crawlable internal links are broken."),
    ("External Links", "REVIEW when external links are broken or clearly irrelevant."),
    ("Images", "REVIEW when meaningful images are broken or lack useful alt text."),
    ("Structured Data", "PASS when JSON-LD is parseable and represents visible page content; REVIEW invalid/missing data where expected."),
    ("datePublished", "PASS when a valid publication date is present where the article schema provides it."),
    ("dateModified", "REVIEW when the modification date is missing, malformed, or inconsistent with visible metadata."),
    ("Sitemap", "PASS when the preferred URL is present in an accessible sitemap where expected."),
    ("Mobile Content", "REVIEW/FAIL when mobile receives materially less main content than desktop."),
    ("JavaScript Rendering", "REVIEW when the initial HTML contains very little article text and depends heavily on scripts."),
    ("HTTPS", "PASS when the preferred page uses HTTPS."),
    ("Broken Resources", "REVIEW when important linked resources appear broken."),
]

CONTENT_RULES = [
    ("Search Intent", "PASS when the main content directly addresses the topic promised by the title/H1."),
    ("Content Relevance", "REVIEW/FAIL when substantial sections are unrelated to the page topic."),
    ("Thin Content", "System heuristic: PASS at 600+ meaningful words, REVIEW at 300–599, FAIL below 300. This is not a Google word-count rule."),
    ("Original Value", "PASS when the page adds useful data, examples, analysis or first-hand value. External/site comparison may be required."),
    ("Factual Accuracy", "FAIL confirmed false claims; REVIEW claims that require source verification."),
    ("Outdated Information", "REVIEW when time-sensitive claims appear stale or reference old years without context."),
    ("Keyword Use", "PASS when important terms are used naturally; FAIL obvious unnatural repetition."),
    ("Repetition", "REVIEW/FAIL when sentences or paragraphs are unnecessarily repeated."),
    ("Generic / Filler Content", "REVIEW when a high share of text adds little topic-specific information."),
    ("Title vs Content", "PASS when title terms/topic are strongly represented in the body."),
    ("H1 vs Content", "PASS when H1 accurately represents the main body."),
    ("Heading Relevance", "REVIEW when multiple headings have weak topical relation to the title/H1."),
    ("Introduction Quality", "PASS when the opening quickly establishes the promised topic."),
    ("FAQ Quality", "REVIEW when FAQ answers are empty, extremely short, repetitive or unrelated."),
    ("Unsupported Superlatives", "REVIEW claims such as best, cheapest, highest, most popular when no evidence/source is apparent."),
    ("Source Quality", "REVIEW important quantitative/regulatory claims with no visible source where sourcing is reasonably expected."),
    ("Data Accuracy", "REVIEW inconsistent prices, percentages, dates or repeated figures inside the page."),
    ("Entity Accuracy", "REVIEW names of projects, areas, schools, developers and organisations that require external verification."),
    ("Grammar / Readability", "REVIEW when sentence structure is consistently difficult to read or text is obviously malformed."),
    ("Broken Content", "FAIL obvious placeholders/unfinished output; REVIEW empty headings or duplicated content blocks."),
]

# -----------------------------
# Helpers
# -----------------------------

UA_DESKTOP = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151.0.0.0 Safari/537.36"
}
UA_MOBILE = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36 Chrome/151.0 Mobile Safari/537.36"
}
UA_GOOGLEBOT = {
    "User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
}

def normalize_url(url):
    url = (url or "").strip()
    if not url:
        return ""
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    return url

def fetch(url, headers, timeout=16):
    start = time.time()
    r = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
    elapsed = time.time() - start
    return r, elapsed

def soup_of(html):
    return BeautifulSoup(html or "", "html.parser")

def clean_text(soup):
    clone = BeautifulSoup(str(soup), "html.parser")
    for tag in clone(["script", "style", "noscript", "svg", "template"]):
        tag.decompose()
    text = " ".join(clone.stripped_strings)
    return re.sub(r"\s+", " ", text).strip()

def main_content_text(soup):
    candidates = []
    for selector in ["article", "main", "[role='main']", ".entry-content", ".post-content", ".article-content", ".content"]:
        for node in soup.select(selector):
            t = clean_text(node)
            if len(t) > 200:
                candidates.append(t)
    if candidates:
        return max(candidates, key=len)
    return clean_text(soup.body or soup)

def similarity(a, b):
    a, b = (a or "")[:40000], (b or "")[:40000]
    if not a and not b:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()

def tokenize(text):
    return re.findall(r"[A-Za-zÀ-ÿ\u0600-\u06FF0-9']+", (text or "").lower())

def word_count(text):
    return len(tokenize(text))

def top_ngram_density(text, n=2):
    words = [w for w in tokenize(text) if len(w) > 2]
    if len(words) < n:
        return ("", 0.0, 0)
    grams = [" ".join(words[i:i+n]) for i in range(len(words)-n+1)]
    counts = Counter(grams)
    gram, count = counts.most_common(1)[0]
    return gram, count / max(1, len(grams)), count

def title_text(soup):
    return soup.title.get_text(" ", strip=True) if soup.title else ""

def meta_content(soup, name=None, prop=None):
    if name:
        tag = soup.find("meta", attrs={"name": re.compile(f"^{re.escape(name)}$", re.I)})
    else:
        tag = soup.find("meta", attrs={"property": re.compile(f"^{re.escape(prop)}$", re.I)})
    return (tag.get("content") or "").strip() if tag else ""

def first_h1(soup):
    h = soup.find("h1")
    return h.get_text(" ", strip=True) if h else ""

def canonical_href(soup):
    tag = soup.find("link", rel=lambda x: x and "canonical" in [str(i).lower() for i in (x if isinstance(x, list) else [x])])
    return (tag.get("href") or "").strip() if tag else ""

def keyword_overlap(a, b):
    stop = {
        "the","and","for","with","from","this","that","your","you","are","our","in","on","of","to","a","an","is",
        "في","من","على","إلى","الى","عن","هذا","هذه","مع","و","أو","او","ما","هو","هي","التي","الذي"
    }
    aa = {x for x in tokenize(a) if len(x) > 2 and x not in stop}
    bb = {x for x in tokenize(b) if len(x) > 2 and x not in stop}
    if not aa:
        return 0.0
    return len(aa & bb) / len(aa)

def status_class(s):
    return {"PASS":"status-pass","REVIEW":"status-review","FAIL":"status-fail"}.get(s, "")

def result(name, status, finding, rule):
    return {"Check": name, "Status": status, "Finding": finding, "Rule": rule}

def robots_directives(soup):
    values = []
    for tag in soup.find_all("meta"):
        n = (tag.get("name") or "").lower()
        if n in {"robots", "googlebot"}:
            values.append((tag.get("content") or "").lower())
    return ", ".join(values)

def parse_jsonld(soup):
    parsed, errors = [], 0
    for tag in soup.find_all("script", attrs={"type": re.compile("ld\\+json", re.I)}):
        raw = tag.string or tag.get_text()
        if not raw.strip():
            continue
        try:
            parsed.append(json.loads(raw))
        except Exception:
            errors += 1
    return parsed, errors

def walk_json(obj):
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from walk_json(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk_json(v)

def get_schema_values(jsonld, key):
    vals = []
    for root in jsonld:
        for obj in walk_json(root):
            if isinstance(obj, dict) and key in obj:
                vals.append(obj[key])
    return vals

def obvious_hidden(node):
    style = (node.get("style") or "").replace(" ", "").lower()
    hidden_attr = node.has_attr("hidden")
    aria_hidden = (node.get("aria-hidden") or "").lower() == "true"
    bad_style = any(x in style for x in [
        "display:none", "visibility:hidden", "opacity:0",
        "font-size:0", "height:0", "width:0", "left:-9999", "text-indent:-9999"
    ])
    return hidden_attr or bad_style or aria_hidden

def repeated_sentence_ratio(text):
    sents = [re.sub(r"\s+", " ", s.strip().lower()) for s in re.split(r"[.!?؟]+", text) if len(s.strip()) >= 35]
    if not sents:
        return 0.0, []
    counts = Counter(sents)
    repeated = [s for s,c in counts.items() if c > 1]
    duplicate_instances = sum(counts[s]-1 for s in repeated)
    return duplicate_instances / len(sents), repeated[:4]

def repeated_paragraph_ratio(soup):
    paras = []
    for p in soup.find_all("p"):
        t = re.sub(r"\s+", " ", p.get_text(" ", strip=True).lower())
        if len(t) >= 80:
            paras.append(t)
    if not paras:
        return 0.0, []
    counts = Counter(paras)
    repeated = [p for p,c in counts.items() if c > 1]
    duplicate_instances = sum(counts[p]-1 for p in repeated)
    return duplicate_instances / len(paras), repeated[:3]

def looks_time_sensitive(text):
    keys = [
        "price","prices","rent","rental","sale price","roi","yield","visa","law","rule","fee","fees","bus route",
        "metro","project status","completion","handover","aed","%","سعر","أسعار","ايجار","إيجار","قانون","رسوم","مترو"
    ]
    low = text.lower()
    return any(k in low for k in keys)

def old_years(text):
    years = [int(y) for y in re.findall(r"\b20(?:1\d|2\d)\b", text)]
    return sorted(set(y for y in years if y <= CURRENT_YEAR - 2))

def classify_counts(rows):
    c = Counter(r["Status"] for r in rows)
    if c[FAIL]:
        overall = FAIL
    elif c[REVIEW]:
        overall = REVIEW
    else:
        overall = PASS
    return overall, c

# -----------------------------
# Spam audit
# -----------------------------

def audit_spam(url, desktop_r, mobile_r, bot_r, soup, body_text):
    rows = []
    rules = dict(SPAM_RULES)

    desktop_text = body_text
    bot_text = main_content_text(soup_of(bot_r.text))
    mobile_text = main_content_text(soup_of(mobile_r.text))

    sim_bot = similarity(desktop_text, bot_text)
    if desktop_r.url != bot_r.url:
        rows.append(result("Cloaking", FAIL, f"User final URL and Googlebot final URL differ: {desktop_r.url} vs {bot_r.url}", rules["Cloaking"]))
    elif sim_bot < 0.72 and min(word_count(desktop_text), word_count(bot_text)) > 150:
        rows.append(result("Cloaking", FAIL, f"Material user/Googlebot content difference detected ({sim_bot:.0%} similarity).", rules["Cloaking"]))
    elif sim_bot < 0.88:
        rows.append(result("Cloaking", REVIEW, f"User/Googlebot content similarity is {sim_bot:.0%}; review dynamic/personalised content.", rules["Cloaking"]))
    else:
        rows.append(result("Cloaking", PASS, f"User/Googlebot content similarity is {sim_bot:.0%}.", rules["Cloaking"]))

    if desktop_r.url != bot_r.url:
        st_redirect = FAIL
        note = f"Different final destinations: user → {desktop_r.url}; bot → {bot_r.url}"
    else:
        st_redirect = PASS
        note = f"Same final destination for user and crawler: {desktop_r.url}"
    rows.append(result("Sneaky Redirect", st_redirect, note, rules["Sneaky Redirect"]))

    if mobile_r.url != desktop_r.url:
        rows.append(result("Device Spam Redirect", FAIL, f"Mobile final URL differs from desktop: {mobile_r.url}", rules["Device Spam Redirect"]))
    else:
        sm = similarity(desktop_text, mobile_text)
        rows.append(result("Device Spam Redirect", PASS if sm >= 0.80 else REVIEW, f"Desktop/mobile final URL matches; content similarity {sm:.0%}.", rules["Device Spam Redirect"]))

    hidden_nodes = []
    hidden_links = []
    for node in soup.find_all(True):
        if obvious_hidden(node):
            t = node.get_text(" ", strip=True)
            if len(t) >= 40:
                hidden_nodes.append(t[:180])
            if node.name == "a" and node.get("href"):
                hidden_links.append(node.get("href"))
            for a in node.find_all("a", href=True):
                hidden_links.append(a.get("href"))

    if len(hidden_nodes) >= 3:
        rows.append(result("Hidden Text", REVIEW, f"Found {len(hidden_nodes)} substantial hidden text blocks. Manual intent review required.", rules["Hidden Text"]))
    else:
        rows.append(result("Hidden Text", PASS, f"No clear spam-scale hidden text pattern found ({len(hidden_nodes)} substantial hidden blocks).", rules["Hidden Text"]))

    if hidden_links:
        rows.append(result("Hidden Links", REVIEW, f"Found {len(set(hidden_links))} link(s) inside hidden elements. Review whether they are legitimate UI/accessibility elements.", rules["Hidden Links"]))
    else:
        rows.append(result("Hidden Links", PASS, "No links found inside obvious hidden elements.", rules["Hidden Links"]))

    gram, density, count = top_ngram_density(body_text, 2)
    if count >= 20 and density >= 0.035:
        kstatus = FAIL
    elif count >= 12 and density >= 0.022:
        kstatus = REVIEW
    else:
        kstatus = PASS
    rows.append(result("Keyword Stuffing", kstatus, f"Most repeated 2-word phrase: “{gram}” — {count} uses ({density:.1%} of bigrams).", rules["Keyword Stuffing"]))

    rows.append(result("Scraped Content", REVIEW, "A single fetched URL cannot prove external copying. Run an external similarity/search comparison before marking PASS/FAIL.", rules["Scraped Content"]))

    parsed = urlparse(url)
    host = parsed.netloc.lower().replace("www.", "")
    anchors = soup.find_all("a", href=True)
    external = []
    for a in anchors:
        href = urljoin(url, a.get("href"))
        p = urlparse(href)
        if p.scheme in {"http","https"} and p.netloc and p.netloc.lower().replace("www.","") != host:
            external.append((a, href))
    keyword_rich = 0
    for a, href in external:
        txt = a.get_text(" ", strip=True)
        if len(tokenize(txt)) >= 4:
            keyword_rich += 1
    if len(external) > 60 or (len(external) >= 12 and keyword_rich / max(1,len(external)) > .65):
        link_status = REVIEW
        finding = f"{len(external)} external links; {keyword_rich} have 4+ word anchor text. Review link intent."
    else:
        link_status = PASS
        finding = f"{len(external)} external links found; no clear automated link-spam pattern."
    rows.append(result("Link Spam", link_status, finding, rules["Link Spam"]))

    paid_candidates = 0
    paid_bad = 0
    for a, href in external:
        context = (a.get_text(" ", strip=True) + " " + (a.parent.get_text(" ", strip=True) if a.parent else "")).lower()
        if any(k in context for k in ["sponsored", "advertisement", "advertorial", "paid partnership", "affiliate"]):
            paid_candidates += 1
            rel = {str(x).lower() for x in (a.get("rel") or [])}
            if not ({"sponsored","nofollow"} & rel):
                paid_bad += 1
    if paid_bad:
        ps = FAIL
        pf = f"{paid_bad} identifiable paid/sponsored link(s) lack sponsored/nofollow qualification."
    elif paid_candidates:
        ps = PASS
        pf = f"{paid_candidates} paid/sponsored candidate link(s) found and qualified."
    else:
        ps = PASS
        pf = "No clearly identifiable paid/sponsored links detected from visible context."
    rows.append(result("Paid Links", ps, pf, rules["Paid Links"]))

    hacked_terms = ["viagra","cialis","casino","slot gacor","online casino","betting bonus","levitra","payday loan"]
    low = body_text.lower()
    hacked_hits = [x for x in hacked_terms if x in low]
    if len(hacked_hits) >= 2:
        hs = FAIL
    elif hacked_hits:
        hs = REVIEW
    else:
        hs = PASS
    rows.append(result("Hacked Content", hs, ("Suspicious terms: " + ", ".join(hacked_hits)) if hacked_hits else "No common injected-spam signatures detected.", rules["Hacked Content"]))

    script_text = "\n".join((s.string or s.get_text() or "") for s in soup.find_all("script"))
    suspicious_js = []
    for pattern in ["window.location", "location.replace(", "document.location", "eval(atob(", "fromCharCode("]:
        if pattern.lower() in script_text.lower():
            suspicious_js.append(pattern)
    js_status = REVIEW if len(suspicious_js) >= 2 else PASS
    rows.append(result("Spam JavaScript", js_status, f"Suspicious redirect/obfuscation indicators: {', '.join(suspicious_js) if suspicious_js else 'none detected'}.", rules["Spam JavaScript"]))

    iframes = soup.find_all("iframe")
    hidden_iframes = [i for i in iframes if obvious_hidden(i)]
    if hidden_iframes:
        iframe_status = REVIEW
        iframe_find = f"Found {len(hidden_iframes)} hidden iframe(s); verify purpose and source."
    else:
        iframe_status = PASS
        iframe_find = f"{len(iframes)} iframe(s) found; none obviously hidden."
    rows.append(result("Spam Iframes", iframe_status, iframe_find, rules["Spam Iframes"]))

    rows.append(result("Site Reputation Abuse", REVIEW, "URL-only analysis can flag unrelated third-party content, but confirming reputation abuse requires editorial/ownership context.", rules["Site Reputation Abuse"]))

    comment_nodes = soup.select(".comment, .comments, [id*='comment'], [class*='comment']")
    ugc_links = 0
    for n in comment_nodes:
        ugc_links += len(n.find_all("a", href=True))
    ugc_status = REVIEW if ugc_links >= 10 else PASS
    rows.append(result("User-Generated Spam", ugc_status, f"Detected {ugc_links} links in comment/UGC-like containers.", rules["User-Generated Spam"]))

    lower_js = script_text.lower()
    hijack = ("popstate" in lower_js and ("pushstate" in lower_js or "replacestate" in lower_js) and ("location" in lower_js or "redirect" in lower_js))
    rows.append(result("Back Button Hijacking", FAIL if hijack else PASS, "Browser-history redirect pattern detected." if hijack else "No obvious browser-history hijacking pattern detected.", rules["Back Button Hijacking"]))

    malware_signals = sum(1 for x in ["eval(atob(", "unescape(", "document.write('<script", 'document.write("<script'] if x in lower_js)
    if malware_signals >= 2:
        ms = REVIEW
        mf = "Multiple script-obfuscation/injection patterns detected; security review required."
    else:
        ms = PASS
        mf = "No strong malware/scam script signature detected by static HTML scan."
    rows.append(result("Malware / Scam Behaviour", ms, mf, rules["Malware / Scam Behaviour"]))

    return rows

# -----------------------------
# SEO audit
# -----------------------------

def audit_seo(url, desktop_r, desktop_elapsed, mobile_r, soup, body_text):
    rows = []
    rules = dict(SEO_RULES)

    code = desktop_r.status_code
    rows.append(result("HTTP Status", PASS if code == 200 else FAIL, f"HTTP {code}.", rules["HTTP Status"]))

    robots = robots_directives(soup)
    if "noindex" in robots:
        rows.append(result("Indexability", FAIL, f"Page-level robots directive contains noindex: {robots}", rules["Indexability"]))
    else:
        rows.append(result("Indexability", PASS, f"No page-level noindex detected{': ' + robots if robots else ''}.", rules["Indexability"]))

    if "none" in robots or "noindex" in robots or "nofollow" in robots:
        rs = REVIEW if "noindex" not in robots else FAIL
    else:
        rs = PASS
    rows.append(result("Robots", rs, robots or "No restrictive page-level robots meta detected.", rules["Robots"]))

    canonical = canonical_href(soup)
    if not canonical:
        cs = REVIEW
        cf = "Canonical tag not found."
    else:
        can_abs = urljoin(desktop_r.url, canonical)
        same_path = urlparse(can_abs).path.rstrip("/") == urlparse(desktop_r.url).path.rstrip("/")
        cs = PASS if same_path else REVIEW
        cf = f"Canonical: {can_abs}"
    rows.append(result("Canonical", cs, cf, rules["Canonical"]))

    title = title_text(soup)
    title_len = len(title)
    if not title:
        ts = FAIL
    elif title_len > 70 or title_len < 20:
        ts = REVIEW
    else:
        ts = PASS
    rows.append(result("Title Tag", ts, f"{title_len} characters — {title or 'missing'}", rules["Title Tag"]))

    meta = meta_content(soup, name="description")
    ml = len(meta)
    if not meta:
        md = REVIEW
    elif ml < 70 or ml > 180:
        md = REVIEW
    else:
        md = PASS
    rows.append(result("Meta Description", md, f"{ml} characters{': ' + meta[:180] if meta else ' — missing'}", rules["Meta Description"]))

    h1s = [h.get_text(" ", strip=True) for h in soup.find_all("h1") if h.get_text(" ", strip=True)]
    if len(h1s) == 1:
        h1_status = PASS
    elif len(h1s) == 0:
        h1_status = FAIL
    else:
        h1_status = REVIEW
    rows.append(result("H1", h1_status, f"{len(h1s)} H1(s) found" + (f": {h1s[0]}" if h1s else ""), rules["H1"]))

    headings = []
    empty_headings = 0
    for tag in soup.find_all(re.compile(r"^h[1-6]$")):
        txt = tag.get_text(" ", strip=True)
        if not txt:
            empty_headings += 1
        else:
            headings.append((tag.name, txt))
    dup_h = len(headings) - len(set(x[1].lower() for x in headings))
    hs = REVIEW if empty_headings or dup_h >= 3 else PASS
    rows.append(result("Heading Structure", hs, f"{len(headings)} populated headings; {empty_headings} empty; {dup_h} duplicate heading occurrence(s).", rules["Heading Structure"]))

    parsed = urlparse(desktop_r.url)
    q = parsed.query
    bad_chars = bool(re.search(r"\s|[<>\"{}|\\^`]", desktop_r.url))
    if bad_chars:
        us = FAIL
    elif len(q) > 80 or q.count("&") >= 4:
        us = REVIEW
    else:
        us = PASS
    rows.append(result("URL Structure", us, f"Path: {parsed.path}" + (f" | Query: {q[:120]}" if q else ""), rules["URL Structure"]))

    links = []
    for a in soup.find_all("a", href=True):
        href = urljoin(desktop_r.url, a.get("href"))
        if href.startswith(("http://","https://")):
            links.append(href)
    host = parsed.netloc.lower().replace("www.","")
    internal = [x for x in links if urlparse(x).netloc.lower().replace("www.","") == host]
    external = [x for x in links if urlparse(x).netloc.lower().replace("www.","") != host]
    rows.append(result("Internal Links", PASS if internal else REVIEW, f"{len(internal)} crawlable HTTP(S) internal links found.", rules["Internal Links"]))
    rows.append(result("External Links", PASS, f"{len(external)} external HTTP(S) links found. Full broken-link validation is intentionally not run against every target in this first version.", rules["External Links"]))

    imgs = soup.find_all("img")
    no_alt = [i for i in imgs if i.get("alt") is None]
    image_status = REVIEW if imgs and len(no_alt)/len(imgs) > .35 else PASS
    rows.append(result("Images", image_status, f"{len(imgs)} images; {len(no_alt)} missing alt attribute.", rules["Images"]))

    jsonld, json_errors = parse_jsonld(soup)
    if json_errors:
        sd = REVIEW
    elif jsonld:
        sd = PASS
    else:
        sd = REVIEW
    rows.append(result("Structured Data", sd, f"{len(jsonld)} valid JSON-LD block(s); {json_errors} parse error(s).", rules["Structured Data"]))

    published = get_schema_values(jsonld, "datePublished")
    modified = get_schema_values(jsonld, "dateModified")
    rows.append(result("datePublished", PASS if published else REVIEW, f"Schema datePublished: {published[:3] if published else 'not found'}", rules["datePublished"]))
    rows.append(result("dateModified", PASS if modified else REVIEW, f"Schema dateModified: {modified[:3] if modified else 'not found'}", rules["dateModified"]))

    # Sitemap check: lightweight, only common endpoints and only when response is reasonably sized.
    sitemap_found = False
    sitemap_contains = False
    checked = []
    origin = f"{parsed.scheme}://{parsed.netloc}"
    candidates = [urljoin(origin, "/sitemap.xml"), urljoin(origin, "/sitemap_index.xml")]
    for sm in candidates:
        try:
            rr = requests.get(sm, headers=UA_DESKTOP, timeout=8)
            checked.append((sm, rr.status_code))
            if rr.status_code == 200 and len(rr.content) < 8_000_000:
                sitemap_found = True
                if desktop_r.url.rstrip("/") in rr.text:
                    sitemap_contains = True
                    break
        except Exception:
            pass
    if sitemap_contains:
        ss = PASS
        sf = "Preferred URL found in a common sitemap endpoint."
    elif sitemap_found:
        ss = REVIEW
        sf = "Sitemap found, but URL was not found in the fetched top-level sitemap. It may be in a child sitemap."
    else:
        ss = REVIEW
        sf = "Common sitemap endpoints were not confirmed in this lightweight check."
    rows.append(result("Sitemap", ss, sf, rules["Sitemap"]))

    mobile_text = main_content_text(soup_of(mobile_r.text))
    sm = similarity(body_text, mobile_text)
    rows.append(result("Mobile Content", PASS if sm >= .80 else REVIEW, f"Desktop/mobile main-content similarity: {sm:.0%}.", rules["Mobile Content"]))

    script_count = len(soup.find_all("script"))
    wc = word_count(body_text)
    if wc < 150 and script_count >= 20:
        jr = REVIEW
        jf = f"Only {wc} extracted words with {script_count} scripts; rendered-content test recommended."
    else:
        jr = PASS
        jf = f"{wc} extracted words; {script_count} scripts. No obvious empty-HTML shell pattern."
    rows.append(result("JavaScript Rendering", jr, jf, rules["JavaScript Rendering"]))

    rows.append(result("HTTPS", PASS if parsed.scheme == "https" else FAIL, f"Preferred URL scheme: {parsed.scheme}", rules["HTTPS"]))

    resource_urls = []
    for tag, attr in [("script","src"),("link","href"),("img","src")]:
        for n in soup.find_all(tag):
            v = n.get(attr)
            if v and v.startswith(("http://","https://","/")):
                resource_urls.append(urljoin(desktop_r.url, v))
    rows.append(result("Broken Resources", REVIEW if not resource_urls else PASS, f"{len(resource_urls)} linked resource URLs discovered. Full resource crawl is not run in v1.", rules["Broken Resources"]))

    return rows

# -----------------------------
# Content audit
# -----------------------------

def audit_content(url, soup, body_text):
    rows = []
    rules = dict(CONTENT_RULES)
    title = title_text(soup)
    h1 = first_h1(soup)
    wc = word_count(body_text)

    title_overlap = keyword_overlap(title, body_text)
    if title_overlap >= .65:
        s = PASS
    elif title_overlap >= .35:
        s = REVIEW
    else:
        s = FAIL
    rows.append(result("Search Intent", s, f"{title_overlap:.0%} of meaningful title terms are represented in the page text.", rules["Search Intent"]))

    headings = [h.get_text(" ", strip=True) for h in soup.find_all(re.compile(r"^h[2-4]$")) if h.get_text(" ", strip=True)]
    weak = [h for h in headings if keyword_overlap(title or h1, h) < .10 and len(tokenize(h)) >= 3]
    rel_status = REVIEW if headings and len(weak)/len(headings) > .45 else PASS
    rows.append(result("Content Relevance", rel_status, f"{len(weak)} of {len(headings)} H2-H4 headings have very weak lexical overlap with the main topic.", rules["Content Relevance"]))

    thin_status = PASS if wc >= 600 else REVIEW if wc >= 300 else FAIL
    rows.append(result("Thin Content", thin_status, f"{wc:,} extracted meaningful words.", rules["Thin Content"]))

    value_signals = {
        "tables": len(soup.find_all("table")),
        "lists": len(soup.find_all(["ul","ol"])),
        "numbers": len(re.findall(r"\b\d+(?:[.,]\d+)?%?\b", body_text)),
    }
    if wc >= 800 and (value_signals["tables"] or value_signals["numbers"] >= 12 or value_signals["lists"] >= 3):
        ov = PASS
        of = f"Useful-value signals detected: {value_signals['tables']} table(s), {value_signals['lists']} list(s), {value_signals['numbers']} numeric references."
    else:
        ov = REVIEW
        of = "Original value cannot be confirmed from one URL alone; compare against competing/site content. " + f"Signals: {value_signals}."
    rows.append(result("Original Value", ov, of, rules["Original Value"]))

    rows.append(result("Factual Accuracy", REVIEW, "Requires source/data verification; the static URL scan does not treat unverified claims as automatically correct.", rules["Factual Accuracy"]))

    olds = old_years(body_text)
    if olds and looks_time_sensitive(body_text):
        od = REVIEW
        odf = f"Time-sensitive language detected alongside older year references: {olds[-6:]}. Verify that these are contextual, not stale."
    else:
        od = PASS
        odf = "No obvious stale-year signal found by the lightweight rule."
    rows.append(result("Outdated Information", od, odf, rules["Outdated Information"]))

    gram, density, count = top_ngram_density(body_text, 2)
    if count >= 20 and density >= .035:
        ku = FAIL
    elif count >= 12 and density >= .022:
        ku = REVIEW
    else:
        ku = PASS
    rows.append(result("Keyword Use", ku, f"Top repeated phrase: “{gram}” — {count} uses ({density:.1%}).", rules["Keyword Use"]))

    sent_ratio, repeated_sents = repeated_sentence_ratio(body_text)
    para_ratio, repeated_paras = repeated_paragraph_ratio(soup)
    rep = max(sent_ratio, para_ratio)
    if rep >= .10:
        rp = FAIL
    elif rep >= .04:
        rp = REVIEW
    else:
        rp = PASS
    rows.append(result("Repetition", rp, f"Estimated duplicate sentence/paragraph ratio: {rep:.1%}.", rules["Repetition"]))

    paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all("p") if len(p.get_text(" ", strip=True)) >= 60]
    if paragraphs:
        topic = title or h1
        low_specific = sum(1 for p in paragraphs if keyword_overlap(topic, p) < .05)
        filler_share = low_specific / len(paragraphs)
    else:
        filler_share = 1
    filler_status = REVIEW if filler_share > .55 else PASS
    rows.append(result("Generic / Filler Content", filler_status, f"{filler_share:.0%} of substantial paragraphs have very weak lexical overlap with the title topic. Use this as a review signal, not proof.", rules["Generic / Filler Content"]))

    tc = keyword_overlap(title, body_text)
    rows.append(result("Title vs Content", PASS if tc >= .55 else REVIEW if tc >= .3 else FAIL, f"Title-to-body topic overlap: {tc:.0%}.", rules["Title vs Content"]))

    hc = keyword_overlap(h1, body_text) if h1 else 0
    rows.append(result("H1 vs Content", PASS if h1 and hc >= .55 else REVIEW if h1 else FAIL, f"H1-to-body topic overlap: {hc:.0%}." if h1 else "H1 missing.", rules["H1 vs Content"]))

    if headings:
        relevant = sum(1 for h in headings if keyword_overlap(title or h1, h) >= .10)
        hr = relevant / len(headings)
        hstatus = PASS if hr >= .55 else REVIEW
        hfind = f"{relevant}/{len(headings)} H2-H4 headings show direct lexical relation to the main topic."
    else:
        hstatus = REVIEW
        hfind = "No H2-H4 headings available for relevance assessment."
    rows.append(result("Heading Relevance", hstatus, hfind, rules["Heading Relevance"]))

    intro_words = " ".join(tokenize(body_text)[:140])
    intro_overlap = keyword_overlap(title or h1, intro_words)
    iq = PASS if intro_overlap >= .45 else REVIEW
    rows.append(result("Introduction Quality", iq, f"Opening 140-word topic overlap: {intro_overlap:.0%}.", rules["Introduction Quality"]))

    faq_headers = [h for h in headings if "faq" in h.lower() or "frequently asked" in h.lower() or "أسئلة" in h]
    questions = [x.get_text(" ", strip=True) for x in soup.find_all(["h2","h3","h4","strong"]) if x.get_text(" ", strip=True).endswith(("?","؟"))]
    if faq_headers or questions:
        fq = REVIEW if len(questions) and sum(len(tokenize(q)) < 3 for q in questions) > len(questions)/2 else PASS
        ff = f"FAQ-like content detected: {len(questions)} question heading(s)."
    else:
        fq = PASS
        ff = "No FAQ section detected; no FAQ quality issue to evaluate."
    rows.append(result("FAQ Quality", fq, ff, rules["FAQ Quality"]))

    super_terms = ["best", "cheapest", "most popular", "number one", "#1", "highest", "lowest", "أفضل", "الأرخص", "الأكثر شعبية"]
    hits = [x for x in super_terms if x.lower() in body_text.lower()]
    outbound_citations = len([a for a in soup.find_all("a", href=True) if urlparse(urljoin(url,a["href"])).netloc not in {"", urlparse(url).netloc}])
    ss = REVIEW if hits and outbound_citations == 0 else PASS
    rows.append(result("Unsupported Superlatives", ss, f"Superlative indicators: {hits if hits else 'none'}; external source links: {outbound_citations}.", rules["Unsupported Superlatives"]))

    numeric_claims = len(re.findall(r"(?:AED\s*)?\b\d+(?:[.,]\d+)?(?:\s*[KMB])?\b|\b\d+(?:\.\d+)?%", body_text, flags=re.I))
    if numeric_claims >= 10 and outbound_citations == 0:
        sq = REVIEW
        sf = f"{numeric_claims} numeric/data-like claims and no external source links detected. Verify whether internal Bayut data is properly attributed."
    else:
        sq = PASS
        sf = f"{numeric_claims} numeric/data-like claims; {outbound_citations} external source links."
    rows.append(result("Source Quality", sq, sf, rules["Source Quality"]))

    # Detect conflicting identical labels followed by multiple different numeric values.
    # Conservative: only REVIEW when repeated percentage labels show many different values.
    percents = re.findall(r"\b\d+(?:\.\d+)?%", body_text)
    data_status = REVIEW if len(set(percents)) >= 12 else PASS
    rows.append(result("Data Accuracy", data_status, f"{len(percents)} percentage references ({len(set(percents))} unique). External/source-level validation may still be required.", rules["Data Accuracy"]))

    rows.append(result("Entity Accuracy", REVIEW, "Entity names require external/source verification; URL-only static parsing cannot confirm every project, school, developer or place name.", rules["Entity Accuracy"]))

    sentences = [s for s in re.split(r"[.!?؟]+", body_text) if len(tokenize(s)) >= 4]
    avg_len = sum(len(tokenize(s)) for s in sentences) / max(1, len(sentences))
    gr = REVIEW if avg_len > 35 else PASS
    rows.append(result("Grammar / Readability", gr, f"Average sentence length: {avg_len:.1f} words. This is a readability heuristic, not a grammar proof.", rules["Grammar / Readability"]))

    placeholders = [x for x in ["lorem ipsum", "todo", "tbd", "[insert", "placeholder", "coming soon"] if x in body_text.lower()]
    empty_heads = sum(1 for h in soup.find_all(re.compile(r"^h[1-6]$")) if not h.get_text(" ", strip=True))
    if placeholders:
        bc = FAIL
    elif empty_heads >= 2 or para_ratio >= .10:
        bc = REVIEW
    else:
        bc = PASS
    rows.append(result("Broken Content", bc, f"Placeholder indicators: {placeholders if placeholders else 'none'}; empty headings: {empty_heads}.", rules["Broken Content"]))

    return rows

# -----------------------------
# UI
# -----------------------------

st.markdown(
    """
    <div class="bayut-header">
      <div>
        <div class="brand">bayut URL Quality Auditor</div>
        <div class="subtitle">Single-URL checks for Spam, SEO and Content quality</div>
      </div>
      <div class="pill">URL-by-URL audit</div>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown("### Audit structure")
    st.markdown("**Spam Check**  \nGoogle spam-risk patterns")
    st.markdown("**SEO Check**  \nCrawling, indexing and on-page signals")
    st.markdown("**Content Check**  \nUsefulness, relevance, accuracy and quality")
    st.divider()
    st.caption("Rule thresholds in this app are internal auditing heuristics unless the rule explicitly describes a Google spam-policy condition.")
    show_rules = st.checkbox("Show rule library", value=False)

url_input = st.text_input(
    "Article URL",
    placeholder="https://www.bayut.com/mybayut/example-article/",
)

run = st.button("Run URL Audit", type="primary")

if show_rules:
    st.markdown('<div class="section-title">Rule Library</div>', unsafe_allow_html=True)
    for label, rules in [("Spam", SPAM_RULES), ("SEO", SEO_RULES), ("Content", CONTENT_RULES)]:
        with st.expander(f"{label} rules ({len(rules)})"):
            for i, (name, rule) in enumerate(rules, 1):
                st.markdown(f"**{i}. {name}**  \n{rule}")

if run:
    url = normalize_url(url_input)
    if not url:
        st.error("Enter a URL first.")
        st.stop()

    try:
        with st.spinner("Fetching the URL as desktop, mobile and crawler..."):
            desktop_r, desktop_elapsed = fetch(url, UA_DESKTOP)
            mobile_r, _ = fetch(url, UA_MOBILE)
            bot_r, _ = fetch(url, UA_GOOGLEBOT)
            soup = soup_of(desktop_r.text)
            body_text = main_content_text(soup)

        spam_rows = audit_spam(url, desktop_r, mobile_r, bot_r, soup, body_text)
        seo_rows = audit_seo(url, desktop_r, desktop_elapsed, mobile_r, soup, body_text)
        content_rows = audit_content(url, soup, body_text)

        spam_status, spam_counts = classify_counts(spam_rows)
        seo_status, seo_counts = classify_counts(seo_rows)
        content_status, content_counts = classify_counts(content_rows)

        all_statuses = [spam_status, seo_status, content_status]
        overall = FAIL if FAIL in all_statuses else REVIEW if REVIEW in all_statuses else PASS

        cols = st.columns(4)
        cards = [
            ("Overall", overall, f"Final URL: {desktop_r.url}"),
            ("Spam", spam_status, f"{spam_counts[FAIL]} fail · {spam_counts[REVIEW]} review"),
            ("SEO", seo_status, f"{seo_counts[FAIL]} fail · {seo_counts[REVIEW]} review"),
            ("Content", content_status, f"{content_counts[FAIL]} fail · {content_counts[REVIEW]} review"),
        ]
        for col, (label, value, note) in zip(cols, cards):
            with col:
                st.markdown(
                    f"""
                    <div class="metric-card">
                      <div class="metric-label">{label}</div>
                      <div class="metric-value {status_class(value)}">{value}</div>
                      <div class="metric-note">{html_lib.escape(note)}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        st.caption(
            f"HTTP {desktop_r.status_code} · {word_count(body_text):,} extracted words · "
            f"{desktop_elapsed:.2f}s server response · {len(desktop_r.history)} redirect(s)"
        )

        tabs = st.tabs([
            f"Spam Check ({len(spam_rows)})",
            f"SEO Check ({len(seo_rows)})",
            f"Content Check ({len(content_rows)})",
        ])

        for tab, rows in zip(tabs, [spam_rows, seo_rows, content_rows]):
            with tab:
                df = pd.DataFrame(rows)
                status_order = pd.Categorical(df["Status"], categories=[FAIL, REVIEW, PASS], ordered=True)
                df = df.assign(_sort=status_order).sort_values("_sort").drop(columns="_sort")
                st.dataframe(
                    df,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Check": st.column_config.TextColumn(width="medium"),
                        "Status": st.column_config.TextColumn(width="small"),
                        "Finding": st.column_config.TextColumn(width="large"),
                        "Rule": st.column_config.TextColumn(width="large"),
                    },
                )

        export = {
            "url_requested": url,
            "url_final": desktop_r.url,
            "overall": overall,
            "spam": spam_rows,
            "seo": seo_rows,
            "content": content_rows,
        }
        st.download_button(
            "Download audit JSON",
            data=json.dumps(export, ensure_ascii=False, indent=2),
            file_name="url_audit.json",
            mime="application/json",
        )

        with st.expander("Important interpretation notes"):
            st.markdown(
                """
                - A **FAIL** means the rule engine found a strong condition that should be investigated immediately.
                - A **REVIEW** is not a Google penalty or proof of spam. It means the URL needs human or external-source verification.
                - The Googlebot check uses a Googlebot **User-Agent comparison**. It does not reproduce Google's full rendering/indexing infrastructure.
                - External plagiarism/scraping, factual accuracy, entity accuracy and site-reputation abuse cannot be conclusively proven from one static URL alone.
                - Content word-count and repetition thresholds are internal QA heuristics, not Google thresholds.
                """
            )

    except requests.exceptions.RequestException as e:
        st.error(f"Could not fetch the URL: {e}")
    except Exception as e:
        st.exception(e)

else:
    st.markdown("### What this version checks")
    a, b, c = st.columns(3)
    with a:
        st.markdown("**Spam — 16 rules**")
        st.caption("Cloaking, redirects, hidden content, stuffing, links, hacked content, scripts, UGC, malware and related spam risks.")
    with b:
        st.markdown("**SEO — 20 rules**")
        st.caption("Status, indexability, canonical, titles, headings, links, images, schema, dates, sitemap, mobile, HTTPS and more.")
    with c:
        st.markdown("**Content — 20 rules**")
        st.caption("Intent, relevance, thinness, originality, freshness, repetition, FAQs, sourcing, accuracy and readability.")
