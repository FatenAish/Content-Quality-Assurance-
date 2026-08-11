
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
# Single URL audit for Spam, SEO and Content
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
    initial_sidebar_state="expanded",
)

st.markdown(
    f"""
    <style>
    :root {{
        --bayut-green: #00A66A;
        --bayut-green-dark: #008B59;
        --bayut-mint: #F2FBF7;
        --bayut-mint-2: #EAF7F1;
        --ink: #121926;
        --muted: #667085;
        --line: #E4E9E7;
        --panel: #FFFFFF;
        --soft: #F8FAF9;
        --warn: #B7791F;
        --danger: #C53030;
    }}

    html, body, [class*="css"] {{
        font-family: Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    .stApp {{
        background: #ffffff;
        color: var(--ink);
    }}
    header[data-testid="stHeader"] {{
        display:none;
    }}
    #MainMenu, footer {{
        visibility:hidden;
    }}
    .block-container {{
        max-width: 1460px;
        padding: 22px 30px 42px 30px;
    }}

    /* Sidebar */
    section[data-testid="stSidebar"] {{
        width: 286px !important;
        min-width: 286px !important;
        max-width: 286px !important;
        background: #ffffff;
        border-right: 1px solid #E8ECEA;
    }}
    section[data-testid="stSidebar"] > div {{
        width: 286px !important;
        padding-top: 0 !important;
    }}
    section[data-testid="stSidebar"] [data-testid="stSidebarContent"] {{
        padding: 24px 18px 22px 18px;
    }}
    .side-brand {{
        display:flex;
        align-items:center;
        gap:9px;
        padding: 2px 3px 30px 3px;
        color:var(--bayut-green);
        font-size:28px;
        font-weight:800;
        letter-spacing:-1px;
    }}
    .side-brand svg {{width:31px;height:31px;}}
    .side-title {{
        font-size:12px;
        line-height:1;
        color:#667085;
        font-weight:800;
        letter-spacing:.7px;
        text-transform:uppercase;
        padding: 5px 6px 14px 6px;
    }}
    .nav-card {{
        display:flex;
        align-items:center;
        gap:13px;
        padding:14px 12px;
        border-radius:12px;
        margin-bottom:9px;
        border-left:4px solid transparent;
    }}
    .nav-card.active {{
        background:linear-gradient(90deg, #F0FAF5 0%, #F6FBF8 100%);
        border-left-color:var(--bayut-green);
    }}
    .nav-icon {{
        width:43px;
        height:43px;
        border-radius:50%;
        border:1px solid #E6EEE9;
        background:#fff;
        display:flex;
        align-items:center;
        justify-content:center;
        flex:0 0 43px;
    }}
    .nav-icon svg {{width:23px;height:23px;stroke:var(--bayut-green);}}
    .nav-name {{font-size:14px;font-weight:800;color:#172026;margin-bottom:4px;}}
    .nav-desc {{font-size:11px;line-height:1.55;color:#667085;}}
    .side-divider {{height:1px;background:#ECEFED;margin:22px 4px;}}
    .side-note {{
        padding:13px 12px;
        border:1px solid #E5EAE7;
        border-radius:10px;
        background:#FAFBFA;
        color:#69736F;
        font-size:10.5px;
        line-height:1.55;
    }}
    .side-note strong {{color:var(--bayut-green);}}
    section[data-testid="stSidebar"] .stCheckbox {{
        margin-top:28px;
        padding: 8px 4px 0 4px;
    }}
    section[data-testid="stSidebar"] .stCheckbox label p {{
        font-size:12px;
        font-weight:700;
        color:#29312F;
    }}

    /* Utility row */
    .utility-row {{
        display:flex;
        justify-content:flex-end;
        gap:10px;
        margin: 0 2px 12px 0;
    }}
    .utility-btn {{
        display:inline-flex;
        align-items:center;
        justify-content:center;
        gap:7px;
        min-width:38px;
        height:38px;
        padding:0 12px;
        border:1px solid #E6EAE8;
        border-radius:999px;
        background:#fff;
        color:#111827;
        font-size:12px;
        box-shadow:0 2px 8px rgba(16,24,40,.03);
    }}
    .utility-btn.icon-only {{padding:0;width:38px;}}
    .utility-btn svg {{width:17px;height:17px;stroke:#202723;}}

    /* Hero */
    .hero-card {{
        position:relative;
        overflow:hidden;
        display:flex;
        align-items:center;
        justify-content:space-between;
        min-height:142px;
        padding:25px 30px;
        border:1px solid #D7E9E0;
        border-radius:15px;
        background:
            radial-gradient(circle at 17% 50%, rgba(0,166,106,.10), transparent 18%),
            radial-gradient(circle at 90% 22%, rgba(0,166,106,.06), transparent 24%),
            linear-gradient(115deg, #FFFFFF 0%, #F7FCF9 55%, #F0FAF5 100%);
        box-shadow:0 4px 18px rgba(16,24,40,.03);
        margin-bottom:10px;
    }}
    .hero-card:after {{
        content:"";
        position:absolute;
        right:-80px; top:18px;
        width:420px; height:160px;
        border-radius:55% 0 0 55%;
        background:linear-gradient(120deg, rgba(0,166,106,.025), rgba(0,166,106,.055));
        transform:rotate(-7deg);
        pointer-events:none;
    }}
    .hero-left {{display:flex;align-items:center;gap:22px;position:relative;z-index:2;}}
    .hero-icon {{
        width:76px;height:76px;border-radius:50%;
        background:rgba(0,166,106,.075);
        border:1px solid rgba(0,166,106,.08);
        display:flex;align-items:center;justify-content:center;
        box-shadow:0 0 0 12px rgba(0,166,106,.035);
    }}
    .hero-icon svg {{width:43px;height:43px;stroke:var(--bayut-green);stroke-width:2;}}
    .hero-title {{
        font-size:28px;line-height:1.12;font-weight:800;color:#101828;letter-spacing:-.8px;
    }}
    .hero-title .bayut-word {{color:var(--bayut-green);}}
    .hero-sub {{font-size:13px;color:#667085;margin-top:11px;}}
    .audit-pill {{
        position:relative;z-index:2;
        padding:12px 18px;
        border-radius:999px;
        background:#fff;
        border:1px solid #DDE8E2;
        color:var(--bayut-green-dark);
        font-size:12px;font-weight:800;
        box-shadow:0 6px 16px rgba(16,24,40,.08);
    }}

    /* URL input panel */
    .url-shell {{
        border:1px solid #E4E8E6;
        background:#fff;
        border-radius:14px;
        padding:16px 18px 17px;
        box-shadow:0 7px 18px rgba(16,24,40,.05);
        margin: 8px 0 22px 0;
    }}
    .url-label {{font-size:12px;font-weight:800;color:#27302D;margin-bottom:8px;}}
    .field-label {{font-size:11.5px;font-weight:800;color:#344054;margin:10px 0 6px;}}
    .field-help {{font-size:10.5px;color:#98A2B3;margin-top:4px;line-height:1.4;}}
    .keyword-context {{margin:8px 0 16px;padding:10px 12px;border:1px solid #E1ECE6;border-radius:10px;background:#F8FCFA;color:#475467;font-size:11.5px;}}
    .keyword-context strong {{color:var(--bayut-green-dark);}}
    div[data-testid="stTextInput"] {{margin-top:0;}}
    div[data-testid="stTextInput"] input {{
        height:48px;
        border:1px solid #CFE8DC !important;
        border-radius:10px !important;
        padding-left:15px !important;
        background:#fff !important;
        color:#344054 !important;
        box-shadow:none !important;
        font-size:12px !important;
    }}
    div[data-testid="stTextInput"] > div > div {{
        border:none !important;
        box-shadow:none !important;
        background:transparent !important;
    }}
    div[data-testid="stButton"] button {{
        height:48px;
        border:0 !important;
        border-radius:9px !important;
        background:linear-gradient(180deg, #00AF70 0%, #009960 100%) !important;
        color:#fff !important;
        font-size:13px !important;
        font-weight:800 !important;
        box-shadow:0 7px 14px rgba(0,166,106,.22) !important;
        transition:.16s ease;
    }}
    div[data-testid="stButton"] button:hover {{
        transform:translateY(-1px);
        background:linear-gradient(180deg, #00A86B 0%, #008B59 100%) !important;
    }}

    /* Section title */
    .section-heading {{
        font-size:20px;
        font-weight:800;
        color:#172026;
        letter-spacing:-.35px;
        margin:20px 2px 14px 2px;
    }}

    /* Feature cards */
    .feature-card {{
        position:relative;
        min-height:150px;
        padding:20px 20px 20px 20px;
        border:1px solid #E2E7E5;
        border-radius:13px;
        background:#fff;
        box-shadow:0 7px 18px rgba(16,24,40,.05);
        overflow:hidden;
    }}
    .feature-card:after {{
        content:"";
        position:absolute;bottom:0;left:0;width:58px;height:3px;background:var(--bayut-green);
        border-radius:0 3px 0 0;
    }}
    .feature-row {{display:flex;gap:15px;align-items:flex-start;}}
    .feature-icon {{
        width:48px;height:48px;border-radius:50%;flex:0 0 48px;
        display:flex;align-items:center;justify-content:center;
        border:1px solid #DDECE5;background:#F2FAF6;
    }}
    .feature-icon svg {{width:25px;height:25px;stroke:#008B59;}}
    .feature-title {{font-size:15px;font-weight:800;color:#202725;margin-top:2px;}}
    .feature-title span {{color:var(--bayut-green-dark);}}
    .feature-desc {{font-size:11px;line-height:1.55;color:#667085;margin-top:10px;}}

    /* How it works */
    .how-card {{
        border:1px solid #E2E7E5;
        border-radius:13px;
        background:#fff;
        padding:20px 22px 22px;
        box-shadow:0 7px 18px rgba(16,24,40,.045);
        margin-top:8px;
    }}
    .steps {{display:grid;grid-template-columns:1fr 32px 1fr 32px 1fr 32px 1fr;gap:8px;align-items:center;}}
    .step {{display:flex;gap:13px;align-items:flex-start;min-width:0;}}
    .step-icon {{
        width:52px;height:52px;border-radius:50%;background:#F1FAF5;border:1px solid #DCECE4;
        display:flex;align-items:center;justify-content:center;flex:0 0 52px;position:relative;
    }}
    .step-icon svg {{width:25px;height:25px;stroke:var(--bayut-green);}}
    .step-num {{
        position:absolute;bottom:-12px;left:50%;transform:translateX(-50%);
        width:19px;height:19px;border-radius:50%;background:var(--bayut-green);color:#fff;
        font-size:10px;font-weight:800;display:flex;align-items:center;justify-content:center;
        border:2px solid #fff;
    }}
    .step-title {{font-size:12px;font-weight:800;color:#202725;margin-top:3px;}}
    .step-desc {{font-size:10.5px;line-height:1.5;color:#667085;margin-top:6px;}}
    .arrow {{text-align:center;color:#C3CCC7;font-size:25px;font-weight:300;}}

    /* Results */
    .metric-card {{
        border:1px solid #E2E7E5;
        border-radius:13px;
        padding:17px 18px;
        background:#fff;
        min-height:112px;
        box-shadow:0 5px 14px rgba(16,24,40,.04);
    }}
    .metric-label {{
        color:#667085;font-size:10.5px;font-weight:800;text-transform:uppercase;letter-spacing:.55px;
    }}
    .metric-value {{font-size:23px;font-weight:850;margin-top:7px;}}
    .metric-note {{color:#667085;font-size:10px;margin-top:6px;line-height:1.4;}}
    .status-pass {{ color: var(--bayut-green); font-weight:800; }}
    .status-review {{ color: var(--warn); font-weight:800; }}
    .status-fail {{ color: var(--danger); font-weight:800; }}

    /* Tabs / dataframe / expanders */
    button[data-baseweb="tab"] {{font-weight:800 !important;font-size:12px !important;}}
    div[data-testid="stDataFrame"] {{
        border:1px solid #E4E8E6;
        border-radius:12px;
        overflow:hidden;
    }}
    div[data-testid="stExpander"] {{
        border:1px solid #E5EAE7 !important;
        border-radius:10px !important;
        background:#fff !important;
    }}
    .stDownloadButton button {{
        background:#fff !important;
        color:var(--bayut-green-dark) !important;
        border:1px solid #CFE8DC !important;
        box-shadow:none !important;
    }}

    @media (max-width: 1100px) {{
        section[data-testid="stSidebar"] {{width:240px !important;min-width:240px !important;max-width:240px !important;}}
        section[data-testid="stSidebar"] > div {{width:240px !important;}}
        .steps {{grid-template-columns:1fr;}}
        .arrow {{display:none;}}
        .hero-card {{padding:22px;}}
        .hero-title {{font-size:24px;}}
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

# -----------------------------
# Rule library
# -----------------------------

SPAM_RULES = [
    ("Cloaking", "Compare normal user and Googlebot responses. FAIL when materially different content is served specifically to search crawlers."),
    ("Sneaky Redirect", "FAIL when crawler and user are sent to materially different destinations or users are deceptively redirected."),
    ("Device Spam Redirect", "FAIL when mobile or device users are redirected to unrelated or spam destinations while other visitors are not."),
    ("Hidden Text", "FAIL when substantial SEO focused text is intentionally hidden from users. Legitimate UI and accessibility hiding is not spam."),
    ("Hidden Links", "FAIL when links are deliberately invisible, tiny, outside the visible screen or otherwise concealed for ranking manipulation."),
    ("Keyword Stuffing", "FAIL when keywords, locations or query phrases are repeated unnaturally for rankings."),
    ("Scraped Content", "FAIL when substantial external content is copied or lightly transformed with little original value. Requires external comparison."),
    ("Link Spam", "FAIL when links are clearly created or inserted primarily to manipulate rankings."),
    ("Paid Links", "FAIL when identifiable paid or sponsored links pass ranking credit without appropriate sponsored or nofollow qualification."),
    ("Hacked Content", "FAIL when unauthorized spam text, pages, links or redirects are injected."),
    ("Spam JavaScript", "FAIL when scripts inject spam content, hidden links or deceptive redirects."),
    ("Spam Iframes", "FAIL when unauthorized or suspicious iframes introduce deceptive or spam content."),
    ("Site Reputation Abuse", "FAIL when unrelated third party content primarily exploits the host site's ranking signals. Often needs manual context."),
    ("User Generated Spam", "FAIL when comments/profiles/UGC contain mass spam or manipulative links."),
    ("Back Button Hijacking", "FAIL when scripts manipulate browser history to prevent users from returning to the previous page."),
    ("Malware / Scam Behaviour", "FAIL when malicious downloads, harmful scripts, impersonation or deliberately deceptive functionality is detected."),
]

SEO_RULES = [
    ("HTTP Status", "PASS when the canonical live article returns HTTP 200."),
    ("Indexability", "FAIL when an intended indexable article contains noindex."),
    ("Robots", "FAIL when Googlebot is unintentionally blocked by page level robots directives."),
    ("Canonical", "PASS when a valid canonical points to the correct preferred URL."),
    ("Title Tag", "PASS when a relevant, non empty title exists and is not excessively long or stuffed."),
    ("Meta Description", "PASS when a useful, relevant meta description exists."),
    ("H1", "PASS when a clear relevant H1 exists."),
    ("Heading Structure", "REVIEW when headings are empty, highly repetitive, or structurally confusing."),
    ("URL Structure", "REVIEW when the URL is malformed, misleading, or dominated by unnecessary parameters."),
    ("Internal Links", "REVIEW/FAIL when important crawlable internal links are broken."),
    ("External Links", "REVIEW when external links are broken or clearly irrelevant."),
    ("Images", "REVIEW when meaningful images are broken or lack useful alt text."),
    ("Structured Data", "PASS when JSON LD is parseable and represents visible page content; REVIEW invalid/missing data where expected."),
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
    ("Thin Content", "System heuristic: PASS at 600+ meaningful words, REVIEW at 300–599, FAIL below 300. This is not a Google word count rule."),
    ("Original Value", "PASS when the page adds useful data, examples, analysis or first hand value. External/site comparison may be required."),
    ("Factual Accuracy", "FAIL confirmed false claims; REVIEW claims that require source verification."),
    ("Outdated Information", "REVIEW when time sensitive claims appear stale or reference old years without context."),
    ("Keyword Use", "PASS when important terms are used naturally; FAIL obvious unnatural repetition."),
    ("Repetition", "REVIEW/FAIL when sentences or paragraphs are unnecessarily repeated."),
    ("Generic / Filler Content", "REVIEW when a high share of text adds little topic specific information."),
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


SYSTEM_USES = {
    # Spam
    "Cloaking": "Desktop User Agent, Googlebot User Agent, final URL comparison, main content extraction, text similarity",
    "Sneaky Redirect": "Desktop User Agent, Googlebot User Agent, HTTP redirect handling, final destination comparison",
    "Device Spam Redirect": "Desktop User Agent, Mobile User Agent, final URL comparison, main content similarity",
    "Hidden Text": "HTML DOM, CSS style attributes, hidden attribute, aria hidden attribute, visible text length",
    "Hidden Links": "HTML anchor elements, hidden parent elements, CSS visibility rules, link destination extraction",
    "Keyword Stuffing": "Article text, Focus Keyword, Secondary Keywords, exact phrase count, N gram frequency, repetition density",
    "Scraped Content": "Current URL content plus external comparison requirement. The current version marks this for review when outside comparison is needed",
    "Link Spam": "External link count, anchor text, destination domain, anchor length, link pattern analysis",
    "Paid Links": "External links, surrounding text, sponsored and affiliate terms, rel sponsored attribute, rel nofollow attribute",
    "Hacked Content": "Rendered page text, suspicious spam terms, injected content pattern matching",
    "Spam JavaScript": "Inline JavaScript, redirect patterns, obfuscation patterns, location functions, encoded script indicators",
    "Spam Iframes": "Iframe elements, iframe visibility, CSS hiding rules, iframe source information",
    "Site Reputation Abuse": "Page topic and editorial context. The current version marks this for review when ownership and publishing purpose cannot be confirmed from one URL",
    "User Generated Spam": "Comment and user content containers, DOM class and ID patterns, links inside user content areas",
    "Back Button Hijacking": "JavaScript history functions, popstate, pushState, replaceState, redirect and location logic",
    "Malware / Scam Behaviour": "JavaScript source, script obfuscation patterns, script injection patterns, suspicious redirect behaviour",

    # SEO
    "HTTP Status": "HTTP request and returned response status code",
    "Indexability": "Meta robots directive, Googlebot meta directive, noindex detection",
    "Robots": "Meta robots directive, Googlebot meta directive, index and follow restrictions",
    "Canonical": "Canonical link element, canonical destination, current final URL, URL path comparison",
    "Title Tag": "HTML title element, title length, Focus Keyword presence and topic relevance",
    "Meta Description": "Meta description element, description length, Focus Keyword presence",
    "H1": "H1 elements, H1 count, H1 text, Focus Keyword presence",
    "Heading Structure": "H1 through H6 elements, empty heading count, repeated heading count, heading order",
    "URL Structure": "URL scheme, domain, path, query parameters, query length, invalid character patterns",
    "Internal Links": "Anchor elements, resolved link URLs, current domain, internal domain comparison",
    "External Links": "Anchor elements, resolved link URLs, external domain comparison",
    "Images": "Image elements, image count, alt attribute presence",
    "Structured Data": "JSON LD script elements, JSON parser, schema object extraction, parsing errors",
    "datePublished": "Parsed JSON LD, datePublished property",
    "dateModified": "Parsed JSON LD, dateModified property",
    "Sitemap": "Common sitemap locations, HTTP requests, sitemap response, audited URL lookup",
    "Mobile Content": "Desktop User Agent, Mobile User Agent, extracted main content, text similarity",
    "JavaScript Rendering": "Extracted article word count, script count, initial HTML content availability",
    "HTTPS": "Final URL scheme and HTTPS detection",
    "Broken Resources": "Script source URLs, stylesheet URLs, image source URLs, resource extraction",

    # Content
    "Search Intent": "Focus Keyword when provided, otherwise title and H1, article body, topic keyword overlap",
    "Content Relevance": "Focus Keyword or main topic, H2 through H4 headings, heading topic overlap",
    "Thin Content": "Main content extraction and meaningful article word count",
    "Original Value": "Main content word count, tables, lists, numeric references, useful information signals",
    "Factual Accuracy": "Claims found in the article plus external verification requirement. The current version marks unverified facts for review",
    "Outdated Information": "Years in the article, time sensitive terms, prices, rent, ROI, fees, laws, projects and other freshness signals",
    "Keyword Use": "Focus Keyword, Secondary Keywords, exact phrase count, N gram frequency, keyword frequency in the article",
    "Repetition": "Normalised sentences, normalised paragraphs, duplicate counts, repetition ratio",
    "Generic / Filler Content": "Substantial paragraphs, Focus Keyword or main topic, paragraph topic overlap",
    "Title vs Content": "HTML title text, main article body, topic keyword overlap",
    "H1 vs Content": "Main H1 text, main article body, topic keyword overlap",
    "Heading Relevance": "Focus Keyword or main topic, H2 through H4 headings, topic similarity",
    "Introduction Quality": "First section of the article, approximately the first 140 words, Focus Keyword or main topic, topic overlap",
    "FAQ Quality": "FAQ like headings, question marks, question text length, repeated or weak question patterns",
    "Unsupported Superlatives": "Superlative terms such as best, cheapest and most popular, external source link presence",
    "Source Quality": "Numeric claims, data like statements, external source link count, visible attribution signals",
    "Data Accuracy": "Numbers and percentages extracted from the page, repeated values, internal consistency signals",
    "Entity Accuracy": "Names and entities found in the content plus external verification requirement. The current version marks unverified entities for review",
    "Grammar / Readability": "Sentence splitting, words per sentence, average sentence length",
    "Broken Content": "Placeholder terms, unfinished content indicators, empty headings, repeated paragraphs"
}

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

def parse_keywords(raw):
    """Parse comma/semicolon/newline/pipe-separated secondary keywords and de-duplicate them."""
    if not raw:
        return []
    parts = re.split(r"[,;\n|]+", raw)
    out = []
    seen = set()
    for part in parts:
        kw = re.sub(r"\s+", " ", part).strip()
        key = kw.casefold()
        if kw and key not in seen:
            seen.add(key)
            out.append(kw)
    return out

def phrase_count(text, phrase):
    """Count exact keyword-phrase occurrences on normalized token text."""
    phrase_tokens = tokenize(phrase)
    if not phrase_tokens:
        return 0
    hay = " ".join(tokenize(text))
    needle = " ".join(phrase_tokens)
    return len(re.findall(r"(?<!\w)" + re.escape(needle) + r"(?!\w)", hay, flags=re.I))

def keyword_in_text(keyword, text, min_overlap=0.8):
    if not keyword:
        return True
    if phrase_count(text, keyword) > 0:
        return True
    return keyword_overlap(keyword, text) >= min_overlap

def keyword_summary(body_text, focus_keyword, secondary_keywords):
    kws = ([focus_keyword] if focus_keyword else []) + list(secondary_keywords or [])
    return [(kw, phrase_count(body_text, kw)) for kw in kws]

def status_class(s):
    return {"PASS":"status-pass","REVIEW":"status-review","FAIL":"status-fail"}.get(s, "")

def result(name, status, finding, rule):
    method = SYSTEM_USES.get(name, "Rule based page analysis")
    return {
        "Check": name,
        "Status": status,
        "Result": finding,
        "Why": f"The system used {method}. The fixed rule applied is: {rule}",
        "_internal_status": status,
        "_rule": rule,
        "_system_uses": method,
    }

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
    c = Counter(r.get("_internal_status", PASS) for r in rows)
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

def audit_spam(url, desktop_r, mobile_r, bot_r, soup, body_text, focus_keyword="", secondary_keywords=None):
    rows = []
    rules = dict(SPAM_RULES)
    secondary_keywords = secondary_keywords or []

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
        rows.append(result("Hidden Links", REVIEW, f"Found {len(set(hidden_links))} link(s) inside hidden elements. Review whether they are legitimate UI and accessibility elements.", rules["Hidden Links"]))
    else:
        rows.append(result("Hidden Links", PASS, "No links found inside obvious hidden elements.", rules["Hidden Links"]))

    gram, density, count = top_ngram_density(body_text, 2)
    if count >= 20 and density >= 0.035:
        kstatus = FAIL
    elif count >= 12 and density >= 0.022:
        kstatus = REVIEW
    else:
        kstatus = PASS
    target_counts = keyword_summary(body_text, focus_keyword, secondary_keywords)
    target_note = ""
    if target_counts:
        target_note = " Target keywords — " + "; ".join(f"{kw}: {n}" for kw, n in target_counts[:12]) + "."
    rows.append(result("Keyword Stuffing", kstatus, f"Most repeated 2-word phrase: “{gram}” — {count} uses ({density:.1%} of bigrams).{target_note}", rules["Keyword Stuffing"]))

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
        pf = f"{paid_bad} identifiable paid or sponsored link(s) lack sponsored or nofollow qualification."
    elif paid_candidates:
        ps = PASS
        pf = f"{paid_candidates} paid or sponsored candidate link(s) found and qualified."
    else:
        ps = PASS
        pf = "No clearly identifiable paid or sponsored links detected from visible context."
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

    rows.append(result("Site Reputation Abuse", REVIEW, "URL only analysis can flag unrelated third party content, but confirming reputation abuse requires editorial/ownership context.", rules["Site Reputation Abuse"]))

    comment_nodes = soup.select(".comment, .comments, [id*='comment'], [class*='comment']")
    ugc_links = 0
    for n in comment_nodes:
        ugc_links += len(n.find_all("a", href=True))
    ugc_status = REVIEW if ugc_links >= 10 else PASS
    rows.append(result("User Generated Spam", ugc_status, f"Detected {ugc_links} links in comment/UGC-like containers.", rules["User Generated Spam"]))

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

def audit_seo(url, desktop_r, desktop_elapsed, mobile_r, soup, body_text, focus_keyword="", secondary_keywords=None):
    rows = []
    rules = dict(SEO_RULES)
    secondary_keywords = secondary_keywords or []

    code = desktop_r.status_code
    rows.append(result("HTTP Status", PASS if code == 200 else FAIL, f"HTTP {code}.", rules["HTTP Status"]))

    robots = robots_directives(soup)
    if "noindex" in robots:
        rows.append(result("Indexability", FAIL, f"Page-level robots directive contains noindex: {robots}", rules["Indexability"]))
    else:
        rows.append(result("Indexability", PASS, f"No page level noindex detected{': ' + robots if robots else ''}.", rules["Indexability"]))

    if "none" in robots or "noindex" in robots or "nofollow" in robots:
        rs = REVIEW if "noindex" not in robots else FAIL
    else:
        rs = PASS
    rows.append(result("Robots", rs, robots or "No restrictive page level robots meta detected.", rules["Robots"]))

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
    focus_in_title = keyword_in_text(focus_keyword, title) if focus_keyword else True
    if focus_keyword and not focus_in_title and ts == PASS:
        ts = REVIEW
    title_kw_note = f" | Focus keyword {'found' if focus_in_title else 'not found'}: {focus_keyword}" if focus_keyword else ""
    rows.append(result("Title Tag", ts, f"{title_len} characters — {title or 'missing'}{title_kw_note}", rules["Title Tag"]))

    meta = meta_content(soup, name="description")
    ml = len(meta)
    if not meta:
        md = REVIEW
    elif ml < 70 or ml > 180:
        md = REVIEW
    else:
        md = PASS
    focus_in_meta = keyword_in_text(focus_keyword, meta) if focus_keyword else True
    if focus_keyword and not focus_in_meta and md == PASS:
        md = REVIEW
    meta_kw_note = f" | Focus keyword {'found' if focus_in_meta else 'not found'}" if focus_keyword else ""
    rows.append(result("Meta Description", md, f"{ml} characters{': ' + meta[:180] if meta else ' — missing'}{meta_kw_note}", rules["Meta Description"]))

    h1s = [h.get_text(" ", strip=True) for h in soup.find_all("h1") if h.get_text(" ", strip=True)]
    if len(h1s) == 1:
        h1_status = PASS
    elif len(h1s) == 0:
        h1_status = FAIL
    else:
        h1_status = REVIEW
    focus_in_h1 = keyword_in_text(focus_keyword, h1s[0]) if focus_keyword and h1s else (not focus_keyword)
    if focus_keyword and h1s and not focus_in_h1 and h1_status == PASS:
        h1_status = REVIEW
    h1_kw_note = f" | Focus keyword {'found' if focus_in_h1 else 'not found'}" if focus_keyword else ""
    rows.append(result("H1", h1_status, f"{len(h1s)} H1(s) found" + (f": {h1s[0]}" if h1s else "") + h1_kw_note, rules["H1"]))

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
    rows.append(result("Structured Data", sd, f"{len(jsonld)} valid JSON LD block(s); {json_errors} parse error(s).", rules["Structured Data"]))

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

def audit_content(url, soup, body_text, focus_keyword="", secondary_keywords=None):
    rows = []
    rules = dict(CONTENT_RULES)
    secondary_keywords = secondary_keywords or []
    title = title_text(soup)
    h1 = first_h1(soup)
    wc = word_count(body_text)
    target_topic = focus_keyword or title or h1

    intent_overlap = keyword_overlap(target_topic, body_text)
    if intent_overlap >= .65:
        s = PASS
    elif intent_overlap >= .35:
        s = REVIEW
    else:
        s = FAIL
    intent_label = f"focus keyword ‘{focus_keyword}’" if focus_keyword else "title topic"
    rows.append(result("Search Intent", s, f"{intent_overlap:.0%} of meaningful {intent_label} terms are represented in the page text.", rules["Search Intent"]))

    headings = [h.get_text(" ", strip=True) for h in soup.find_all(re.compile(r"^h[2-4]$")) if h.get_text(" ", strip=True)]
    weak = [h for h in headings if keyword_overlap(target_topic, h) < .10 and len(tokenize(h)) >= 3]
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
    kw_notes = []
    if focus_keyword:
        fc = phrase_count(body_text, focus_keyword)
        per_1000 = (fc * 1000 / max(1, wc))
        kw_notes.append(f"Focus ‘{focus_keyword}’: {fc} exact use(s), {per_1000:.1f}/1,000 words")
        if fc == 0 and ku == PASS:
            ku = REVIEW
        # Internal heuristic only; multi-word exact repetition is more meaningful than one-word frequency.
        if len(tokenize(focus_keyword)) >= 2:
            if per_1000 >= 40:
                ku = FAIL
            elif per_1000 >= 25 and ku == PASS:
                ku = REVIEW
    if secondary_keywords:
        sec_counts = [(kw, phrase_count(body_text, kw)) for kw in secondary_keywords]
        kw_notes.append("Secondary — " + "; ".join(f"{kw}: {n}" for kw, n in sec_counts[:12]))
    extra_kw = " | " + " | ".join(kw_notes) if kw_notes else ""
    rows.append(result("Keyword Use", ku, f"Top repeated phrase: “{gram}” — {count} uses ({density:.1%}).{extra_kw}", rules["Keyword Use"]))

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
        topic = target_topic
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
        relevant = sum(1 for h in headings if keyword_overlap(target_topic, h) >= .10)
        hr = relevant / len(headings)
        hstatus = PASS if hr >= .55 else REVIEW
        hfind = f"{relevant}/{len(headings)} H2-H4 headings show direct lexical relation to the main topic."
    else:
        hstatus = REVIEW
        hfind = "No H2-H4 headings available for relevance assessment."
    rows.append(result("Heading Relevance", hstatus, hfind, rules["Heading Relevance"]))

    intro_words = " ".join(tokenize(body_text)[:140])
    intro_overlap = keyword_overlap(target_topic, intro_words)
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

    rows.append(result("Entity Accuracy", REVIEW, "Entity names require external/source verification; URL only static parsing cannot confirm every project, school, developer or place name.", rules["Entity Accuracy"]))

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

ICON_SEARCH_CHECK = """
<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
  <circle cx="10.8" cy="10.8" r="6.7" stroke="currentColor" stroke-width="1.8"/>
  <path d="M15.6 15.6L20.1 20.1" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
  <path d="M7.8 10.7L10 12.8L14.2 8.7" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
"""
ICON_SHIELD = """
<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
  <path d="M12 3L19 5.8V11.2C19 15.5 16.1 19.1 12 21C7.9 19.1 5 15.5 5 11.2V5.8L12 3Z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>
  <path d="M9 11.8L11.1 13.9L15.3 9.7" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
"""
ICON_SEARCH = """
<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
  <circle cx="10.8" cy="10.8" r="6.4" stroke="currentColor" stroke-width="1.8"/>
  <path d="M15.6 15.6L20.1 20.1" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
</svg>
"""
ICON_DOC = """
<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
  <path d="M6 3.8H14L18 7.8V20.2H6V3.8Z" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/>
  <path d="M14 3.8V8H18" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/>
  <path d="M9 12H15M9 15.5H15" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>
</svg>
"""
ICON_LINK = """
<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
  <path d="M9.6 14.4L14.4 9.6" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/>
  <path d="M7.7 16.3L6.2 17.8C4.5 19.5 1.8 19.5.2 17.8C-1.5 16.2-1.5 13.5.2 11.8L3.4 8.6C5.1 6.9 7.8 6.9 9.5 8.6" transform="translate(4 0)" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/>
  <path d="M16.3 7.7L17.8 6.2C19.5 4.5 22.2 4.5 23.8 6.2C25.5 7.8 25.5 10.5 23.8 12.2L20.6 15.4C18.9 17.1 16.2 17.1 14.5 15.4" transform="translate(-4 0)" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/>
</svg>
"""
ICON_LIST = """
<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
  <path d="M6 7H18M6 12H15M6 17H13" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
  <circle cx="17.2" cy="16.6" r="2.3" stroke="currentColor" stroke-width="1.6"/>
  <path d="M18.9 18.3L20.4 19.8" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>
</svg>
"""
ICON_CHART = """
<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
  <path d="M5 19V12M10 19V8M15 19V14M20 19V5" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
</svg>
"""
ICON_BADGE = """
<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
  <path d="M12 3L14.2 5.1L17.2 4.8L18.2 7.7L21 9L19.9 11.9L21 14.8L18.2 16.1L17.2 19L14.2 18.7L12 21L9.8 18.7L6.8 19L5.8 16.1L3 14.8L4.1 11.9L3 9L5.8 7.7L6.8 4.8L9.8 5.1L12 3Z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>
  <path d="M8.8 12L11 14.2L15.5 9.7" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
"""
ICON_HOME = """
<svg viewBox="0 0 28 28" fill="none" xmlns="http://www.w3.org/2000/svg">
  <circle cx="14" cy="14" r="11.5" stroke="currentColor" stroke-width="2.2"/>
  <path d="M8.5 13.2L14 8.6L19.5 13.2V19H9V13.2" stroke="currentColor" stroke-width="2.1" stroke-linejoin="round"/>
  <path d="M12 19V15H16V19" stroke="currentColor" stroke-width="2.1" stroke-linejoin="round"/>
</svg>
"""

with st.sidebar:
    st.markdown(
        f"""
        <div class="side-brand">{ICON_HOME}<span>bayut</span></div>
        <div class="side-title">Audit Structure</div>
        <div class="nav-card active">
          <div class="nav-icon">{ICON_SHIELD}</div>
          <div><div class="nav-name">Spam Check</div><div class="nav-desc">Google spam risk patterns</div></div>
        </div>
        <div class="nav-card">
          <div class="nav-icon">{ICON_SEARCH}</div>
          <div><div class="nav-name">SEO Check</div><div class="nav-desc">Crawling, indexing and<br>on page signals</div></div>
        </div>
        <div class="nav-card">
          <div class="nav-icon">{ICON_DOC}</div>
          <div><div class="nav-name">Content Check</div><div class="nav-desc">Usefulness, relevance,<br>accuracy and quality</div></div>
        </div>
        <div class="side-divider"></div>
        <div class="side-note"><strong>ⓘ</strong>&nbsp;&nbsp;Rule thresholds in this app are internal auditing heuristics unless the rule explicitly describes a Google spam-policy condition.</div>
        """,
        unsafe_allow_html=True,
    )
    show_rules = st.checkbox("Show rule library", value=False)

st.markdown(
    """
    <div class="utility-row">
      <div class="utility-btn">
        <svg viewBox="0 0 24 24" fill="none"><path d="M12 16V4M8 8L12 4L16 8" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/><path d="M5 13V19H19V13" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>
        Share
      </div>
      <div class="utility-btn icon-only"><svg viewBox="0 0 24 24" fill="none"><path d="M12 3.8L14.4 8.7L19.8 9.5L15.9 13.3L16.8 18.7L12 16.2L7.2 18.7L8.1 13.3L4.2 9.5L9.6 8.7L12 3.8Z" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/></svg></div>
      <div class="utility-btn icon-only"><svg viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="8" stroke="currentColor" stroke-width="1.6"/><path d="M8.3 15.3C9 16.1 9.7 16.3 10.6 16.4V14.9C9.2 14.5 8.7 13.4 8.7 12.2C8.7 11.4 9 10.6 9.7 10C9.5 9.4 9.6 8.8 9.8 8.3C10.4 8.3 11 8.6 11.4 8.9C11.8 8.8 12.2 8.8 12.6 8.9C13 8.6 13.6 8.3 14.2 8.3C14.4 8.8 14.5 9.4 14.3 10C15 10.6 15.3 11.4 15.3 12.2C15.3 13.4 14.8 14.5 13.4 14.9V16.4C14.3 16.3 15 16.1 15.7 15.3" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg></div>
      <div class="utility-btn icon-only"><svg viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="5.5" r="1.5"/><circle cx="12" cy="12" r="1.5"/><circle cx="12" cy="18.5" r="1.5"/></svg></div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    f"""
    <div class="hero-card">
      <div class="hero-left">
        <div class="hero-icon">{ICON_SEARCH_CHECK}</div>
        <div>
          <div class="hero-title"><span class="bayut-word">bayut</span> URL Quality Auditor</div>
          <div class="hero-sub">Single URL checks for Spam, SEO and Content quality</div>
        </div>
      </div>
      <div class="audit-pill">URL by URL audit</div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown('<div class="url-shell"><div class="url-label">Article URL</div>', unsafe_allow_html=True)
url_col, btn_col = st.columns([5.25, 1.35], gap="medium")
with url_col:
    url_input = st.text_input(
        "Article URL",
        placeholder="https://www.bayut.com/area-guides/damac-hills-akoya-damac/",
        label_visibility="collapsed",
        key="article_url",
    )
with btn_col:
    run = st.button("▶  Run URL Audit", type="primary", use_container_width=True)

kw_col, secondary_col = st.columns([1, 1], gap="medium")
with kw_col:
    st.markdown('<div class="field-label">Focus Keyword</div>', unsafe_allow_html=True)
    focus_keyword_input = st.text_input(
        "Focus Keyword",
        placeholder="e.g. DAMAC Hills",
        label_visibility="collapsed",
        key="focus_keyword",
    )
    st.markdown('<div class="field-help">Primary keyword the page should target.</div>', unsafe_allow_html=True)
with secondary_col:
    st.markdown('<div class="field-label">Secondary Keywords</div>', unsafe_allow_html=True)
    secondary_keywords_input = st.text_input(
        "Secondary Keywords",
        placeholder="e.g. DAMAC Hills villas, living in DAMAC Hills, Akoya by DAMAC",
        label_visibility="collapsed",
        key="secondary_keywords",
    )
    st.markdown('<div class="field-help">Separate multiple keywords with commas.</div>', unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)

if show_rules:
    st.markdown('<div class="section-heading">Rule Library</div>', unsafe_allow_html=True)
    for label, rules in [("Spam", SPAM_RULES), ("SEO", SEO_RULES), ("Content", CONTENT_RULES)]:
        with st.expander(f"{label} rules ({len(rules)})"):
            for i, (name, rule) in enumerate(rules, 1):
                method = SYSTEM_USES.get(name, "Rule based page analysis")
                st.markdown(f"**{i}. {name}**  \n**What the System Uses:** {method}  \n**Rule:** {rule}")

if run:
    url = normalize_url(url_input)
    focus_keyword = re.sub(r"\s+", " ", (focus_keyword_input or "")).strip()
    secondary_keywords = parse_keywords(secondary_keywords_input)
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

        spam_rows = audit_spam(url, desktop_r, mobile_r, bot_r, soup, body_text, focus_keyword, secondary_keywords)
        seo_rows = audit_seo(url, desktop_r, desktop_elapsed, mobile_r, soup, body_text, focus_keyword, secondary_keywords)
        content_rows = audit_content(url, soup, body_text, focus_keyword, secondary_keywords)

        # Internal rule outcomes are retained only for engine logic.
        # They are never shown to the user.
        spam_status, spam_counts = classify_counts(spam_rows)
        seo_status, seo_counts = classify_counts(seo_rows)
        content_status, content_counts = classify_counts(content_rows)

        st.markdown(
            """
            <div style="margin-top:18px;margin-bottom:8px;">
              <div style="font-size:22px;font-weight:800;">Audit Results</div>
              <div style="font-size:13px;color:#66736F;margin-top:4px;">
                Each rule shows its status, the result found and why the system reached that result.
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        info_cols = st.columns(3)
        with info_cols[0]:
            st.markdown(
                f"""
                <div class="metric-card">
                  <div class="metric-label">Spam Check</div>
                  <div class="metric-value {status_class(spam_status)}">{spam_status}</div>
                  <div class="metric-note">{spam_counts[PASS]} PASS · {spam_counts[REVIEW]} REVIEW · {spam_counts[FAIL]} FAIL</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with info_cols[1]:
            st.markdown(
                f"""
                <div class="metric-card">
                  <div class="metric-label">SEO Check</div>
                  <div class="metric-value {status_class(seo_status)}">{seo_status}</div>
                  <div class="metric-note">{seo_counts[PASS]} PASS · {seo_counts[REVIEW]} REVIEW · {seo_counts[FAIL]} FAIL</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with info_cols[2]:
            st.markdown(
                f"""
                <div class="metric-card">
                  <div class="metric-label">Content Check</div>
                  <div class="metric-value {status_class(content_status)}">{content_status}</div>
                  <div class="metric-note">{content_counts[PASS]} PASS · {content_counts[REVIEW]} REVIEW · {content_counts[FAIL]} FAIL</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.caption(
            f"HTTP {desktop_r.status_code} · {word_count(body_text):,} extracted words · "
            f"{desktop_elapsed:.2f}s server response · {len(desktop_r.history)} redirects"
        )

        tabs = st.tabs([
            f"Spam Check ({len(spam_rows)})",
            f"SEO Check ({len(seo_rows)})",
            f"Content Check ({len(content_rows)})",
        ])

        for tab, rows in zip(tabs, [spam_rows, seo_rows, content_rows]):
            with tab:
                public_rows = [
                    {
                        "Check": row["Check"],
                        "Status": row["Status"],
                        "Result": row["Result"],
                        "Why": row["Why"],
                    }
                    for row in rows
                ]
                df = pd.DataFrame(public_rows)

                def status_style(value):
                    if value == "PASS":
                        return "color: #28B16D; font-weight: 800;"
                    if value == "REVIEW":
                        return "color: #B7791F; font-weight: 800;"
                    if value == "FAIL":
                        return "color: #C53030; font-weight: 800;"
                    return ""

                styled_df = df.style.map(status_style, subset=["Status"])

                st.dataframe(
                    styled_df,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Check": st.column_config.TextColumn(width="medium"),
                        "Status": st.column_config.TextColumn(width="small"),
                        "Result": st.column_config.TextColumn(width="large"),
                        "Why": st.column_config.TextColumn(width="large"),
                    },
                )

        export = {
            "url_requested": url,
            "url_final": desktop_r.url,
            "focus_keyword": focus_keyword,
            "secondary_keywords": secondary_keywords,
            "spam": [
                {"Check": r["Check"], "Status": r["Status"], "Result": r["Result"], "Why": r["Why"]}
                for r in spam_rows
            ],
            "seo": [
                {"Check": r["Check"], "Status": r["Status"], "Result": r["Result"], "Why": r["Why"]}
                for r in seo_rows
            ],
            "content": [
                {"Check": r["Check"], "Status": r["Status"], "Result": r["Result"], "Why": r["Why"]}
                for r in content_rows
            ],
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
                Every rule receives one of three statuses: PASS, REVIEW or FAIL.

                Result shows exactly what the system found.

                Why explains the data and rule used to reach that status and result.

                When a rule cannot be fully verified from one URL, it can receive REVIEW and the Result explains what additional verification is required.

                The Googlebot check uses a Googlebot User Agent comparison. It does not reproduce Google's full rendering and indexing infrastructure.

                External plagiarism, factual accuracy, entity accuracy and site reputation abuse may require external verification.

                Content word count and repetition thresholds are internal QA heuristics and are not Google thresholds.
                """
            )

    except requests.exceptions.RequestException as e:
        st.error(f"Could not fetch the URL: {e}")
    except Exception as e:
        st.exception(e)

else:
    st.markdown('<div class="section-heading">What this version checks</div>', unsafe_allow_html=True)
    a, b, c = st.columns(3, gap="medium")
    cards = [
        (a, ICON_SHIELD, '<span>Spam</span> 16 rules', 'Cloaking, redirects, hidden content, stuffing, links, hacked content, scripts, UGC, malware and related spam risks.'),
        (b, ICON_SEARCH, '<span>SEO</span> 20 rules', 'Status, indexability, canonical, titles, headings, links, images, schema, dates, sitemap, mobile, HTTPS and more.'),
        (c, ICON_DOC, '<span>Content</span> 20 rules', 'Intent, relevance, thinness, originality, freshness, repetition, FAQs, sourcing, accuracy and readability.'),
    ]
    for col, icon, title, desc in cards:
        with col:
            st.markdown(
                f"""
                <div class="feature-card">
                  <div class="feature-row">
                    <div class="feature-icon">{icon}</div>
                    <div>
                      <div class="feature-title">{title}</div>
                      <div class="feature-desc">{desc}</div>
                    </div>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown(
        f"""
        <div class="how-card">
          <div class="section-heading" style="margin:0 0 17px 0;">How it works</div>
          <div class="steps">
            <div class="step">
              <div class="step-icon">{ICON_LINK}<div class="step-num">1</div></div>
              <div><div class="step-title">Enter URL and Keywords</div><div class="step-desc">Provide the article URL, Focus Keyword and optional Secondary Keywords.</div></div>
            </div>
            <div class="arrow">···›</div>
            <div class="step">
              <div class="step-icon">{ICON_LIST}<div class="step-num">2</div></div>
              <div><div class="step-title">Run Audit</div><div class="step-desc">We check the URL against Spam, SEO and Content quality rules.</div></div>
            </div>
            <div class="arrow">···›</div>
            <div class="step">
              <div class="step-icon">{ICON_CHART}<div class="step-num">3</div></div>
              <div><div class="step-title">Review Results</div><div class="step-desc">Browse findings, issues and recommendations across all categories.</div></div>
            </div>
            <div class="arrow">···›</div>
            <div class="step">
              <div class="step-icon">{ICON_BADGE}<div class="step-num">4</div></div>
              <div><div class="step-title">Take Action</div><div class="step-desc">Fix issues, improve quality and run again to validate improvements.</div></div>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
