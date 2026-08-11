
import re
import json
import time
import html as html_lib
import gzip
import xml.etree.ElementTree as ET
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
from difflib import SequenceMatcher
from urllib.parse import urljoin, urlparse
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except Exception:
    PLAYWRIGHT_AVAILABLE = False

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

# Performance controls
PAGE_FETCH_TIMEOUT = 9
SITEMAP_REQUEST_TIMEOUT = 4
SITEMAP_MAX_FILES = 28
SITEMAP_MAX_DEPTH = 3
SITEMAP_WORKERS = 8
SITEMAP_TIME_BUDGET = 12
PLAYWRIGHT_NAV_TIMEOUT = 12000
PLAYWRIGHT_SETTLE_MS = 450

LINK_CHECK_TIMEOUT = 3
LINK_CHECK_WORKERS = 16
RESOURCE_CHECK_TIMEOUT = 3
RESOURCE_CHECK_WORKERS = 24

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
    ("Hidden Text", "Inspect why text is hidden before assigning a result. Legitimate interface, responsive and accessibility hiding should PASS. Unexplained hiding should REVIEW. Hiding intended to manipulate search rankings should FAIL."),
    ("Hidden Links", "Inspect the exact link and the reason it is hidden. Legitimate interface, responsive and accessibility hiding should PASS. Unexplained hiding should REVIEW. Deliberately concealed links intended to manipulate rankings should FAIL."),
    ("Keyword Stuffing", "Evaluate repetition in context. Repetition of the primary topic, location or named entity does not trigger REVIEW by frequency alone. PASS when target phrases are used naturally. REVIEW when repeated query phrases appear unusually frequent without a clear editorial reason. FAIL when repetition is clearly excessive and manipulative."),
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
    ("Title Tag", "Google does not define a fixed character limit. PASS when the title exists, clearly describes the page, represents the Focus Keyword or its meaning, and is not repetitive or stuffed. Length is an internal quality signal only. Titles from 30 to 70 characters are generally concise. Titles from 71 to 80 characters do not receive REVIEW from length alone. Titles above 80 characters receive REVIEW for possible verbosity. Very short titles receive REVIEW only when they are too vague or weakly related to the page."),
    ("Meta Description", "PASS when a useful, relevant meta description exists."),
    ("H1", "PASS when one clear H1 exists and it represents the Focus Keyword meaning or the page topic. Exact phrase matching is not required. REVIEW multiple H1 elements or a weak semantic relationship. FAIL when the H1 is missing or clearly unrelated."),
    ("Heading Structure", "REVIEW when headings are empty, highly repetitive, or structurally confusing."),
    ("URL Structure", "REVIEW when the URL is malformed, misleading, or dominated by unnecessary parameters."),
    ("Internal Links", "REVIEW/FAIL when important crawlable internal links are broken."),
    ("External Links", "Request every discovered external HTTP link. Treat known social platform login, anti bot and restricted automated responses as expected platform behaviour rather than broken links. PASS when no confirmed broken destination is found. REVIEW confirmed 4xx or 5xx problems outside expected platform behaviour, unreachable URLs or unresolved restricted destinations."),
    ("Images", "REVIEW when meaningful images are broken or lack useful alt text."),
    ("Structured Data", "Parse JSON LD and compare important article fields with visible page signals. PASS when JSON LD is valid and headline or article topic is consistent with the visible page. REVIEW parse errors, missing expected article data or material schema to page mismatch."),
    ("datePublished", "Compare schema datePublished with visible or page metadata publication dates when available. PASS when a valid publication date exists and no material inconsistency is detected. REVIEW missing or materially inconsistent publication dates."),
    ("dateModified", "Compare schema dateModified with visible update metadata, sitemap lastmod and HTTP Last Modified when available. PASS when signals are consistent. REVIEW missing dates or material freshness inconsistencies. HTTP Last Modified mismatch is treated as a technical inconsistency, not a spam violation."),
    ("Sitemap", "Follow sitemap indexes and child sitemaps before deciding the result. PASS when the preferred canonical URL is found in an accessible sitemap. REVIEW when sitemap files are accessible but the preferred URL is not found after child sitemap inspection, or when sitemap inspection cannot be completed."),
    ("Mobile Content", "REVIEW/FAIL when mobile receives materially less main content than desktop."),
    ("JavaScript Rendering", "REVIEW when the initial HTML contains very little article text and depends heavily on scripts."),
    ("HTTPS", "PASS when the preferred page uses HTTPS."),
    ("Broken Resources", "Request only render relevant image, stylesheet, font preload and JavaScript resources. Exclude API discovery, oEmbed, canonical, alternate and WordPress endpoint links. PASS when checked render resources resolve successfully. REVIEW confirmed broken or unreachable render resources."),
]

CONTENT_RULES = [
    ("Search Intent", "PASS when the main content directly addresses the topic promised by the title/H1."),
    ("Content Relevance", "Evaluate the isolated article by heading hierarchy and section context. FAQ sections are judged by their answers, and named project or place headings are judged by the content beneath them. REVIEW or FAIL only when substantial article sections remain unrelated after contextual analysis."),
    ("Thin Content", "System heuristic: PASS at 600+ meaningful words, REVIEW at 300–599, FAIL below 300. This is not a Google word count rule."),
    ("Original Value", "PASS when the page adds useful data, examples, analysis or first hand value. External/site comparison may be required."),
    ("Factual Accuracy", "Extract factual and numeric claims from the isolated article body and show claim examples and visible source signals. REVIEW claims that still require external or first party data verification. FAIL only when a claim is confirmed false by a connected verification source."),
    ("Outdated Information", "Inspect each old year inside the isolated article body together with its sentence context. Historical or contextual years do not trigger REVIEW by themselves. REVIEW older years only when they appear in time sensitive claims such as current prices, rent, ROI, fees, laws, routes or project status."),
    ("Keyword Use", "Evaluate Focus Keyword and Secondary Keyword use in context. Exact matching is not required for every secondary phrase. Repetition of the primary topic or named entity is allowed when editorially necessary. PASS natural use, REVIEW unusually repetitive wording, FAIL clearly manipulative repetition."),
    ("Repetition", "REVIEW/FAIL when sentences or paragraphs are unnecessarily repeated."),
    ("Generic / Filler Content", "REVIEW when a high share of text adds little topic specific information."),
    ("Title vs Content", "PASS when title terms/topic are strongly represented in the body."),
    ("H1 vs Content", "PASS when H1 accurately represents the main body."),
    ("Heading Relevance", "Respect heading hierarchy when evaluating H2 to H4 sections. FAQ headings include their child questions and answers. Project, building, place and other entity headings can PASS through related section context even without Focus Keyword wording."),
    ("Introduction Quality", "PASS when the opening quickly establishes the promised topic."),
    ("FAQ Quality", "REVIEW when FAQ answers are empty, extremely short, repetitive or unrelated."),
    ("Unsupported Superlatives", "REVIEW claims such as best, cheapest, highest, most popular when no evidence/source is apparent."),
    ("Source Quality", "REVIEW important quantitative/regulatory claims with no visible source where sourcing is reasonably expected."),
    ("Data Accuracy", "REVIEW inconsistent prices, percentages, dates or repeated figures inside the page."),
    ("Entity Accuracy", "Clean generic property wording around entity names, extract conservative named entities, and compare entity spellings for suspicious near duplicates. REVIEW remaining entities that need external verification and possible inconsistent spellings. FAIL only when a connected verification source confirms an entity is incorrect."),
    ("Grammar / Readability", "REVIEW when sentence structure is consistently difficult to read or text is obviously malformed."),
    ("Broken Content", "FAIL obvious placeholders/unfinished output; REVIEW empty headings or duplicated content blocks."),
]


SYSTEM_USES = {
    # Spam
    "Cloaking": "Desktop User Agent, Googlebot User Agent, final URL comparison, main content extraction, text similarity",
    "Sneaky Redirect": "Desktop User Agent, Googlebot User Agent, HTTP redirect handling, final destination comparison",
    "Device Spam Redirect": "Desktop User Agent, Mobile User Agent, final URL comparison, main content similarity",
    "Hidden Text": "Rendered DOM when available, computed CSS, hidden attribute, accessibility attributes, responsive visibility, interface context, text length and hiding reason classification",
    "Hidden Links": "Rendered DOM when available, computed CSS, desktop and mobile visibility, link URL, anchor text, element and parent context, interface controls, accessibility attributes and hiding reason classification",
    "Keyword Stuffing": "Article text, Focus Keyword, Secondary Keywords, exact phrase counts, repetition per 1,000 words, N gram frequency, primary topic phrase detection, title, H1 and URL context",
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
    "Title Tag": "HTML title element, character count as an advisory signal, Focus Keyword exact or semantic term overlap, title to article topic overlap, repeated title terms",
    "Meta Description": "Meta description element, description length, Focus Keyword presence",
    "H1": "Full page H1 elements including article header H1, H1 count, Focus Keyword exact match, semantic concept overlap and article topic relationship",
    "Heading Structure": "H1 through H6 elements, empty heading count, repeated heading count, heading order",
    "URL Structure": "URL scheme, domain, path, query parameters, query length, invalid character patterns",
    "Internal Links": "Anchor elements, resolved link URLs, current domain, internal domain comparison",
    "External Links": "External anchor URLs, HTTP HEAD or lightweight GET requests, response code, final destination and request errors",
    "Images": "Image elements, image count, alt attribute presence",
    "Structured Data": "JSON LD scripts, JSON parsing, schema headline and article fields, visible title and H1 semantic comparison",
    "datePublished": "Schema datePublished, article published metadata, visible time elements and date consistency comparison",
    "dateModified": "Schema dateModified, article modified metadata, visible time elements, sitemap lastmod, HTTP Last Modified and date consistency comparison",
    "Sitemap": "robots.txt sitemap declarations, common sitemap locations, sitemap XML parsing, sitemap index detection, recursive child sitemap requests, preferred URL lookup and lastmod extraction",
    "Mobile Content": "Desktop User Agent, Mobile User Agent, extracted main content, text similarity",
    "JavaScript Rendering": "Extracted article word count, script count, initial HTML content availability",
    "HTTPS": "Final URL scheme and HTTPS detection",
    "Broken Resources": "Render relevant image, stylesheet, font preload and JavaScript resource URLs, HTTP response codes, final destinations and request errors while excluding API discovery and metadata links",

    # Content
    "Search Intent": "Focus Keyword when provided, otherwise title and H1, article body, topic keyword overlap",
    "Content Relevance": "Focus Keyword or main topic, hierarchical H2 through H4 sections, FAQ parent and child content, entity heading recognition, semantic heading overlap and section context",
    "Thin Content": "Main content extraction and meaningful article word count",
    "Original Value": "Main content word count, tables, lists, numeric references, useful information signals",
    "Factual Accuracy": "Isolated article sentences, numeric and date claims, visible external source links and claim examples that require verification",
    "Outdated Information": "Old years inside isolated article sentences, sentence context, historical markers and time sensitive terms such as prices, rent, ROI, fees, laws, routes and project status",
    "Keyword Use": "Focus Keyword, Secondary Keywords, exact phrase counts, semantic topic representation, repetition per 1,000 words, N gram frequency and primary topic phrase detection",
    "Repetition": "Normalised sentences, normalised paragraphs, duplicate counts, repetition ratio",
    "Generic / Filler Content": "Substantial paragraphs, Focus Keyword or main topic, paragraph topic overlap",
    "Title vs Content": "HTML title text, main article body, topic keyword overlap",
    "H1 vs Content": "Main H1 text, main article body, topic keyword overlap",
    "Heading Relevance": "Hierarchical H2 through H4 relationships, Focus Keyword or main topic, FAQ child content, entity heading recognition, semantic concept overlap and section context",
    "Introduction Quality": "First section of the article, approximately the first 140 words, Focus Keyword or main topic, topic overlap",
    "FAQ Quality": "FAQ like headings, question marks, question text length, repeated or weak question patterns",
    "Unsupported Superlatives": "Superlative terms such as best, cheapest and most popular, external source link presence",
    "Source Quality": "Numeric claims, data like statements, external source link count, visible attribution signals",
    "Data Accuracy": "Numbers and percentages extracted from the page, repeated values, internal consistency signals",
    "Entity Accuracy": "Cleaned entity candidates from proper noun headings, anchor text and proper noun phrases, generic property prefix removal, CTA and FAQ filtering, near duplicate spelling similarity and external or first party verification requirement",
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

def fetch(url, headers, timeout=PAGE_FETCH_TIMEOUT):
    start = time.time()
    r = requests.get(
        url,
        headers=headers,
        timeout=timeout,
        allow_redirects=True,
    )
    elapsed = time.time() - start
    return r, elapsed

def fetch_page_variants(url):
    """
    Fetch desktop, mobile and Googlebot variants in parallel.
    This replaces three sequential network waits with one parallel stage.
    """
    jobs = {
        "desktop": UA_DESKTOP,
        "mobile": UA_MOBILE,
        "googlebot": UA_GOOGLEBOT,
    }
    output = {}

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(fetch, url, headers, PAGE_FETCH_TIMEOUT): label
            for label, headers in jobs.items()
        }
        for future in as_completed(futures):
            label = futures[future]
            output[label] = future.result()

    return (
        output["desktop"][0],
        output["desktop"][1],
        output["mobile"][0],
        output["mobile"][1],
        output["googlebot"][0],
        output["googlebot"][1],
    )

def soup_of(html):
    return BeautifulSoup(html or "", "html.parser")

def clean_text(soup):
    clone = BeautifulSoup(str(soup), "html.parser")
    for tag in clone(["script", "style", "noscript", "svg", "template"]):
        tag.decompose()
    text = " ".join(clone.stripped_strings)
    return re.sub(r"\s+", " ", text).strip()

ARTICLE_BODY_SELECTORS = [
    "[itemprop='articleBody']",
    ".entry-content",
    ".post-content",
    ".article-content",
    ".post-body",
    ".article-body",
    ".single-post-content",
    ".td-post-content",
    "article",
    "main",
    "[role='main']",
]

ARTICLE_REMOVE_SELECTORS = [
    "script", "style", "noscript", "svg", "template",
    "nav", "footer", "aside",
    "#comments", ".comments", ".comments-area", ".comment-area",
    "#respond", ".comment-respond", ".comment-form", ".comment-list",
    ".related-posts", ".related-articles", ".related-content",
    ".recommended-posts", ".recommended-articles", ".recommendations",
    ".popular-posts", ".popular-articles", ".most-popular",
    ".sidebar", ".widget-area", ".side-bar",
    ".newsletter", ".subscribe", ".subscription",
    ".social-share", ".share-buttons", ".sharing",
    ".author-box", ".author-bio",
    ".breadcrumb", ".breadcrumbs",
    ".post-navigation", ".pagination",
]

ARTICLE_BOILERPLATE_PATTERNS = [
    "comment", "respond", "reply",
    "related-post", "related_post", "related article", "related-article",
    "recommended", "recommendation",
    "popular-post", "popular_post", "most-popular",
    "sidebar", "widget-area", "widget_area",
    "newsletter", "subscribe", "subscription",
    "social-share", "share-button",
    "post-navigation", "breadcrumb",
]

ARTICLE_BOUNDARY_HEADINGS = {
    "leave a reply",
    "leave a comment",
    "comments",
    "related posts",
    "related articles",
    "recommended",
    "recommended articles",
    "recommended posts",
    "you may also like",
    "popular",
    "popular posts",
    "most popular",
    "recent posts",
    "subscribe",
    "اشترك",
    "اترك تعليق",
    "اترك تعليقا",
    "مقالات ذات صلة",
    "مقالات مقترحة",
    "الأكثر قراءة",
    "الاكثر قراءة",
}

def node_signature(node):
    if node is None or not getattr(node, "name", None):
        return ""
    values = [
        node.name,
        node.get("id") or "",
        " ".join(node.get("class") or []),
        node.get("role") or "",
        node.get("aria-label") or "",
    ]
    return " ".join(values).lower()

def looks_like_boilerplate_container(node):
    sig = node_signature(node)
    return any(pattern in sig for pattern in ARTICLE_BOILERPLATE_PATTERNS)

def prune_article_fragment(node):
    """
    Clone and isolate editorial article content.
    Navigation, comments, sidebars, related content, popular widgets,
    subscriptions and other page chrome are removed before content QA.
    """
    fragment = BeautifulSoup(str(node), "html.parser")

    for selector in ARTICLE_REMOVE_SELECTORS:
        for found in fragment.select(selector):
            found.decompose()

    # Remove containers whose IDs/classes strongly identify non article UI.
    for found in list(fragment.find_all(True)):
        if looks_like_boilerplate_container(found):
            found.decompose()

    # Remove a boundary heading and the siblings after it inside the same widget/container.
    for heading in list(fragment.find_all(re.compile(r"^h[2-6]$"))):
        label = re.sub(r"\s+", " ", heading.get_text(" ", strip=True)).strip().lower()
        if label in ARTICLE_BOUNDARY_HEADINGS:
            current = heading
            while current is not None:
                nxt = current.next_sibling
                try:
                    current.decompose()
                except Exception:
                    pass
                current = nxt

    return fragment

def article_candidate_score(node, selector_bonus=0):
    fragment = prune_article_fragment(node)
    text_value = clean_text(fragment)
    if len(text_value) < 200:
        return -10_000, fragment

    paragraphs = [
        p.get_text(" ", strip=True)
        for p in fragment.find_all("p")
        if len(p.get_text(" ", strip=True)) >= 40
    ]
    headings = [
        h.get_text(" ", strip=True)
        for h in fragment.find_all(re.compile(r"^h[1-4]$"))
        if h.get_text(" ", strip=True)
    ]
    links = fragment.find_all("a", href=True)

    # Prefer editorial prose and specific article body selectors.
    score = (
        selector_bonus
        + len(text_value)
        + len(paragraphs) * 180
        + len(headings) * 60
        - max(0, len(links) - len(paragraphs) * 3) * 20
    )
    return score, fragment

def article_content_node(soup):
    """
    Select the most likely editorial article body and return a pruned clone.
    Specific article body selectors are preferred over broad main containers.
    """
    selector_weights = {
        "[itemprop='articleBody']": 9000,
        ".entry-content": 8500,
        ".post-content": 8200,
        ".article-content": 8200,
        ".post-body": 8000,
        ".article-body": 8000,
        ".single-post-content": 7800,
        ".td-post-content": 7800,
        "article": 5500,
        "main": 1500,
        "[role='main']": 1500,
    }

    candidates = []
    seen = set()

    for selector in ARTICLE_BODY_SELECTORS:
        for node in soup.select(selector):
            identity = id(node)
            if identity in seen:
                continue
            seen.add(identity)

            score, fragment = article_candidate_score(
                node,
                selector_weights.get(selector, 0),
            )
            if score > 0:
                candidates.append((score, fragment))

    if candidates:
        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1]

    return prune_article_fragment(soup.body or soup)

def main_content_node(soup):
    return article_content_node(soup)

def main_content_text(soup):
    return clean_text(article_content_node(soup))

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


SEMANTIC_CONCEPTS = {
    # Real estate and housing concepts
    "property": {
        "property", "properties", "apartment", "apartments", "flat", "flats",
        "villa", "villas", "townhouse", "townhouses", "house", "houses",
        "home", "homes", "residence", "residences", "unit", "units",
        "عقار", "عقارات", "شقة", "شقق", "فيلا", "فلل", "منزل", "منازل",
        "وحدة", "وحدات", "سكن", "سكنية"
    },
    "rent": {
        "rent", "rents", "rental", "rentals", "renting", "lease", "leasing",
        "إيجار", "ايجار", "استئجار", "للإيجار", "للايجار", "تأجير", "تاجير"
    },
    "sale": {
        "sale", "sales", "sell", "selling", "buy", "buying", "purchase",
        "بيع", "للبيع", "شراء", "للشراء"
    },
    "price": {
        "price", "prices", "cost", "costs", "rate", "rates",
        "سعر", "أسعار", "اسعار", "تكلفة", "تكاليف"
    },
    "location": {
        "area", "areas", "community", "communities", "neighbourhood",
        "neighborhood", "district", "location", "locations",
        "منطقة", "مناطق", "مجمع", "أحياء", "احياء", "حي", "موقع"
    },
    "popular": {
        "popular", "top", "best", "preferred", "favourite", "favorite",
        "الأكثر", "الاكثر", "أفضل", "افضل", "شهرة", "شعبية"
    },
}

SEMANTIC_TOKEN_MAP = {}
for _concept, _terms in SEMANTIC_CONCEPTS.items():
    for _term in _terms:
        SEMANTIC_TOKEN_MAP[_term.casefold()] = _concept

SEMANTIC_STOP_WORDS = {
    "the","and","for","with","from","this","that","your","you","are","our",
    "in","on","of","to","a","an","is","can","where","what","which","how",
    "في","من","على","إلى","الى","عن","هذا","هذه","مع","و","أو","او","ما",
    "هو","هي","التي","الذي","أين","اين","كيف","يمكن"
}

def semantic_tokens(text):
    out = []
    for token in tokenize(text):
        token = token.casefold()
        if len(token) <= 2 or token in SEMANTIC_STOP_WORDS:
            continue

        # Light English plural normalization for terms not already in the map.
        canonical = SEMANTIC_TOKEN_MAP.get(token)
        if canonical:
            out.append(canonical)
            continue

        if token.endswith("ies") and len(token) > 5:
            token = token[:-3] + "y"
        elif token.endswith("s") and len(token) > 4 and not token.endswith("ss"):
            token = token[:-1]

        out.append(SEMANTIC_TOKEN_MAP.get(token, token))
    return out

def semantic_overlap(a, b):
    """
    Lightweight semantic concept overlap.
    This intentionally does not require a large language model or embedding package.
    It normalises common concepts and then measures how much of A is represented in B.
    """
    aa = set(semantic_tokens(a))
    bb = set(semantic_tokens(b))
    if not aa:
        return 0.0
    return len(aa & bb) / len(aa)


def page_primary_h1(soup):
    """
    Return the primary visible H1 for the article.
    The H1 may sit in the article header outside the isolated article body,
    so this deliberately checks the full page before falling back to the body.
    """
    # Prefer H1s near article/main containers.
    preferred = []
    for selector in [
        "article h1",
        "main h1",
        "[role='main'] h1",
        ".entry-title",
        ".post-title",
        ".article-title",
        "header h1",
        "h1",
    ]:
        for node in soup.select(selector):
            value = re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()
            if value and value not in preferred:
                preferred.append(value)
        if preferred:
            break

    return preferred[0] if preferred else ""

def page_h1s(soup):
    """
    Collect unique H1 values from the full page, because the article header
    is often outside .entry-content or itemprop=articleBody.
    """
    values = []
    for node in soup.find_all("h1"):
        value = re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()
        if value and value not in values:
            values.append(value)
    return values


FAQ_HEADING_LABELS = {
    "faq", "faqs", "frequently asked questions",
    "frequently asked question",
    "أسئلة شائعة", "الأسئلة الشائعة", "الاسئلة الشائعة",
}

def is_faq_heading(text):
    label = re.sub(r"\s+", " ", (text or "").strip()).lower()
    return label in FAQ_HEADING_LABELS or "frequently asked" in label

def faq_section_relevant(section_text, target_topic):
    """
    FAQ is structural. Judge the answers inside the FAQ section rather than
    comparing the literal word FAQ with the Focus Keyword.
    """
    if not section_text or len(section_text.strip()) < 40:
        return False

    semantic = semantic_overlap(target_topic, section_text)
    lexical = keyword_overlap(target_topic, section_text)

    target_concepts = set(semantic_tokens(target_topic))
    section_concepts = set(semantic_tokens(section_text))
    shared_concepts = target_concepts & section_concepts

    # FAQ answers do not have to repeat the full Focus Keyword.
    return (
        semantic >= 0.20
        or lexical >= 0.10
        or len(shared_concepts) >= 2
    )

def heading_level(node):
    if not getattr(node, "name", None):
        return None
    match = re.match(r"^h([1-6])$", node.name)
    return int(match.group(1)) if match else None

def heading_sections(soup):
    """
    Return H2 to H4 headings with hierarchical section content.

    H2 includes its child H3 and H4 content until the next H2.
    H3 includes its child H4 content until the next H2 or H3.
    H4 stops at the next H2, H3 or H4.

    This is important for FAQ sections where the FAQ label is an H2 and
    individual questions are H3 headings.
    """
    container = main_content_node(soup)
    headings = container.find_all(re.compile(r"^h[2-4]$"))
    output = []

    for heading in headings:
        heading_text = re.sub(
            r"\s+",
            " ",
            heading.get_text(" ", strip=True),
        ).strip()
        if not heading_text:
            continue

        current_level = heading_level(heading) or 4
        parts = []

        for node in heading.find_all_next():
            if node is heading:
                continue

            node_level = heading_level(node)
            if node_level is not None and 2 <= node_level <= current_level:
                break

            if node.name in {"p", "li", "td", "th", "figcaption"}:
                value = re.sub(
                    r"\s+",
                    " ",
                    node.get_text(" ", strip=True),
                ).strip()
                if value:
                    parts.append(value)

            if sum(len(x) for x in parts) >= 1800:
                break

        output.append({
            "heading": heading_text,
            "level": current_level,
            "section": " ".join(parts)[:2200],
        })

    return output

def primary_topic_phrase(gram, title, h1, focus_keyword, url):
    """
    Treat a repeated phrase as a primary topic phrase when it is strongly represented
    in the page identity itself. This prevents location/entity names from being treated
    as keyword stuffing by frequency alone.
    """
    gram = (gram or "").strip().lower()
    if not gram:
        return False, []

    evidence = []
    if phrase_count(title, gram):
        evidence.append("Title")
    if phrase_count(h1, gram):
        evidence.append("H1")
    if focus_keyword and phrase_count(focus_keyword, gram):
        evidence.append("Focus Keyword")

    path_words = " ".join(tokenize(urlparse(url).path.replace("-", " ")))
    if phrase_count(path_words, gram):
        evidence.append("URL")

    # Require at least two independent page identity signals.
    return len(evidence) >= 2, evidence

def keyword_repetition_assessment(body_text, focus_keyword, secondary_keywords, title="", h1="", url=""):
    wc = max(1, word_count(body_text))
    gram, density, count = top_ngram_density(body_text, 2)
    is_primary_topic, topic_evidence = primary_topic_phrase(gram, title, h1, focus_keyword, url)

    target_rows = []
    strongest_per_1000 = 0.0
    strongest_keyword = ""
    for kw in ([focus_keyword] if focus_keyword else []) + list(secondary_keywords or []):
        exact = phrase_count(body_text, kw)
        per_1000 = exact * 1000 / wc
        target_rows.append((kw, exact, per_1000))
        if per_1000 > strongest_per_1000:
            strongest_per_1000 = per_1000
            strongest_keyword = kw

    status = PASS
    reasons = []

    # Exact multiword query repetition is the strongest signal.
    if strongest_per_1000 >= 25:
        status = FAIL
        reasons.append(
            f"Target phrase '{strongest_keyword}' appears {strongest_per_1000:.1f} times per 1,000 words."
        )
    elif strongest_per_1000 >= 15:
        status = REVIEW
        reasons.append(
            f"Target phrase '{strongest_keyword}' appears {strongest_per_1000:.1f} times per 1,000 words and should be reviewed for natural wording."
        )

    # N gram density only matters when the phrase is not clearly the page's primary entity/topic.
    if not is_primary_topic:
        if count >= 20 and density >= 0.035:
            status = FAIL
            reasons.append(
                f"The repeated phrase '{gram}' is not identified as the primary page topic and represents {density:.1%} of two word phrases."
            )
        elif count >= 12 and density >= 0.022 and status == PASS:
            status = REVIEW
            reasons.append(
                f"The repeated phrase '{gram}' is not identified as the primary page topic and represents {density:.1%} of two word phrases."
            )
    elif count:
        reasons.append(
            f"The repeated phrase '{gram}' is treated as a primary topic or entity phrase because it appears in {', '.join(topic_evidence)}. Its frequency alone does not trigger REVIEW."
        )

    if not reasons:
        reasons.append("No unusually repetitive target phrase pattern was detected.")

    return {
        "status": status,
        "gram": gram,
        "density": density,
        "count": count,
        "primary_topic": is_primary_topic,
        "topic_evidence": topic_evidence,
        "targets": target_rows,
        "reason": " ".join(reasons),
    }

def normalise_url_for_sitemap(value):
    value = (value or "").strip()
    if not value:
        return ""
    parsed = urlparse(value)
    scheme = parsed.scheme.lower()
    host = parsed.netloc.lower()
    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/")
    return f"{scheme}://{host}{path}"

def sitemap_xml_root(response):
    content = response.content or b""
    if not content:
        return None

    # A .gz sitemap can be a gzip file even when the HTTP response is not using Content Encoding.
    if content[:2] == b"\x1f\x8b":
        try:
            content = gzip.decompress(content)
        except Exception:
            return None

    if len(content) > 12_000_000:
        return None

    try:
        return ET.fromstring(content)
    except Exception:
        return None

def xml_local_name(tag):
    return str(tag).split("}")[-1].lower()

def parse_sitemap_document(response):
    root = sitemap_xml_root(response)
    if root is None:
        return None, []

    root_type = xml_local_name(root.tag)
    entries = []

    if root_type == "sitemapindex":
        for item in list(root):
            loc = ""
            lastmod = ""
            for child in list(item):
                name = xml_local_name(child.tag)
                if name == "loc":
                    loc = (child.text or "").strip()
                elif name == "lastmod":
                    lastmod = (child.text or "").strip()
            if loc:
                entries.append({"loc": loc, "lastmod": lastmod})
        return "index", entries

    if root_type == "urlset":
        for item in list(root):
            loc = ""
            lastmod = ""
            for child in list(item):
                name = xml_local_name(child.tag)
                if name == "loc":
                    loc = (child.text or "").strip()
                elif name == "lastmod":
                    lastmod = (child.text or "").strip()
            if loc:
                entries.append({"loc": loc, "lastmod": lastmod})
        return "urlset", entries

    return None, []

def cache_bucket(seconds=600):
    return int(time.time() // seconds)

@lru_cache(maxsize=128)
def _robots_sitemaps_cached(origin, _bucket):
    found = []
    try:
        rr = requests.get(
            urljoin(origin, "/robots.txt"),
            headers=UA_DESKTOP,
            timeout=SITEMAP_REQUEST_TIMEOUT,
        )
        if rr.status_code == 200:
            for line in rr.text.splitlines():
                if line.lower().strip().startswith("sitemap:"):
                    value = line.split(":", 1)[1].strip()
                    if value.startswith(("http://", "https://")):
                        found.append(value)
    except Exception:
        pass

    return tuple(dict.fromkeys(found))

def robots_sitemaps(origin):
    # Refresh robots sitemap declarations every 10 minutes.
    return _robots_sitemaps_cached(origin, cache_bucket(600))

@lru_cache(maxsize=1024)
def _fetch_sitemap_document_cached(sitemap_url, _bucket):
    """
    Cached sitemap request.
    Returns parsed data rather than a requests.Response so repeated URL audits
    on the same host do not download the same sitemap again.
    """
    record = {
        "url": sitemap_url,
        "status": None,
        "type": "",
        "entries": (),
        "error": "",
    }

    try:
        rr = requests.get(
            sitemap_url,
            headers=UA_DESKTOP,
            timeout=SITEMAP_REQUEST_TIMEOUT,
        )
        record["status"] = rr.status_code

        if rr.status_code != 200:
            return record

        doc_type, entries = parse_sitemap_document(rr)
        if not doc_type:
            return record

        record["type"] = doc_type
        record["entries"] = tuple(
            (entry.get("loc", ""), entry.get("lastmod", ""))
            for entry in entries
            if entry.get("loc")
        )
        return record

    except Exception as exc:
        record["error"] = str(exc)
        return record

def fetch_sitemap_document(sitemap_url):
    # Refresh parsed sitemap documents every 10 minutes.
    return _fetch_sitemap_document_cached(sitemap_url, cache_bucket(600))

def sitemap_priority(sitemap_url, page_url):
    """
    Rank likely child sitemaps first without pretending that ranking is proof.
    If the configured file limit is reached, the result is marked incomplete.
    """
    sm = (sitemap_url or "").lower()
    path = urlparse(page_url).path.lower()
    score = 0

    target_tokens = [
        t for t in re.findall(r"[a-z0-9]+", path)
        if len(t) >= 4
    ]

    for token in target_tokens:
        if token in sm:
            score += 5

    for useful in ("mybayut", "post", "posts", "article", "articles", "blog", "page"):
        if useful in sm:
            score += 3

    if sm.endswith(".xml.gz"):
        score += 1

    return score

@lru_cache(maxsize=512)
def _find_url_in_sitemaps_cached(
    page_url,
    max_sitemaps,
    max_depth,
    _bucket,
):
    """
    Fast recursive sitemap inspection.

    Improvements:
    1. robots.txt and sitemap documents are cached
    2. child sitemap files are fetched in parallel
    3. likely sitemap files are checked first
    4. a strict wall clock budget prevents long UI freezes
    5. incomplete traversal is reported as incomplete rather than pretending
       the URL is absent
    """
    started = time.time()

    parsed = urlparse(page_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    target = normalise_url_for_sitemap(page_url)

    seeds = list(robots_sitemaps(origin))
    seeds += [
        urljoin(origin, "/sitemap.xml"),
        urljoin(origin, "/sitemap_index.xml"),
    ]
    seeds = list(dict.fromkeys(seed for seed in seeds if seed))

    frontier = [(seed, 0) for seed in seeds]
    seen = set()
    checked = []
    accessible = 0
    child_count = 0
    stopped_by_budget = False
    stopped_by_limit = False

    while frontier:
        if time.time() - started >= SITEMAP_TIME_BUDGET:
            stopped_by_budget = True
            break

        remaining_capacity = max_sitemaps - len(checked)
        if remaining_capacity <= 0:
            stopped_by_limit = True
            break

        # Rank the current level and only submit as many files as the configured
        # audit limit allows.
        frontier = sorted(
            frontier,
            key=lambda item: sitemap_priority(item[0], page_url),
            reverse=True,
        )

        current_batch = []
        next_frontier = []

        while frontier and len(current_batch) < min(SITEMAP_WORKERS, remaining_capacity):
            sitemap_url, depth = frontier.pop(0)
            if sitemap_url in seen:
                continue
            seen.add(sitemap_url)
            current_batch.append((sitemap_url, depth))

        if not current_batch:
            # Continue with any unprocessed items if duplicates consumed the batch.
            if frontier:
                continue
            break

        with ThreadPoolExecutor(max_workers=min(SITEMAP_WORKERS, len(current_batch))) as executor:
            future_map = {
                executor.submit(fetch_sitemap_document, sitemap_url): (sitemap_url, depth)
                for sitemap_url, depth in current_batch
            }

            for future in as_completed(future_map):
                sitemap_url, depth = future_map[future]
                record = future.result()

                checked.append({
                    "url": sitemap_url,
                    "status": record.get("status"),
                    "type": record.get("type", ""),
                    "entries": len(record.get("entries") or ()),
                    "error": record.get("error", ""),
                })

                if record.get("status") != 200 or not record.get("type"):
                    continue

                accessible += 1
                entries = record.get("entries") or ()

                if record["type"] == "urlset":
                    for loc, lastmod in entries:
                        if normalise_url_for_sitemap(loc) == target:
                            return {
                                "found": True,
                                "accessible": accessible,
                                "checked": checked,
                                "found_in": sitemap_url,
                                "lastmod": lastmod or "",
                                "child_count": child_count,
                                "complete": True,
                                "stopped_by_budget": False,
                                "stopped_by_limit": False,
                                "elapsed": time.time() - started,
                            }

                elif record["type"] == "index" and depth < max_depth:
                    children = []
                    for loc, _lastmod in entries:
                        if loc and loc not in seen:
                            children.append((loc, depth + 1))

                    children.sort(
                        key=lambda item: sitemap_priority(item[0], page_url),
                        reverse=True,
                    )
                    next_frontier.extend(children)
                    child_count += len(children)

        # Keep unprocessed items from this level, then append newly discovered
        # children. This avoids losing files while still checking likely ones first.
        frontier = frontier + next_frontier

    complete = not frontier and not stopped_by_budget and not stopped_by_limit

    return {
        "found": False,
        "accessible": accessible,
        "checked": checked,
        "found_in": "",
        "lastmod": "",
        "child_count": child_count,
        "complete": complete,
        "stopped_by_budget": stopped_by_budget,
        "stopped_by_limit": stopped_by_limit,
        "elapsed": time.time() - started,
    }

def find_url_in_sitemaps(
    page_url,
    max_sitemaps=SITEMAP_MAX_FILES,
    max_depth=SITEMAP_MAX_DEPTH,
):
    # Cache the completed sitemap result for 10 minutes.
    return _find_url_in_sitemaps_cached(
        page_url,
        max_sitemaps,
        max_depth,
        cache_bucket(600),
    )

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
    """
    Static fallback only.
    aria hidden by itself is not treated as visually hidden because it affects
    the accessibility tree and does not necessarily hide content on screen.
    """
    style = (node.get("style") or "").replace(" ", "").lower()
    hidden_attr = node.has_attr("hidden")
    inert_attr = node.has_attr("inert")
    bad_style = any(x in style for x in [
        "display:none",
        "visibility:hidden",
        "visibility:collapse",
        "opacity:0",
        "font-size:0",
        "height:0",
        "width:0",
        "max-height:0",
        "left:-9999",
        "right:-9999",
        "top:-9999",
        "text-indent:-9999",
        "clip:rect(0",
        "clip-path:inset(50",
        "content-visibility:hidden",
        "transform:scale(0"
    ])
    closed_details = node.name == "details" and not node.has_attr("open")
    return hidden_attr or inert_attr or bad_style or closed_details

def hidden_reasons(node):
    reasons = []
    style = (node.get("style") or "").replace(" ", "").lower()

    if node.has_attr("hidden"):
        value = node.get("hidden")
        if str(value).lower() == "until-found":
            reasons.append("hidden until found")
        else:
            reasons.append("hidden attribute")

    if node.has_attr("inert"):
        reasons.append("inert inactive interface region")

    if node.name == "details" and not node.has_attr("open"):
        reasons.append("closed details disclosure")

    checks = [
        ("display:none", "display none"),
        ("visibility:hidden", "visibility hidden"),
        ("visibility:collapse", "visibility collapse"),
        ("opacity:0", "opacity zero"),
        ("font-size:0", "font size zero"),
        ("height:0", "height zero"),
        ("width:0", "width zero"),
        ("max-height:0", "maximum height zero"),
        ("left:-9999", "positioned outside the visible screen"),
        ("right:-9999", "positioned outside the visible screen"),
        ("top:-9999", "positioned outside the visible screen"),
        ("text-indent:-9999", "text indented outside the visible screen"),
        ("clip:rect(0", "visually clipped"),
        ("clip-path:inset(50", "visually clipped"),
        ("content-visibility:hidden", "content visibility hidden"),
        ("transform:scale(0", "scaled to zero"),
    ]
    for pattern, label in checks:
        if pattern in style:
            reasons.append(label)

    return reasons

def element_label(node):
    if node is None:
        return "Unknown element"

    parts = [node.name or "element"]
    node_id = node.get("id")
    if node_id:
        parts.append(f"id {node_id}")

    classes = node.get("class") or []
    if classes:
        parts.append("class " + " ".join(str(c) for c in classes[:8]))

    role = node.get("role")
    if role:
        parts.append(f"role {role}")

    return ", ".join(parts)

def _token_string(*parts):
    return " ".join(str(p or "") for p in parts).lower()

LEGITIMATE_UI_PATTERNS = {
    "WordPress comment reply control": [
        "cancel-comment-reply-link",
        "cancel reply"
    ],
    "Accordion or collapsible content": [
        "accordion", "collapse", "collapsible", "expandable", "faq-item", "faq_item"
    ],
    "Tab panel": [
        "tabpanel", "tab-panel", "tabcontent", "tab-content", "tabs-panel"
    ],
    "Modal dialog or popup": [
        "modal", "dialog", "popup", "pop-up", "lightbox", "overlay", "drawer", "offcanvas", "off-canvas"
    ],
    "Responsive navigation": [
        "mobile-menu", "mobile_menu", "mobile-nav", "mobile_nav", "hamburger",
        "responsive-menu", "responsive_menu", "desktop-nav", "desktop_nav"
    ],
    "Dropdown or submenu": [
        "dropdown", "sub-menu", "submenu", "mega-menu", "megamenu", "flyout"
    ],
    "Slider or carousel": [
        "slider", "carousel", "slideshow", "swiper", "slick", "splide", "glide", "slide"
    ],
    "Tooltip or popover": [
        "tooltip", "popover", "tippy", "hint", "help-tip"
    ],
    "Accessibility only content": [
        "screen-reader", "screen_reader", "sr-only", "sr_only", "visually-hidden",
        "visually_hidden", "a11y", "accessible-only", "accessibility"
    ],
    "Cookie or consent interface": [
        "cookie", "consent", "privacy-banner", "privacy_banner", "cmp"
    ],
    "Search or filter panel": [
        "search-overlay", "search_panel", "search-panel", "filter-panel", "filter_panel",
        "filter-drawer", "filter_drawer", "sort-panel", "sort_panel"
    ],
    "Form status or validation message": [
        "validation", "error-message", "error_message", "form-message", "form_message",
        "success-message", "success_message", "alert"
    ],
    "Loading or deferred interface": [
        "loading", "loader", "spinner", "skeleton", "lazy", "placeholder"
    ],
}

SUSPICIOUS_HIDE_REASONS = {
    "opacity zero",
    "font size zero",
    "positioned outside the visible screen",
    "text indented outside the visible screen",
    "scaled to zero",
}

def known_ui_reason_from_text(context_text):
    context = (context_text or "").lower()
    for label, patterns in LEGITIMATE_UI_PATTERNS.items():
        if any(pattern in context for pattern in patterns):
            return label
    return ""

def static_hidden_link_details(soup, base_url):
    details = []
    seen = set()

    for anchor in soup.find_all("a", href=True):
        hidden_element = None
        node = anchor

        while node is not None and getattr(node, "name", None):
            if obvious_hidden(node):
                hidden_element = node
                break
            node = node.parent

        if hidden_element is None:
            continue

        href = urljoin(base_url, anchor.get("href"))
        anchor_text = anchor.get_text(" ", strip=True) or "(no visible anchor text)"
        reasons = hidden_reasons(hidden_element)

        context_parts = [
            element_label(anchor),
            element_label(hidden_element),
            anchor_text,
            anchor.get("aria-label"),
            anchor.get("title"),
            hidden_element.get("aria-label"),
            hidden_element.get("role"),
        ]
        context = _token_string(*context_parts)
        known_reason = known_ui_reason_from_text(context)

        status = REVIEW
        purpose = "The reason for hiding could not be confirmed from static HTML alone."

        if anchor.get("id") == "cancel-comment-reply-link":
            status = PASS
            known_reason = "WordPress comment reply control"
            purpose = "This is the standard WordPress Cancel Reply control. It is hidden when the user is not actively replying to a comment."
        elif known_reason:
            status = PASS
            purpose = f"The link appears to belong to a legitimate {known_reason.lower()}."
        elif any(r in SUSPICIOUS_HIDE_REASONS for r in reasons):
            status = FAIL
            purpose = "The link uses a hiding method associated with intentionally invisible links and no legitimate interface purpose was detected."

        key = (href, anchor_text, element_label(hidden_element), tuple(reasons), status)
        if key in seen:
            continue
        seen.add(key)

        details.append({
            "url": href,
            "anchor_text": anchor_text,
            "hidden_element": element_label(hidden_element),
            "hidden_because": ", ".join(reasons) if reasons else "hidden element rule matched",
            "purpose": known_reason or "Unknown",
            "status": status,
            "explanation": purpose,
            "source": "Static HTML fallback",
        })

    return details

@lru_cache(maxsize=128)
def _rendered_hidden_inventory_cached(url, _bucket):
    """
    Uses a real browser when Playwright and Chromium are available.
    It checks computed visibility on desktop and mobile. It also records
    ancestor context so the system can identify why an element is hidden.
    """
    if not PLAYWRIGHT_AVAILABLE:
        return {"available": False, "error": "Playwright is not installed", "desktop": [], "mobile": []}

    js = r"""
    () => {
      function safeText(v) {
        return (v || "").replace(/\s+/g, " ").trim().slice(0, 300);
      }

      function nodeInfo(el) {
        if (!el || el.nodeType !== 1) return null;
        const cs = getComputedStyle(el);
        const rect = el.getBoundingClientRect();

        return {
          tag: (el.tagName || "").toLowerCase(),
          id: el.id || "",
          classes: Array.from(el.classList || []).slice(0, 12),
          role: el.getAttribute("role") || "",
          ariaHidden: el.getAttribute("aria-hidden") || "",
          ariaExpanded: el.getAttribute("aria-expanded") || "",
          ariaControls: el.getAttribute("aria-controls") || "",
          ariaHaspopup: el.getAttribute("aria-haspopup") || "",
          ariaLabel: el.getAttribute("aria-label") || "",
          title: el.getAttribute("title") || "",
          hiddenAttr: el.hasAttribute("hidden"),
          hiddenValue: el.getAttribute("hidden") || "",
          inert: el.hasAttribute("inert"),
          open: el.tagName === "DETAILS" ? el.hasAttribute("open") : null,
          dataState: el.getAttribute("data-state") || "",
          display: cs.display,
          visibility: cs.visibility,
          opacity: cs.opacity,
          fontSize: cs.fontSize,
          position: cs.position,
          textIndent: cs.textIndent,
          clip: cs.clip,
          clipPath: cs.clipPath,
          contentVisibility: cs.contentVisibility || "",
          transform: cs.transform,
          maxHeight: cs.maxHeight,
          overflow: cs.overflow,
          pointerEvents: cs.pointerEvents,
          color: cs.color,
          backgroundColor: cs.backgroundColor,
          rect: {
            x: Math.round(rect.x * 100) / 100,
            y: Math.round(rect.y * 100) / 100,
            width: Math.round(rect.width * 100) / 100,
            height: Math.round(rect.height * 100) / 100
          }
        };
      }

      function hiddenReasons(anchor) {
        const reasons = [];
        const ancestors = [];
        let el = anchor;
        let hiddenNode = null;

        while (el && el.nodeType === 1) {
          const info = nodeInfo(el);
          ancestors.push(info);
          const cs = getComputedStyle(el);

          if (el.hasAttribute("hidden")) {
            reasons.push(el.getAttribute("hidden") === "until-found" ? "hidden until found" : "hidden attribute");
            hiddenNode = hiddenNode || info;
          }

          if (el.hasAttribute("inert")) {
            reasons.push("inert inactive interface region");
            hiddenNode = hiddenNode || info;
          }

          if (el.tagName === "DETAILS" && !el.hasAttribute("open") && anchor !== el.querySelector("summary")) {
            reasons.push("closed details disclosure");
            hiddenNode = hiddenNode || info;
          }

          if (cs.display === "none") {
            reasons.push("display none");
            hiddenNode = hiddenNode || info;
          }

          if (cs.visibility === "hidden") {
            reasons.push("visibility hidden");
            hiddenNode = hiddenNode || info;
          }

          if (cs.visibility === "collapse") {
            reasons.push("visibility collapse");
            hiddenNode = hiddenNode || info;
          }

          if (parseFloat(cs.opacity || "1") <= 0.01) {
            reasons.push("opacity zero");
            hiddenNode = hiddenNode || info;
          }

          if (parseFloat(cs.fontSize || "16") <= 0.5) {
            reasons.push("font size zero");
            hiddenNode = hiddenNode || info;
          }

          if ((cs.contentVisibility || "") === "hidden") {
            reasons.push("content visibility hidden");
            hiddenNode = hiddenNode || info;
          }

          if ((cs.transform || "").includes("matrix(0") || (cs.transform || "").includes("scale(0")) {
            reasons.push("scaled to zero");
            hiddenNode = hiddenNode || info;
          }

          const ti = parseFloat(cs.textIndent || "0");
          if (!Number.isNaN(ti) && ti < -1000) {
            reasons.push("text indented outside the visible screen");
            hiddenNode = hiddenNode || info;
          }

          const clip = (cs.clip || "").replace(/\s+/g, "").toLowerCase();
          const clipPath = (cs.clipPath || "").replace(/\s+/g, "").toLowerCase();
          if (clip.includes("rect(0") || clipPath.includes("inset(50")) {
            reasons.push("visually clipped");
            hiddenNode = hiddenNode || info;
          }

          el = el.parentElement;
        }

        const rect = anchor.getBoundingClientRect();
        if (rect.width <= 0.5) reasons.push("zero visible width");
        if (rect.height <= 0.5) reasons.push("zero visible height");

        const vw = window.innerWidth;
        const vh = window.innerHeight;
        if (
          rect.width > 0 &&
          rect.height > 0 &&
          (rect.right < -50 || rect.left > vw + 50 || rect.bottom < -50 || rect.top > vh + 5000)
        ) {
          reasons.push("positioned outside the visible screen");
        }

        let covered = false;
        let coveringElement = "";
        if (rect.width > 2 && rect.height > 2) {
          const cx = Math.max(0, Math.min(vw - 1, rect.left + rect.width / 2));
          const cy = Math.max(0, Math.min(vh - 1, rect.top + rect.height / 2));
          if (cx >= 0 && cy >= 0 && cx < vw && cy < vh) {
            const top = document.elementFromPoint(cx, cy);
            if (top && top !== anchor && !anchor.contains(top) && !top.contains(anchor)) {
              covered = true;
              coveringElement = `${top.tagName.toLowerCase()}#${top.id || ""}.${Array.from(top.classList || []).slice(0,4).join(".")}`;
            }
          }
        }

        const visualHidden =
          reasons.some(r => [
            "hidden attribute",
            "hidden until found",
            "inert inactive interface region",
            "closed details disclosure",
            "display none",
            "visibility hidden",
            "visibility collapse",
            "opacity zero",
            "font size zero",
            "content visibility hidden",
            "scaled to zero",
            "text indented outside the visible screen",
            "visually clipped",
            "zero visible width",
            "zero visible height",
            "positioned outside the visible screen"
          ].includes(r));

        return {
          reasons: Array.from(new Set(reasons)),
          ancestors,
          hiddenNode,
          visualHidden,
          covered,
          coveringElement
        };
      }

      function controllerInfo(ancestors) {
        const found = [];
        for (const a of ancestors) {
          if (!a || !a.id) continue;
          const esc = (window.CSS && CSS.escape) ? CSS.escape(a.id) : a.id.replace(/"/g, '\\"');
          const controls = document.querySelectorAll(`[aria-controls="${esc}"]`);
          for (const c of controls) {
            found.push({
              tag: (c.tagName || "").toLowerCase(),
              id: c.id || "",
              classes: Array.from(c.classList || []).slice(0, 8),
              text: safeText(c.innerText || c.textContent),
              ariaExpanded: c.getAttribute("aria-expanded") || "",
              ariaHaspopup: c.getAttribute("aria-haspopup") || ""
            });
          }
        }
        return found.slice(0, 5);
      }

      return Array.from(document.querySelectorAll("a[href]")).map((a, index) => {
        const hidden = hiddenReasons(a);
        const info = nodeInfo(a);
        const ancestryText = hidden.ancestors.map(x => {
          if (!x) return "";
          return [
            x.tag, x.id, ...(x.classes || []), x.role, x.ariaLabel,
            x.ariaExpanded, x.ariaControls, x.ariaHaspopup, x.dataState
          ].join(" ");
        }).join(" ");

        return {
          index,
          href: a.href,
          text: safeText(a.innerText || a.textContent) || "(no visible anchor text)",
          id: a.id || "",
          classes: Array.from(a.classList || []).slice(0, 12),
          rel: a.getAttribute("rel") || "",
          ariaLabel: a.getAttribute("aria-label") || "",
          title: a.getAttribute("title") || "",
          role: a.getAttribute("role") || "",
          info,
          reasons: hidden.reasons,
          visualHidden: hidden.visualHidden,
          hiddenNode: hidden.hiddenNode,
          ancestors: hidden.ancestors,
          ancestryText,
          controllers: controllerInfo(hidden.ancestors),
          covered: hidden.covered,
          coveringElement: hidden.coveringElement
        };
      }).filter(x => x.visualHidden);
    }
    """

    result = {"available": True, "error": "", "desktop": [], "mobile": []}

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)

            for label, viewport, user_agent in [
                ("desktop", {"width": 1440, "height": 1100}, UA_DESKTOP["User-Agent"]),
                ("mobile", {"width": 390, "height": 844}, UA_MOBILE["User-Agent"]),
            ]:
                context = browser.new_context(
                    viewport=viewport,
                    user_agent=user_agent,
                    ignore_https_errors=True,
                )
                page = context.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=PLAYWRIGHT_NAV_TIMEOUT)
                page.wait_for_timeout(PLAYWRIGHT_SETTLE_MS)
                result[label] = page.evaluate(js)
                context.close()

            browser.close()

    except Exception as exc:
        result["available"] = False
        result["error"] = str(exc)
        result["desktop"] = []
        result["mobile"] = []

    return result

def rendered_hidden_inventory(url):
    # Rendered visibility can change as the page changes, so cache only 5 minutes.
    return _rendered_hidden_inventory_cached(url, cache_bucket(300))

def _rendered_key(item):
    if item.get("id"):
        return "id:" + item["id"]
    return "|".join([
        item.get("href", ""),
        item.get("text", ""),
        " ".join(item.get("classes") or [])[:160]
    ])

def classify_rendered_hidden_link(item, visible_in_other_viewport=False):
    href = item.get("href", "")
    text = item.get("text", "")
    item_id = item.get("id", "")
    classes = " ".join(item.get("classes") or [])
    ancestry = item.get("ancestryText", "")
    reasons = item.get("reasons") or []
    controllers = item.get("controllers") or []
    hidden_node = item.get("hiddenNode") or {}

    context = _token_string(
        href,
        text,
        item_id,
        classes,
        ancestry,
        item.get("ariaLabel"),
        item.get("title"),
        item.get("role"),
        hidden_node.get("id"),
        " ".join(hidden_node.get("classes") or []),
        hidden_node.get("role"),
        hidden_node.get("ariaLabel"),
        hidden_node.get("dataState"),
        " ".join(c.get("text", "") for c in controllers),
    )

    # Exact known WordPress UI
    if item_id == "cancel-comment-reply-link" or "cancel-comment-reply-link" in context:
        return PASS, "WordPress comment reply control", (
            "This is the standard WordPress Cancel Reply control. "
            "It is hidden when the visitor is not actively replying to a comment and appears when needed."
        )

    # Responsive desktop or mobile duplication
    if visible_in_other_viewport:
        return PASS, "Responsive interface", (
            "The link is hidden in one viewport but available in the other viewport. "
            "This is consistent with responsive desktop and mobile interface behaviour."
        )

    # Native disclosure
    if "closed details disclosure" in reasons:
        return PASS, "Native disclosure control", (
            "The link is inside a closed details element and becomes available when the user opens that disclosure."
        )

    # Explicit controller relationship
    if controllers:
        collapsed = any((c.get("ariaExpanded") or "").lower() == "false" for c in controllers)
        popup = any((c.get("ariaHaspopup") or "").lower() not in {"", "false"} for c in controllers)
        if collapsed or popup:
            return PASS, "Controlled interactive panel", (
                "The hidden element is connected to a visible interface control through ARIA controls. "
                "It is hidden while that panel is closed and becomes available through user interaction."
            )

    known_reason = known_ui_reason_from_text(context)
    if known_reason:
        return PASS, known_reason, (
            f"The link belongs to a recognised {known_reason.lower()} pattern. "
            "This type of content can legitimately be hidden until the relevant interface state is active."
        )

    # Accessibility semantics
    if any("accessibility" in x.lower() or "screen reader" in x.lower() for x in [known_reason]):
        return PASS, "Accessibility only content", (
            "The link is intentionally available for assistive technology or accessibility navigation."
        )

    # hidden until found is a browser supported disclosure state
    if "hidden until found" in reasons:
        return PASS, "Hidden until found", (
            "The element uses the browser hidden until found state and can be revealed by Find in Page or fragment navigation."
        )

    if "inert inactive interface region" in reasons:
        return PASS, "Inactive interface region", (
            "The link is inside an inert interface region. It is intentionally inactive while another interface state is active."
        )

    # Strong suspicious methods when no legitimate UI purpose is found
    strong_suspicious = [r for r in reasons if r in SUSPICIOUS_HIDE_REASONS]
    tiny_anchor = len(tokenize(text)) == 0 and len(text.strip()) <= 2

    if strong_suspicious or tiny_anchor:
        return FAIL, "Unexplained concealed link", (
            "The link uses a strongly concealed presentation method and the scanner found no recognised interface or accessibility reason for hiding it."
        )

    # A link hidden only by display or visibility can be legitimate, but requires context
    return REVIEW, "Unconfirmed hidden interface element", (
        "The link is not visible in the current interface state, but the scanner could not confirm a recognised user interface, responsive or accessibility reason."
    )

def rendered_hidden_link_details(url):
    inventory = rendered_hidden_inventory(url)

    if not inventory.get("available"):
        return [], inventory

    desktop = inventory.get("desktop") or []
    mobile = inventory.get("mobile") or []

    desktop_map = {_rendered_key(x): x for x in desktop}
    mobile_map = {_rendered_key(x): x for x in mobile}

    keys = list(dict.fromkeys(list(desktop_map.keys()) + list(mobile_map.keys())))
    details = []

    for key in keys:
        d = desktop_map.get(key)
        m = mobile_map.get(key)
        item = d or m

        hidden_desktop = d is not None
        hidden_mobile = m is not None

        # If the same element is hidden in only one viewport, treat it as visible in the other.
        visible_other = hidden_desktop != hidden_mobile

        status, purpose, explanation = classify_rendered_hidden_link(
            item,
            visible_in_other_viewport=visible_other
        )

        hidden_node = item.get("hiddenNode") or {}
        hidden_element_parts = [
            hidden_node.get("tag") or item.get("info", {}).get("tag") or "element"
        ]
        if hidden_node.get("id"):
            hidden_element_parts.append("id " + hidden_node["id"])
        if hidden_node.get("classes"):
            hidden_element_parts.append("class " + " ".join(hidden_node["classes"][:8]))
        if hidden_node.get("role"):
            hidden_element_parts.append("role " + hidden_node["role"])

        details.append({
            "url": item.get("href", ""),
            "anchor_text": item.get("text", ""),
            "hidden_element": ", ".join(hidden_element_parts),
            "hidden_because": ", ".join(item.get("reasons") or []) or "computed browser visibility",
            "purpose": purpose,
            "status": status,
            "explanation": explanation,
            "desktop_hidden": hidden_desktop,
            "mobile_hidden": hidden_mobile,
            "controllers": item.get("controllers") or [],
            "source": "Rendered browser inspection",
        })

    return details, inventory

def hidden_link_details(soup, base_url):
    """
    Preferred path: rendered browser inspection.
    Fallback path: static HTML and inline style inspection.
    """
    rendered, inventory = rendered_hidden_link_details(base_url)
    if inventory.get("available"):
        return rendered, inventory

    return static_hidden_link_details(soup, base_url), inventory

def classify_hidden_text_static(node):
    reasons = hidden_reasons(node)
    context = _token_string(
        element_label(node),
        node.get("aria-label"),
        node.get("role"),
        node.get("data-state"),
    )
    known_reason = known_ui_reason_from_text(context)

    if known_reason:
        return PASS, known_reason, f"The hidden text belongs to a recognised {known_reason.lower()} pattern."

    if node.name == "details" and not node.has_attr("open"):
        return PASS, "Native disclosure control", "The text is inside a closed details element."

    if node.has_attr("inert"):
        return PASS, "Inactive interface region", "The text is inside an inert inactive interface region."

    if str(node.get("hidden") or "").lower() == "until-found":
        return PASS, "Hidden until found", "The text uses the browser hidden until found state."

    if any(r in SUSPICIOUS_HIDE_REASONS for r in reasons):
        return FAIL, "Unexplained concealed text", "The text uses a strongly concealed method and no legitimate interface reason was detected."

    return REVIEW, "Unconfirmed hidden interface text", "The text is hidden, but the system could not determine a recognised interface or accessibility purpose."

def hidden_text_details(soup):
    """
    Static text reason classification. We intentionally avoid counting every
    nested descendant as a separate issue by keeping only top level hidden
    blocks with substantial text.
    """
    items = []
    seen_text = set()

    for node in soup.find_all(True):
        if not obvious_hidden(node):
            continue

        text_value = re.sub(r"\s+", " ", node.get_text(" ", strip=True))
        if len(text_value) < 40:
            continue

        # Skip nested hidden elements when their parent is already hidden.
        parent = node.parent
        if parent is not None and getattr(parent, "name", None) and obvious_hidden(parent):
            continue

        normalized = text_value.lower()[:500]
        if normalized in seen_text:
            continue
        seen_text.add(normalized)

        status, purpose, explanation = classify_hidden_text_static(node)
        items.append({
            "text": text_value[:240],
            "hidden_element": element_label(node),
            "hidden_because": ", ".join(hidden_reasons(node)) or "hidden element rule matched",
            "purpose": purpose,
            "status": status,
            "explanation": explanation,
        })

    return items

def unique_http_urls(urls):
    return list(dict.fromkeys(
        u for u in urls
        if isinstance(u, str) and u.startswith(("http://", "https://"))
    ))

@lru_cache(maxsize=4096)
def _probe_http_url_cached(url, timeout, _bucket):
    started = time.time()
    result_data = {
        "url": url,
        "status": None,
        "final_url": url,
        "error": "",
        "elapsed": 0.0,
    }

    try:
        response = requests.head(
            url,
            headers=UA_DESKTOP,
            timeout=timeout,
            allow_redirects=True,
        )

        # Some sites do not support HEAD correctly. Use a lightweight GET fallback.
        if response.status_code in {400, 403, 405, 406, 429}:
            response = requests.get(
                url,
                headers=UA_DESKTOP,
                timeout=timeout,
                allow_redirects=True,
                stream=True,
            )
            response.close()

        result_data["status"] = response.status_code
        result_data["final_url"] = response.url
    except Exception as exc:
        result_data["error"] = str(exc)

    result_data["elapsed"] = time.time() - started
    return result_data

def probe_http_url(url, timeout=LINK_CHECK_TIMEOUT):
    # Network validation refreshes every 10 minutes.
    return _probe_http_url_cached(url, timeout, cache_bucket(600))

def validate_url_set(urls, timeout=LINK_CHECK_TIMEOUT, workers=LINK_CHECK_WORKERS):
    urls = unique_http_urls(urls)
    if not urls:
        return {
            "checked": [],
            "working": [],
            "redirected": [],
            "broken": [],
            "restricted": [],
            "server_errors": [],
            "unreachable": [],
        }

    checked = []
    with ThreadPoolExecutor(max_workers=min(workers, len(urls))) as executor:
        futures = {
            executor.submit(probe_http_url, url, timeout): url
            for url in urls
        }
        for future in as_completed(futures):
            checked.append(future.result())

    working = []
    redirected = []
    broken = []
    restricted = []
    server_errors = []
    unreachable = []

    for item in checked:
        status = item.get("status")
        if status is None:
            unreachable.append(item)
        elif 200 <= status < 300:
            working.append(item)
            if item.get("final_url") and item["final_url"] != item["url"]:
                redirected.append(item)
        elif status in {401, 403, 429}:
            restricted.append(item)
        elif status in {404, 410} or 400 <= status < 500:
            broken.append(item)
        elif status >= 500:
            server_errors.append(item)

    return {
        "checked": checked,
        "working": working,
        "redirected": redirected,
        "broken": broken,
        "restricted": restricted,
        "server_errors": server_errors,
        "unreachable": unreachable,
    }

def extract_page_links(soup, base_url):
    parsed = urlparse(base_url)
    host = parsed.netloc.lower().replace("www.", "")
    internal = []
    external = []

    for anchor in soup.find_all("a", href=True):
        href = urljoin(base_url, anchor.get("href"))
        if not href.startswith(("http://", "https://")):
            continue

        target_host = urlparse(href).netloc.lower().replace("www.", "")
        if target_host == host:
            internal.append(href)
        else:
            external.append(href)

    return unique_http_urls(internal), unique_http_urls(external)

def extract_resource_urls(soup, base_url):
    """
    Extract only resources that materially participate in page rendering.

    Excludes WordPress API discovery, oEmbed, canonical, alternate feeds,
    shortlinks and other link relations that are not CSS, JS, image or font
    resources required for rendering.
    """
    urls = []

    # JavaScript
    for node in soup.find_all("script", src=True):
        resolved = urljoin(base_url, node.get("src"))
        if resolved.startswith(("http://", "https://")):
            urls.append(resolved)

    # Images
    for node in soup.find_all("img", src=True):
        resolved = urljoin(base_url, node.get("src"))
        if resolved.startswith(("http://", "https://")):
            urls.append(resolved)

    # Picture/video source assets
    for node in soup.find_all("source", src=True):
        resolved = urljoin(base_url, node.get("src"))
        if resolved.startswith(("http://", "https://")):
            urls.append(resolved)

    # Only render-relevant <link> elements
    for node in soup.find_all("link", href=True):
        rel = {str(x).lower() for x in (node.get("rel") or [])}
        as_value = (node.get("as") or "").lower()

        is_stylesheet = "stylesheet" in rel
        is_preload_resource = (
            "preload" in rel
            and as_value in {"style", "script", "font", "image"}
        )

        if not (is_stylesheet or is_preload_resource):
            continue

        resolved = urljoin(base_url, node.get("href"))
        if resolved.startswith(("http://", "https://")):
            urls.append(resolved)

    # Explicitly remove known WordPress discovery/API endpoints if they were
    # somehow included through unusual markup.
    filtered = []
    for url in unique_http_urls(urls):
        low = url.lower()
        if any(fragment in low for fragment in [
            "/xmlrpc.php",
            "/wp-json/",
            "/oembed/",
            "api.w.org",
        ]):
            continue
        filtered.append(url)

    return filtered


SOCIAL_DOMAINS = {
    "facebook.com", "www.facebook.com", "m.facebook.com",
    "instagram.com", "www.instagram.com",
    "linkedin.com", "www.linkedin.com",
    "twitter.com", "www.twitter.com",
    "x.com", "www.x.com",
    "tiktok.com", "www.tiktok.com",
    "pinterest.com", "www.pinterest.com",
    "youtube.com", "www.youtube.com",
}

def is_social_domain(url):
    host = urlparse(url or "").netloc.lower()
    return host in SOCIAL_DOMAINS or any(host.endswith("." + d) for d in SOCIAL_DOMAINS)

def social_platform_expected_block(item):
    """
    Some social platforms return login pages, 400/401/403 or anti-bot responses
    to automated requests even when the user-facing link is valid.
    These should not be classified as broken by status alone.
    """
    url = item.get("url", "")
    final_url = item.get("final_url", "")
    status = item.get("status")

    if not is_social_domain(url):
        return False

    if status in {400, 401, 403, 429}:
        return True

    final_low = (final_url or "").lower()
    if any(part in final_low for part in ["/login", "/checkpoint", "/signin", "/auth"]):
        return True

    return False

def classify_link_validation(validation):
    """
    Separate genuinely broken links from expected automated access restrictions.
    """
    working = []
    broken = []
    restricted = []
    expected_platform = []
    unreachable = []
    server_errors = []
    redirected = []

    for item in validation.get("checked", []):
        status = item.get("status")

        if social_platform_expected_block(item):
            expected_platform.append(item)
            continue

        if status is None:
            unreachable.append(item)
        elif 200 <= status < 300:
            working.append(item)
            if item.get("final_url") and item["final_url"] != item["url"]:
                redirected.append(item)
        elif status in {401, 403, 429}:
            restricted.append(item)
        elif status in {404, 410}:
            broken.append(item)
        elif 400 <= status < 500:
            broken.append(item)
        elif status >= 500:
            server_errors.append(item)

    return {
        "checked": validation.get("checked", []),
        "working": working,
        "broken": broken,
        "restricted": restricted,
        "expected_platform": expected_platform,
        "unreachable": unreachable,
        "server_errors": server_errors,
        "redirected": redirected,
    }

def validation_problem_examples(validation, limit=6):
    items = (
        validation.get("broken", [])
        + validation.get("server_errors", [])
        + validation.get("restricted", [])
        + validation.get("unreachable", [])
    )
    examples = []

    for item in items[:limit]:
        if item.get("status") is not None:
            examples.append(
                f"{item['url']} returned HTTP {item['status']}"
                + (
                    f" and ended at {item['final_url']}"
                    if item.get("final_url") and item["final_url"] != item["url"]
                    else ""
                )
            )
        else:
            examples.append(
                f"{item['url']} could not be verified: {item.get('error') or 'request error'}"
            )

    return examples

def parse_datetime_value(value):
    if not value:
        return None
    if isinstance(value, (list, dict)):
        return None

    raw = str(value).strip()
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        pass

    try:
        return parsedate_to_datetime(raw)
    except Exception:
        return None

def datetime_difference_hours(a, b):
    da = parse_datetime_value(a)
    db = parse_datetime_value(b)
    if da is None or db is None:
        return None

    if da.tzinfo is None:
        da = da.replace(tzinfo=timezone.utc)
    if db.tzinfo is None:
        db = db.replace(tzinfo=timezone.utc)

    return abs((da - db).total_seconds()) / 3600

def visible_date_signals(soup):
    published = []
    modified = []

    meta_map = [
        ("article:published_time", published),
        ("article:modified_time", modified),
        ("og:updated_time", modified),
    ]

    for prop, bucket in meta_map:
        value = meta_content(soup, prop=prop)
        if value:
            bucket.append(value)

    for node in soup.find_all("time"):
        value = node.get("datetime") or node.get_text(" ", strip=True)
        context = node_signature(node)
        if any(x in context for x in ["modified", "updated", "update"]):
            modified.append(value)
        elif any(x in context for x in ["published", "publish", "date"]):
            published.append(value)

    return {
        "published": list(dict.fromkeys(x for x in published if x)),
        "modified": list(dict.fromkeys(x for x in modified if x)),
    }

def contextual_old_years(text):
    """
    Return old year references together with the sentence that contains each year.
    Only time sensitive contexts should trigger REVIEW.
    """
    sentences = [
        re.sub(r"\s+", " ", s).strip()
        for s in re.split(r"(?<=[.!?؟])\s+|\n+", text or "")
        if s.strip()
    ]

    historical_terms = [
        "launched", "established", "founded", "opened", "built", "completed",
        "introduced", "inaugurated", "since", "history", "historical",
        "أطلق", "تأسس", "افتتح", "أنشئ", "بني", "اكتمل", "منذ", "تاريخ"
    ]
    sensitive_terms = [
        "price", "prices", "rent", "rental", "roi", "yield", "fee", "fees",
        "law", "rule", "visa", "bus route", "metro", "project status",
        "completion", "handover", "aed", "%",
        "سعر", "أسعار", "اسعار", "إيجار", "ايجار", "عائد", "رسوم",
        "قانون", "مترو", "تسليم"
    ]

    output = []
    for sentence in sentences:
        years = [
            int(y)
            for y in re.findall(r"\b20(?:1\d|2\d)\b", sentence)
            if int(y) <= CURRENT_YEAR - 2
        ]
        if not years:
            continue

        low = sentence.lower()
        historical = any(term in low for term in historical_terms)
        sensitive = any(term in low for term in sensitive_terms)

        # Historical context can coexist with a price claim. Time sensitive wins.
        classification = "Time sensitive" if sensitive else "Contextual or historical" if historical else "Context needs review"

        for year in sorted(set(years)):
            output.append({
                "year": year,
                "sentence": sentence[:320],
                "classification": classification,
                "sensitive": sensitive,
            })

    return output

def factual_claim_examples(article_soup, base_url, limit=6):
    """
    Extract concrete verifiable claims, not generic promotional language.

    Strong claim signals include:
    numbers, dates, percentages, prices, distances, durations,
    completion/launch facts, developer attribution, ranking/data claims,
    named facilities and specific location statements.
    """
    claims = []

    strong_patterns = [
        r"\bAED\s*\d",
        r"\b\d+(?:\.\d+)?%",
        r"\b20(?:1\d|2\d)\b",
        r"\b\d+\s*(?:minute|minutes|min|km|kilometre|kilometer|metre|meter|sq\.?\s*ft|sqft)\b",
        r"\b(?:average|avg\.?)\s+(?:price|rent|roi|yield)\b",
        r"\b(?:completed|launched|established|opened|founded|developed by|developer is|consists of|comprises)\b",
        r"\b(?:most searched|most popular|ranked|according to our data|data experts)\b",
        r"\b(?:located in|located at|situated in|situated at)\b",
        r"\b(?:أسعار|سعر|إيجار|ايجار|عائد|رسوم)\s+\d",
        r"\b(?:دقيقة|دقائق|كم|كيلومتر|متر)\b",
        r"\b(?:تم إطلاق|تم اطلاق|اكتمل|افتتح|تأسس|طورته|المطور)\b",
        r"\b(?:الأكثر بحثا|الاكثر بحثا|وفقا لبيانات|بحسب البيانات)\b",
    ]

    weak_marketing_terms = {
        "great option",
        "comfortable lifestyle",
        "convenient lifestyle",
        "popular choice",
        "not hard to see why",
        "perfect choice",
        "ideal choice",
        "excellent facilities",
    }

    for node in article_soup.find_all(["p", "li", "td"]):
        value = re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()
        if len(value) < 45:
            continue

        low = value.lower()

        # Skip purely promotional/generic text if it has no strong factual signal.
        has_strong = any(
            re.search(pattern, value, flags=re.I)
            for pattern in strong_patterns
        )

        if not has_strong:
            continue

        # If a sentence is dominated by marketing language and has no numeric/date
        # or specific attribution signal, do not treat it as a factual claim.
        has_numeric_specificity = bool(re.search(
            r"\b\d+(?:[.,]\d+)?(?:%|\s*(?:minutes?|km|sqft|sq\.?\s*ft))?\b|AED\s*\d",
            value,
            flags=re.I,
        ))
        has_attribution = bool(re.search(
            r"\b(?:according to|data experts|developed by|developer|completed|launched|located in|located at)\b",
            value,
            flags=re.I,
        ))

        if any(term in low for term in weak_marketing_terms) and not (has_numeric_specificity or has_attribution):
            continue

        sources = []
        for anchor in node.find_all("a", href=True):
            resolved = urljoin(base_url, anchor.get("href"))
            if resolved.startswith(("http://", "https://")):
                sources.append(resolved)

        claims.append({
            "claim": value[:360],
            "source_links": unique_http_urls(sources),
        })

        if len(claims) >= limit:
            break

    return claims

GENERIC_ENTITY_HEADINGS = {
    "faqs", "faq", "introduction", "conclusion", "overview", "summary",
    "popular", "comments", "leave a reply", "find a reliable agent",
    "frequently asked questions", "find an agent", "read more",
    "rent apartments", "rent villas", "apartments", "villas",
    "where to rent", "where can you rent",
}


ENTITY_GENERIC_PREFIX_PATTERNS = [
    r"^(?:studio|studios)\s+(?:in|at|from)\s+",
    r"^(?:apartment|apartments|flat|flats)\s+(?:in|at|from)\s+",
    r"^(?:villa|villas|townhouse|townhouses)\s+(?:in|at|from)\s+",
    r"^(?:unit|units|property|properties)\s+(?:in|at|from)\s+",
    r"^(?:rent|rental|renting)\s+(?:in|at|from)\s+",
]

def clean_entity_candidate(value):
    """
    Remove generic property wording around a proper noun.

    Example:
    studio in Elite Sports Residents
    becomes:
    Elite Sports Residents
    """
    value = re.sub(r"\s+", " ", (value or "")).strip(" ,.;:-")

    changed = True
    while changed and value:
        changed = False
        for pattern in ENTITY_GENERIC_PREFIX_PATTERNS:
            cleaned = re.sub(
                pattern,
                "",
                value,
                flags=re.I,
            ).strip(" ,.;:-")
            if cleaned != value:
                value = cleaned
                changed = True

    return value

def entity_similarity_key(value):
    value = clean_entity_candidate(value).casefold()
    value = re.sub(r"[^a-z0-9\u0600-\u06ff ]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value

def roman_variant_pair(a, b):
    """
    Do not flag legitimate numbered project variants such as
    Global Golf Residence and Global Golf Residence II.
    """
    roman = {"i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x"}
    aa = entity_similarity_key(a).split()
    bb = entity_similarity_key(b).split()

    if len(aa) + 1 == len(bb) and bb[-1] in roman and aa == bb[:-1]:
        return True
    if len(bb) + 1 == len(aa) and aa[-1] in roman and bb == aa[:-1]:
        return True
    return False

def near_duplicate_entities(entities, threshold=0.88):
    """
    Find suspiciously similar entity spellings.

    This is a consistency signal, not automatic proof of an error.
    """
    pairs = []

    for i, left in enumerate(entities):
        left_key = entity_similarity_key(left)
        if not left_key:
            continue

        for right in entities[i + 1:]:
            right_key = entity_similarity_key(right)
            if not right_key or left_key == right_key:
                continue

            if roman_variant_pair(left, right):
                continue

            left_tokens = set(left_key.split())
            right_tokens = set(right_key.split())
            token_overlap = (
                len(left_tokens & right_tokens)
                / max(1, min(len(left_tokens), len(right_tokens)))
            )
            ratio = SequenceMatcher(
                None,
                left_key,
                right_key,
            ).ratio()

            if ratio >= threshold and token_overlap >= 0.60:
                pairs.append({
                    "left": left,
                    "right": right,
                    "similarity": ratio,
                })

    # Remove mirrored or duplicate pair representations.
    unique = []
    seen = set()
    for item in sorted(
        pairs,
        key=lambda x: x["similarity"],
        reverse=True,
    ):
        key = tuple(sorted([
            item["left"].casefold(),
            item["right"].casefold(),
        ]))
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)

    return unique

def looks_like_entity_phrase(value):
    value = clean_entity_candidate(value)
    if not value:
        return False

    low = value.casefold()

    if low in GENERIC_ENTITY_HEADINGS:
        return False

    if any(term in low for term in [
        "find an agent",
        "leave a reply",
        "frequently asked",
        "faq",
        "rent apartment",
        "rent apartments",
        "rent villa",
        "rent villas",
        "where can you",
        "where to rent",
        "click here",
        "read more",
        "want to",
    ]):
        return False

    words = tokenize(value)
    if not (1 <= len(words) <= 7):
        return False

    # Reject sentence fragments and calls to action.
    if value.endswith(("?", "!", ".")):
        return False

    # Reject phrases that are mostly generic SEO/action terms.
    generic_tokens = {
        "rent", "rental", "renting", "apartment", "apartments", "villa", "villas",
        "property", "properties", "find", "agent", "faq", "faqs", "want",
        "best", "popular", "places", "where", "can", "you",
    }
    meaningful = [w.lower() for w in words if w.lower() not in generic_tokens]
    if len(meaningful) == 0:
        return False

    # Prefer proper noun style or known entity suffixes.
    title_case_words = sum(
        1 for token in value.split()
        if token[:1].isupper() or token.isupper()
    )

    entity_suffixes = {
        "residence", "residences", "tower", "towers", "villas", "villa",
        "heights", "gardens", "estate", "estates", "city", "community",
        "school", "academy", "hospital", "clinic", "mall", "hotel",
        "park", "course", "stadium", "centre", "center",
    }

    has_entity_suffix = any(w.lower().strip(".,") in entity_suffixes for w in value.split())

    return title_case_words >= max(1, len(value.split()) // 2) or has_entity_suffix


def entity_heading_context_relevant(heading_text, section_text, target_topic):
    """
    Named projects, buildings and places can be valid headings without
    repeating the Focus Keyword.

    Accept an entity heading when the section beneath it has a meaningful
    relationship to the page topic.
    """
    if not looks_like_entity_phrase(heading_text):
        return False

    if not section_text:
        return False

    section_score = semantic_overlap(target_topic, section_text)
    lexical_score = keyword_overlap(target_topic, section_text)

    target_concepts = set(semantic_tokens(target_topic))
    section_concepts = set(semantic_tokens(section_text))

    important_topic_concepts = {
        "rent", "sale", "property", "price", "location"
    }
    shared_important = (
        target_concepts
        & section_concepts
        & important_topic_concepts
    )

    return (
        section_score >= 0.30
        or lexical_score >= 0.12
        or (
            bool(shared_important)
            and section_score >= 0.20
        )
    )

def entity_candidates(article_soup, limit=20):
    values = []

    # 1. Headings are strong entity candidates when they look like proper nouns.
    for heading in article_soup.find_all(re.compile(r"^h[2-4]$")):
        value = clean_entity_candidate(
            heading.get_text(" ", strip=True)
        )
        if looks_like_entity_phrase(value):
            values.append(value)

    # 2. Anchor text inside the article is often a cleaner signal for named places/projects.
    for anchor in article_soup.find_all("a", href=True):
        value = clean_entity_candidate(
            anchor.get_text(" ", strip=True)
        )
        if looks_like_entity_phrase(value):
            values.append(value)

    # 3. Conservative proper noun phrase extraction from prose.
    text_value = clean_text(article_soup)
    for match in re.findall(
        r"\b(?:[A-Z][A-Za-z0-9'&.-]+(?:\s+|$)){2,5}",
        text_value,
    ):
        value = clean_entity_candidate(match)
        if looks_like_entity_phrase(value):
            values.append(value)

    clean_values = []
    seen = set()

    for value in values:
        value = clean_entity_candidate(value)
        key = value.casefold()

        if key in seen:
            continue
        seen.add(key)

        # Avoid article title / focus keyword style headings being mistaken for entities.
        if len(tokenize(value)) >= 6 and any(
            token in key
            for token in ["rent", "apartments", "villas", "properties"]
        ):
            continue

        clean_values.append(value)

        if len(clean_values) >= limit:
            break

    return clean_values

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

    hidden_text_items = hidden_text_details(soup)

    if hidden_text_items:
        hidden_text_statuses = [x["status"] for x in hidden_text_items]
        hidden_text_status = FAIL if FAIL in hidden_text_statuses else REVIEW if REVIEW in hidden_text_statuses else PASS

        text_details = []
        for index, item in enumerate(hidden_text_items[:6], 1):
            text_details.append(
                f"Hidden text {index}. "
                f"Purpose: {item['purpose']}. "
                f"Hidden Because: {item['hidden_because']}. "
                f"Element: {item['hidden_element']}. "
                f"Example Text: {item['text']}. "
                f"Assessment: {item['explanation']}"
            )

        if hidden_text_status == PASS:
            text_summary = "Hidden text was detected, but every detected block had a recognised legitimate hiding reason. "
        elif hidden_text_status == REVIEW:
            text_summary = "Hidden text was detected and at least one block has an unconfirmed hiding reason. "
        else:
            text_summary = "Hidden text was detected and at least one block uses a strongly concealed method without a recognised legitimate reason. "

        rows.append(result(
            "Hidden Text",
            hidden_text_status,
            text_summary + " ".join(text_details),
            rules["Hidden Text"]
        ))
    else:
        rows.append(result(
            "Hidden Text",
            PASS,
            "No substantial visually hidden text blocks were detected by the static hiding checks.",
            rules["Hidden Text"]
        ))

    hidden_links, hidden_inventory = hidden_link_details(soup, desktop_r.url)

    if hidden_links:
        statuses = [item["status"] for item in hidden_links]
        hidden_status = FAIL if FAIL in statuses else REVIEW if REVIEW in statuses else PASS

        detail_lines = []
        for index, item in enumerate(hidden_links[:10], 1):
            viewport_note = ""
            if "desktop_hidden" in item:
                viewport_note = (
                    f" Desktop Hidden: {'Yes' if item['desktop_hidden'] else 'No'}. "
                    f"Mobile Hidden: {'Yes' if item['mobile_hidden'] else 'No'}."
                )

            controller_note = ""
            if item.get("controllers"):
                controller_text = "; ".join(
                    f"{c.get('tag', 'control')} {c.get('text', '')} aria expanded {c.get('ariaExpanded', '')}"
                    for c in item["controllers"][:3]
                )
                controller_note = f" Interface Controller: {controller_text}."

            detail_lines.append(
                f"Link {index}. "
                f"Status: {item['status']}. "
                f"URL: {item['url']}. "
                f"Anchor Text: {item['anchor_text']}. "
                f"Hidden Element: {item['hidden_element']}. "
                f"Hidden Because: {item['hidden_because']}. "
                f"Detected Purpose: {item['purpose']}. "
                f"Reason Assessment: {item['explanation']}."
                f"{viewport_note}"
                f"{controller_note}"
            )

        extra = ""
        if len(hidden_links) > 10:
            extra = f" Additional hidden links not shown: {len(hidden_links) - 10}."

        if hidden_status == PASS:
            summary = (
                f"Found {len(hidden_links)} hidden link{'s' if len(hidden_links) != 1 else ''}. "
                "Every detected hidden link had a recognised legitimate interface, responsive or accessibility reason. "
            )
        elif hidden_status == REVIEW:
            summary = (
                f"Found {len(hidden_links)} hidden link{'s' if len(hidden_links) != 1 else ''}. "
                "At least one link has an unconfirmed hiding reason and needs review. "
            )
        else:
            summary = (
                f"Found {len(hidden_links)} hidden link{'s' if len(hidden_links) != 1 else ''}. "
                "At least one link uses a strongly concealed method without a recognised legitimate interface reason. "
            )

        if not hidden_inventory.get("available"):
            summary += (
                "Rendered browser inspection was unavailable, so the system used the static HTML fallback. "
                f"Browser inspection note: {hidden_inventory.get('error', 'not available')}. "
            )

        rows.append(result(
            "Hidden Links",
            hidden_status,
            summary + " ".join(detail_lines) + extra,
            rules["Hidden Links"]
        ))
    else:
        browser_note = ""
        if not hidden_inventory.get("available"):
            browser_note = (
                " Rendered browser inspection was unavailable, so the result used the static HTML fallback. "
                f"Browser inspection note: {hidden_inventory.get('error', 'not available')}."
            )

        rows.append(result(
            "Hidden Links",
            PASS,
            "No visually hidden links were detected by the available checks." + browser_note,
            rules["Hidden Links"]
        ))

    title_for_kw = title_text(soup)
    h1_for_kw = first_h1(soup)
    kw_assessment = keyword_repetition_assessment(
        body_text,
        focus_keyword,
        secondary_keywords,
        title=title_for_kw,
        h1=h1_for_kw,
        url=url,
    )
    target_note = ""
    if kw_assessment["targets"]:
        target_note = " Target phrases: " + "; ".join(
            f"{kw}: {exact} exact use(s), {per_1000:.1f} per 1,000 words"
            for kw, exact, per_1000 in kw_assessment["targets"][:12]
        ) + "."
    rows.append(
        result(
            "Keyword Stuffing",
            kw_assessment["status"],
            f"Most repeated two word phrase: '{kw_assessment['gram']}' with {kw_assessment['count']} uses "
            f"({kw_assessment['density']:.1%} of two word phrases). "
            f"{kw_assessment['reason']}{target_note}",
            rules["Keyword Stuffing"],
        )
    )

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

def audit_seo(url, desktop_r, desktop_elapsed, mobile_r, soup, body_text, focus_keyword="", secondary_keywords=None, sitemap_result=None, external_validation=None, resource_validation=None):
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

    # Google does not publish a fixed Title Tag character limit.
    # Length is treated only as an internal quality signal.
    if not title:
        ts = FAIL
        title_reason = "Title is missing."
    else:
        ts = PASS
        title_reason_parts = []

        # Topic relevance between the title and the actual article body.
        title_body_overlap = keyword_overlap(title, body_text)

        # Focus Keyword representation.
        focus_exact = keyword_in_text(focus_keyword, title) if focus_keyword else True
        focus_overlap = keyword_overlap(focus_keyword, title) if focus_keyword else 1.0
        focus_represented = focus_exact or focus_overlap >= 0.60

        # Detect obvious repetition inside the Title Tag.
        title_words = [
            w for w in tokenize(title)
            if len(w) > 2 and w not in {
                "the", "and", "for", "with", "from", "this", "that", "your", "you",
                "are", "our", "in", "on", "of", "to", "a", "an", "is",
                "في", "من", "على", "إلى", "الى", "عن", "هذا", "هذه", "مع", "و", "أو", "او"
            }
        ]
        title_word_counts = Counter(title_words)
        repeated_title_terms = [
            word for word, count in title_word_counts.items()
            if count >= 3
        ]

        # Length logic.
        if title_len > 80:
            ts = REVIEW
            title_reason_parts.append(
                f"The title contains {title_len} characters and may be more verbose than necessary."
            )
        elif title_len < 30:
            # A short title is only reviewed if it also has weak topic coverage.
            if title_body_overlap < 0.55:
                ts = REVIEW
                title_reason_parts.append(
                    f"The title contains {title_len} characters and has weak topic coverage."
                )
            else:
                title_reason_parts.append(
                    f"The title contains {title_len} characters but still represents the page topic clearly."
                )
        elif 71 <= title_len <= 80:
            title_reason_parts.append(
                f"The title contains {title_len} characters. Length alone does not trigger REVIEW."
            )
        else:
            title_reason_parts.append(
                f"The title contains {title_len} characters and is within the system's concise internal range."
            )

        # Relevance logic.
        if title_body_overlap < 0.35:
            ts = REVIEW
            title_reason_parts.append(
                f"Title to article topic overlap is only {title_body_overlap:.0%}."
            )
        else:
            title_reason_parts.append(
                f"Title to article topic overlap is {title_body_overlap:.0%}."
            )

        # Focus Keyword logic uses exact or semantic term overlap.
        if focus_keyword:
            if not focus_represented:
                ts = REVIEW
                title_reason_parts.append(
                    f"The Focus Keyword meaning is weakly represented in the title. Term overlap is {focus_overlap:.0%}."
                )
            elif focus_exact:
                title_reason_parts.append(
                    f"The Focus Keyword is directly represented in the title."
                )
            else:
                title_reason_parts.append(
                    f"The Focus Keyword is represented semantically. Term overlap is {focus_overlap:.0%}."
                )

        # Obvious repetition inside the title.
        if repeated_title_terms:
            ts = REVIEW
            title_reason_parts.append(
                "Repeated title terms detected: " + ", ".join(repeated_title_terms[:6]) + "."
            )

        title_reason = " ".join(title_reason_parts)

    rows.append(
        result(
            "Title Tag",
            ts,
            f"Title: {title or 'missing'}. {title_reason}",
            rules["Title Tag"]
        )
    )

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

    h1s = page_h1s(soup)

    if len(h1s) == 0:
        h1_status = FAIL
        h1_finding = "No H1 was found on the page."
    else:
        h1_text = h1s[0]
        h1_status = PASS if len(h1s) == 1 else REVIEW

        if focus_keyword:
            h1_exact = phrase_count(h1_text, focus_keyword) > 0
            h1_semantic = semantic_overlap(focus_keyword, h1_text)
            h1_page_topic = semantic_overlap(h1_text, body_text)

            if h1_exact:
                relation_note = "The Focus Keyword is directly represented."
            elif h1_semantic >= 0.60:
                relation_note = f"The Focus Keyword meaning is represented semantically at {h1_semantic:.0%} concept overlap."
            elif h1_page_topic >= 0.60:
                relation_note = (
                    f"Exact Focus Keyword wording is not present, but the H1 strongly represents the article topic "
                    f"at {h1_page_topic:.0%} concept overlap."
                )
            else:
                h1_status = REVIEW
                relation_note = (
                    f"The H1 has weak semantic representation of the Focus Keyword "
                    f"({h1_semantic:.0%}) and the article topic ({h1_page_topic:.0%})."
                )
        else:
            h1_page_topic = semantic_overlap(h1_text, body_text)
            if h1_page_topic < 0.45:
                h1_status = REVIEW
            relation_note = f"H1 to article semantic concept overlap is {h1_page_topic:.0%}."

        count_note = (
            "One H1 was found."
            if len(h1s) == 1
            else f"{len(h1s)} H1 elements were found, so the structure should be reviewed."
        )
        h1_finding = f"{count_note} H1: {h1_text}. {relation_note}"

    rows.append(result("H1", h1_status, h1_finding, rules["H1"]))

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

    internal, external = extract_page_links(soup, desktop_r.url)
    rows.append(
        result(
            "Internal Links",
            PASS if internal else REVIEW,
            f"{len(internal)} unique crawlable HTTP(S) internal links found.",
            rules["Internal Links"],
        )
    )

    if external_validation is None:
        external_validation = validate_url_set(
            external,
            timeout=LINK_CHECK_TIMEOUT,
            workers=LINK_CHECK_WORKERS,
        )

    external_classified = classify_link_validation(external_validation)
    external_problem_items = (
        external_classified["broken"]
        + external_classified["server_errors"]
        + external_classified["restricted"]
        + external_classified["unreachable"]
    )

    if not external:
        external_status = PASS
        external_finding = "No external HTTP links were found."
    elif external_problem_items:
        external_status = REVIEW
        external_problems = validation_problem_examples(
            {
                "broken": external_classified["broken"],
                "server_errors": external_classified["server_errors"],
                "restricted": external_classified["restricted"],
                "unreachable": external_classified["unreachable"],
            }
        )
        external_finding = (
            f"{len(external_classified['checked'])} unique external links were requested. "
            f"{len(external_classified['working'])} resolved successfully. "
            f"{len(external_classified['expected_platform'])} social platform link(s) returned expected automated access restrictions and were not treated as broken. "
            f"Problems requiring review: " + "; ".join(external_problems) + "."
        )
    else:
        external_status = PASS
        external_finding = (
            f"{len(external_classified['checked'])} unique external HTTP links were requested. "
            f"{len(external_classified['working'])} resolved directly. "
            f"{len(external_classified['expected_platform'])} social platform link(s) returned expected login or anti-bot responses and were not treated as broken. "
            f"{len(external_classified['redirected'])} redirected to a working final destination."
        )

    rows.append(
        result(
            "External Links",
            external_status,
            external_finding,
            rules["External Links"],
        )
    )

    imgs = soup.find_all("img")
    no_alt = [i for i in imgs if i.get("alt") is None]
    image_status = REVIEW if imgs and len(no_alt)/len(imgs) > .35 else PASS
    rows.append(result("Images", image_status, f"{len(imgs)} images; {len(no_alt)} missing alt attribute.", rules["Images"]))

    jsonld, json_errors = parse_jsonld(soup)
    headlines = [
        str(value)
        for value in get_schema_values(jsonld, "headline")
        if isinstance(value, (str, int, float))
    ]

    visible_title = title_text(soup)
    visible_h1 = page_primary_h1(soup)
    headline_scores = [
        max(
            semantic_overlap(headline, visible_title),
            semantic_overlap(headline, visible_h1),
            keyword_overlap(headline, visible_title),
            keyword_overlap(headline, visible_h1),
        )
        for headline in headlines
    ] if headlines else []

    if json_errors:
        sd = REVIEW
        schema_finding = f"{len(jsonld)} valid JSON LD block(s) and {json_errors} parse error(s)."
    elif not jsonld:
        sd = REVIEW
        schema_finding = "No valid JSON LD block was found."
    elif headlines and max(headline_scores or [0]) < 0.45:
        sd = REVIEW
        schema_finding = (
            f"{len(jsonld)} valid JSON LD block(s) found, but schema headline has weak agreement with the visible title and H1. "
            f"Schema headline example: {headlines[0]}."
        )
    else:
        sd = PASS
        schema_finding = (
            f"{len(jsonld)} valid JSON LD block(s); {json_errors} parse error(s)."
        )
        if headlines:
            schema_finding += (
                f" Schema headline is consistent with the visible page at "
                f"{max(headline_scores):.0%} semantic or lexical agreement."
            )

    rows.append(result("Structured Data", sd, schema_finding, rules["Structured Data"]))

    published = [
        str(value)
        for value in get_schema_values(jsonld, "datePublished")
        if isinstance(value, (str, int, float))
    ]
    modified = [
        str(value)
        for value in get_schema_values(jsonld, "dateModified")
        if isinstance(value, (str, int, float))
    ]
    visible_dates = visible_date_signals(soup)

    published_status = PASS if published else REVIEW
    published_notes = [
        f"Schema datePublished: {published[:3] if published else 'not found'}."
    ]
    if visible_dates["published"]:
        published_notes.append(
            f"Visible or metadata published dates: {visible_dates['published'][:3]}."
        )
        if published:
            diffs = [
                datetime_difference_hours(published[0], value)
                for value in visible_dates["published"]
            ]
            diffs = [d for d in diffs if d is not None]
            if diffs and min(diffs) > 24:
                published_status = REVIEW
                published_notes.append("Publication date signals differ by more than 24 hours.")

    rows.append(
        result(
            "datePublished",
            published_status,
            " ".join(published_notes),
            rules["datePublished"],
        )
    )

    modified_status = PASS if modified else REVIEW
    modified_notes = [
        f"Schema dateModified: {modified[:3] if modified else 'not found'}."
    ]

    if visible_dates["modified"]:
        modified_notes.append(
            f"Visible or metadata modified dates: {visible_dates['modified'][:3]}."
        )

    sitemap_lastmod = sitemap_result.get("lastmod") if sitemap_result else ""
    if sitemap_lastmod:
        modified_notes.append(f"Sitemap lastmod: {sitemap_lastmod}.")
        if modified:
            diff = datetime_difference_hours(modified[0], sitemap_lastmod)
            if diff is not None and diff > 24:
                modified_status = REVIEW
                modified_notes.append("Schema dateModified and sitemap lastmod differ by more than 24 hours.")

    http_last_modified = desktop_r.headers.get("Last-Modified") or desktop_r.headers.get("last-modified")
    if http_last_modified:
        modified_notes.append(f"HTTP Last Modified: {http_last_modified}.")
        if modified:
            diff = datetime_difference_hours(modified[0], http_last_modified)
            if diff is not None and diff > 24:
                modified_status = REVIEW
                modified_notes.append(
                    "HTTP Last Modified differs materially from the editorial modification date. This is a technical freshness inconsistency, not a spam violation."
                )

    if visible_dates["modified"] and modified:
        diffs = [
            datetime_difference_hours(modified[0], value)
            for value in visible_dates["modified"]
        ]
        diffs = [d for d in diffs if d is not None]
        if diffs and min(diffs) > 24:
            modified_status = REVIEW
            modified_notes.append("Visible modified date and schema dateModified differ by more than 24 hours.")

    rows.append(
        result(
            "dateModified",
            modified_status,
            " ".join(modified_notes),
            rules["dateModified"],
        )
    )

    if sitemap_result is None:
        sitemap_result = find_url_in_sitemaps(desktop_r.url)

    if sitemap_result["found"]:
        ss = PASS
        sf = (
            f"Preferred URL found in sitemap: {sitemap_result['found_in']}. "
            f"Sitemap files checked: {len(sitemap_result['checked'])}. "
            f"Child sitemap references discovered: {sitemap_result['child_count']}. "
            f"Sitemap stage time: {sitemap_result.get('elapsed', 0):.1f} seconds."
        )
        if sitemap_result.get("lastmod"):
            sf += f" Sitemap lastmod: {sitemap_result['lastmod']}."
    elif sitemap_result["accessible"] > 0 and sitemap_result["complete"]:
        ss = REVIEW
        sf = (
            f"Accessible sitemap files were fully inspected but the preferred URL was not found. "
            f"Sitemap files checked: {len(sitemap_result['checked'])}. "
            f"Child sitemap references discovered: {sitemap_result['child_count']}."
        )
    elif sitemap_result["accessible"] > 0:
        ss = REVIEW
        if sitemap_result.get("stopped_by_budget"):
            stop_reason = f"the {SITEMAP_TIME_BUDGET} second sitemap time budget was reached"
        elif sitemap_result.get("stopped_by_limit"):
            stop_reason = f"the {SITEMAP_MAX_FILES} sitemap file audit limit was reached"
        else:
            stop_reason = "the sitemap inspection could not process every discovered file"

        sf = (
            f"Sitemap inspection was incomplete because {stop_reason}. "
            f"Sitemap files checked: {len(sitemap_result['checked'])}. "
            f"Child sitemap references discovered: {sitemap_result['child_count']}. "
            f"Sitemap stage time: {sitemap_result.get('elapsed', 0):.1f} seconds."
        )
    else:
        ss = REVIEW
        sf = (
            f"No accessible XML sitemap could be confirmed from robots.txt or the common sitemap locations. "
            f"Endpoints attempted: {len(sitemap_result['checked'])}."
        )

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

    resource_urls = extract_resource_urls(soup, desktop_r.url)
    if resource_validation is None:
        resource_validation = validate_url_set(
            resource_urls,
            timeout=RESOURCE_CHECK_TIMEOUT,
            workers=RESOURCE_CHECK_WORKERS,
        )

    resource_problems = validation_problem_examples(resource_validation)
    if not resource_urls:
        resource_status = REVIEW
        resource_finding = "No external image, stylesheet or JavaScript resource URLs were discovered."
    elif resource_problems:
        resource_status = REVIEW
        resource_finding = (
            f"{len(resource_validation['checked'])} unique resource URLs were requested. "
            f"{len(resource_validation['working'])} resolved successfully. "
            f"Problems: " + "; ".join(resource_problems) + "."
        )
    else:
        resource_status = PASS
        resource_finding = (
            f"All {len(resource_validation['checked'])} unique image, stylesheet and JavaScript resource URLs were requested and resolved successfully."
        )

    rows.append(
        result(
            "Broken Resources",
            resource_status,
            resource_finding,
            rules["Broken Resources"],
        )
    )

    return rows

# -----------------------------
# Content audit
# -----------------------------

def audit_content(url, soup, body_text, focus_keyword="", secondary_keywords=None):
    rows = []
    rules = dict(CONTENT_RULES)
    secondary_keywords = secondary_keywords or []

    # All Content QA rules use the isolated editorial article body.
    article_soup = main_content_node(soup)
    body_text = clean_text(article_soup)

    title = title_text(soup)
    h1 = page_primary_h1(soup)
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

    content_sections = heading_sections(article_soup)
    headings = [item["heading"] for item in content_sections]

    weak_sections = []
    for item in content_sections:
        heading_score = semantic_overlap(target_topic, item["heading"])
        section_score = semantic_overlap(target_topic, item["section"]) if item["section"] else 0.0

        if is_faq_heading(item["heading"]):
            if not faq_section_relevant(item["section"], target_topic):
                weak_sections.append(item["heading"])
            continue

        if entity_heading_context_relevant(
            item["heading"],
            item["section"],
            target_topic,
        ):
            continue

        if heading_score < 0.20 and section_score < 0.35:
            weak_sections.append(item["heading"])

    if content_sections:
        weak_share = len(weak_sections) / len(content_sections)
        rel_status = FAIL if weak_share > 0.65 else REVIEW if weak_share > 0.45 else PASS
        rel_finding = (
            f"{len(weak_sections)} of {len(content_sections)} H2 to H4 sections remain weakly related after checking both heading meaning and section context."
        )
        if weak_sections:
            rel_finding += " Weak sections: " + "; ".join(weak_sections[:6]) + "."
    else:
        rel_status = PASS
        rel_finding = "No H2 to H4 sections were available for section level relevance analysis."

    rows.append(result("Content Relevance", rel_status, rel_finding, rules["Content Relevance"]))

    thin_status = PASS if wc >= 600 else REVIEW if wc >= 300 else FAIL
    rows.append(result("Thin Content", thin_status, f"{wc:,} extracted meaningful words.", rules["Thin Content"]))

    value_signals = {
        "tables": len(article_soup.find_all("table")),
        "lists": len(article_soup.find_all(["ul","ol"])),
        "numbers": len(re.findall(r"\b\d+(?:[.,]\d+)?%?\b", body_text)),
    }
    if wc >= 800 and (value_signals["tables"] or value_signals["numbers"] >= 12 or value_signals["lists"] >= 3):
        ov = PASS
        of = f"Useful-value signals detected: {value_signals['tables']} table(s), {value_signals['lists']} list(s), {value_signals['numbers']} numeric references."
    else:
        ov = REVIEW
        of = "Original value cannot be confirmed from one URL alone; compare against competing/site content. " + f"Signals: {value_signals}."
    rows.append(result("Original Value", ov, of, rules["Original Value"]))

    claim_examples = factual_claim_examples(article_soup, url)
    if claim_examples:
        claims_with_links = sum(1 for item in claim_examples if item["source_links"])
        factual_status = REVIEW
        factual_finding = (
            f"{len(claim_examples)} factual or numeric claim example(s) were extracted from the isolated article body. "
            f"{claims_with_links} sampled claim(s) contain a visible HTTP source link in the same content block. "
            "External or first party verification is still required before confirming factual accuracy. "
            "Examples: "
            + " | ".join(item["claim"] for item in claim_examples[:4])
        )
    else:
        factual_status = PASS
        factual_finding = (
            "No high confidence factual or numeric claim examples were extracted that require separate source verification."
        )

    rows.append(
        result(
            "Factual Accuracy",
            factual_status,
            factual_finding,
            rules["Factual Accuracy"],
        )
    )

    year_contexts = contextual_old_years(body_text)
    risky_years = [item for item in year_contexts if item["sensitive"]]
    uncertain_years = [
        item for item in year_contexts
        if not item["sensitive"] and item["classification"] == "Context needs review"
    ]

    if risky_years:
        od = REVIEW
        examples = " | ".join(
            f"{item['year']}: {item['sentence']}"
            for item in risky_years[:5]
        )
        odf = (
            f"{len(risky_years)} old year reference(s) occur inside time sensitive claims in the isolated article body. "
            f"Examples: {examples}"
        )
    elif uncertain_years:
        od = REVIEW
        examples = " | ".join(
            f"{item['year']}: {item['sentence']}"
            for item in uncertain_years[:4]
        )
        odf = (
            f"Old year references were found in the isolated article body, but their purpose is not clearly historical or time sensitive. "
            f"Review these contexts: {examples}"
        )
    elif year_contexts:
        od = PASS
        examples = " | ".join(
            f"{item['year']}: {item['sentence']}"
            for item in year_contexts[:4]
        )
        odf = (
            f"Old year references were found, but they appear contextual or historical rather than stale current claims. "
            f"Examples: {examples}"
        )
    else:
        od = PASS
        odf = "No old year references were found inside the isolated article body."

    rows.append(result("Outdated Information", od, odf, rules["Outdated Information"]))

    kw_assessment = keyword_repetition_assessment(
        body_text,
        focus_keyword,
        secondary_keywords,
        title=title,
        h1=h1,
        url=url,
    )

    semantic_note = ""
    if focus_keyword:
        focus_semantic = semantic_overlap(focus_keyword, body_text)
        semantic_note = f" Focus Keyword concept coverage in the article is {focus_semantic:.0%}."

    target_note = ""
    if kw_assessment["targets"]:
        target_note = " Target phrase use: " + "; ".join(
            f"{kw}: {exact} exact use(s), {per_1000:.1f} per 1,000 words"
            for kw, exact, per_1000 in kw_assessment["targets"][:12]
        ) + "."

    rows.append(
        result(
            "Keyword Use",
            kw_assessment["status"],
            f"Most repeated two word phrase: '{kw_assessment['gram']}' with {kw_assessment['count']} uses "
            f"({kw_assessment['density']:.1%}). {kw_assessment['reason']}"
            f"{semantic_note}{target_note}",
            rules["Keyword Use"],
        )
    )

    sent_ratio, repeated_sents = repeated_sentence_ratio(body_text)
    para_ratio, repeated_paras = repeated_paragraph_ratio(article_soup)
    rep = max(sent_ratio, para_ratio)
    if rep >= .10:
        rp = FAIL
    elif rep >= .04:
        rp = REVIEW
    else:
        rp = PASS
    rows.append(result("Repetition", rp, f"Estimated duplicate sentence/paragraph ratio: {rep:.1%}.", rules["Repetition"]))

    paragraphs = [p.get_text(" ", strip=True) for p in article_soup.find_all("p") if len(p.get_text(" ", strip=True)) >= 60]
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

    section_items = heading_sections(article_soup)

    if section_items:
        relevant = 0
        contextual = 0
        weak_examples = []
        detail_examples = []

        for item in section_items:
            heading_score = semantic_overlap(target_topic, item["heading"])
            section_score = semantic_overlap(target_topic, item["section"]) if item["section"] else 0.0

            # FAQ is a structural heading. Judge the FAQ content rather than the
            # literal heading word.
            if is_faq_heading(item["heading"]):
                is_relevant = faq_section_relevant(
                    item["section"],
                    target_topic,
                )
                relevance_reason = "FAQ section context"
            elif entity_heading_context_relevant(
                item["heading"],
                item["section"],
                target_topic,
            ):
                is_relevant = True
                relevance_reason = "entity heading with related section context"
            else:
                is_relevant = (
                    heading_score >= 0.20
                    or section_score >= 0.45
                )
                relevance_reason = "semantic heading or section overlap"

            if is_relevant:
                relevant += 1
                if heading_score < 0.20:
                    contextual += 1
                    if len(detail_examples) < 5:
                        detail_examples.append(
                            f"'{item['heading']}' accepted through {relevance_reason}; "
                            f"section topic overlap {section_score:.0%}."
                        )
            elif len(weak_examples) < 5:
                weak_examples.append(
                    f"'{item['heading']}' heading overlap {heading_score:.0%}, section overlap {section_score:.0%}"
                )

        hr = relevant / len(section_items)
        hstatus = PASS if hr >= 0.70 else REVIEW if hr >= 0.45 else FAIL

        hfind = (
            f"{relevant}/{len(section_items)} H2 to H4 sections are related to the main topic after semantic heading and section context analysis. "
            f"{contextual} section(s) were accepted through contextual section relevance even though the heading itself had low direct overlap."
        )
        if detail_examples:
            hfind += " Context examples: " + " ".join(detail_examples)
        if weak_examples:
            hfind += " Weakest sections: " + "; ".join(weak_examples) + "."
    else:
        hstatus = REVIEW
        hfind = "No H2 to H4 headings were available in the main content for contextual relevance assessment."

    rows.append(result("Heading Relevance", hstatus, hfind, rules["Heading Relevance"]))

    intro_words = " ".join(tokenize(body_text)[:140])
    intro_overlap = keyword_overlap(target_topic, intro_words)
    iq = PASS if intro_overlap >= .45 else REVIEW
    rows.append(result("Introduction Quality", iq, f"Opening 140-word topic overlap: {intro_overlap:.0%}.", rules["Introduction Quality"]))

    faq_headers = [h for h in headings if "faq" in h.lower() or "frequently asked" in h.lower() or "أسئلة" in h]
    questions = [x.get_text(" ", strip=True) for x in article_soup.find_all(["h2","h3","h4","strong"]) if x.get_text(" ", strip=True).endswith(("?","؟"))]
    if faq_headers or questions:
        fq = REVIEW if len(questions) and sum(len(tokenize(q)) < 3 for q in questions) > len(questions)/2 else PASS
        ff = f"FAQ-like content detected: {len(questions)} question heading(s)."
    else:
        fq = PASS
        ff = "No FAQ section detected; no FAQ quality issue to evaluate."
    rows.append(result("FAQ Quality", fq, ff, rules["FAQ Quality"]))

    super_terms = ["best", "cheapest", "most popular", "number one", "#1", "highest", "lowest", "أفضل", "الأرخص", "الأكثر شعبية"]
    hits = [x for x in super_terms if x.lower() in body_text.lower()]
    outbound_citations = len([a for a in article_soup.find_all("a", href=True) if urlparse(urljoin(url,a["href"])).netloc not in {"", urlparse(url).netloc}])
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

    entities = entity_candidates(article_soup)
    near_duplicates = near_duplicate_entities(entities)

    if entities:
        entity_status = REVIEW
        entity_finding = (
            f"{len(entities)} cleaned entity candidate(s) were extracted from the isolated article body and require external or first party verification. "
            f"Examples: {', '.join(entities[:10])}."
        )

        if near_duplicates:
            duplicate_text = " | ".join(
                f"{item['left']} vs {item['right']} "
                f"({item['similarity']:.0%} spelling similarity)"
                for item in near_duplicates[:5]
            )
            entity_finding += (
                " Possible near duplicate entity spellings were detected and should be checked for a typo or legitimate naming variation: "
                + duplicate_text
                + "."
            )
        else:
            entity_finding += (
                " No suspicious near duplicate entity spelling was detected inside the article."
            )
    else:
        entity_status = PASS
        entity_finding = (
            "No clear named entity candidates requiring separate verification were extracted."
        )

    rows.append(
        result(
            "Entity Accuracy",
            entity_status,
            entity_finding,
            rules["Entity Accuracy"],
        )
    )

    sentences = [s for s in re.split(r"[.!?؟]+", body_text) if len(tokenize(s)) >= 4]
    avg_len = sum(len(tokenize(s)) for s in sentences) / max(1, len(sentences))
    gr = REVIEW if avg_len > 35 else PASS
    rows.append(result("Grammar / Readability", gr, f"Average sentence length: {avg_len:.1f} words. This is a readability heuristic, not a grammar proof.", rules["Grammar / Readability"]))

    placeholders = [x for x in ["lorem ipsum", "todo", "tbd", "[insert", "placeholder", "coming soon"] if x in body_text.lower()]
    empty_heads = sum(1 for h in article_soup.find_all(re.compile(r"^h[1-6]$")) if not h.get_text(" ", strip=True))
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

# This placeholder is intentionally above the Rule Library so long audits
# always show visible progress instead of making the page appear frozen.
audit_status_slot = st.empty()

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
        audit_started = time.time()
        audit_status = audit_status_slot.status(
            "Running URL audit",
            expanded=True,
        )

        audit_status.write("1 of 4  Fetching Desktop, Mobile and Googlebot versions in parallel")
        (
            desktop_r,
            desktop_elapsed,
            mobile_r,
            mobile_elapsed,
            bot_r,
            bot_elapsed,
        ) = fetch_page_variants(url)

        soup = soup_of(desktop_r.text)
        body_text = main_content_text(soup)

        # Separate read trees for parallel workers.
        spam_soup = soup_of(desktop_r.text)
        content_soup = soup_of(desktop_r.text)

        audit_status.write(
            f"Page variants fetched in parallel. "
            f"Desktop {desktop_elapsed:.2f}s, Mobile {mobile_elapsed:.2f}s, Googlebot {bot_elapsed:.2f}s"
        )

        internal_urls, external_urls = extract_page_links(soup, desktop_r.url)
        resource_urls = extract_resource_urls(soup, desktop_r.url)

        audit_status.write(
            "2 of 4  Running Spam, Content, Sitemap, External Link and Resource checks in parallel"
        )

        parallel_results = {}
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {
                executor.submit(
                    audit_spam,
                    url,
                    desktop_r,
                    mobile_r,
                    bot_r,
                    spam_soup,
                    body_text,
                    focus_keyword,
                    secondary_keywords,
                ): "Spam",
                executor.submit(
                    audit_content,
                    url,
                    content_soup,
                    body_text,
                    focus_keyword,
                    secondary_keywords,
                ): "Content",
                executor.submit(
                    find_url_in_sitemaps,
                    desktop_r.url,
                    SITEMAP_MAX_FILES,
                    SITEMAP_MAX_DEPTH,
                ): "Sitemap",
                executor.submit(
                    validate_url_set,
                    external_urls,
                    LINK_CHECK_TIMEOUT,
                    LINK_CHECK_WORKERS,
                ): "External Links",
                executor.submit(
                    validate_url_set,
                    resource_urls,
                    RESOURCE_CHECK_TIMEOUT,
                    RESOURCE_CHECK_WORKERS,
                ): "Resources",
            }

            for future in as_completed(futures):
                label = futures[future]
                parallel_results[label] = future.result()

                if label == "Sitemap":
                    sitemap_stage = parallel_results[label]
                    audit_status.write(
                        f"Sitemap check completed in {sitemap_stage.get('elapsed', 0):.1f}s "
                        f"after checking {len(sitemap_stage.get('checked', []))} sitemap file(s)"
                    )
                elif label == "External Links":
                    audit_status.write(
                        f"External link validation completed for {len(parallel_results[label].get('checked', []))} link(s)"
                    )
                elif label == "Resources":
                    audit_status.write(
                        f"Resource validation completed for {len(parallel_results[label].get('checked', []))} resource(s)"
                    )
                else:
                    audit_status.write(f"{label} checks completed")

        spam_rows = parallel_results["Spam"]
        content_rows = parallel_results["Content"]
        sitemap_result = parallel_results["Sitemap"]
        external_validation = parallel_results["External Links"]
        resource_validation = parallel_results["Resources"]

        audit_status.write("3 of 4  Finalising SEO checks")
        seo_rows = audit_seo(
            url,
            desktop_r,
            desktop_elapsed,
            mobile_r,
            soup,
            body_text,
            focus_keyword,
            secondary_keywords,
            sitemap_result=sitemap_result,
            external_validation=external_validation,
            resource_validation=resource_validation,
        )

        total_audit_time = time.time() - audit_started
        audit_status.write("4 of 4  Preparing results")
        audit_status.update(
            label=f"Audit completed in {total_audit_time:.1f} seconds",
            state="complete",
            expanded=False,
        )

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
            f"{desktop_elapsed:.2f}s desktop response · {len(desktop_r.history)} redirects · "
            f"{total_audit_time:.1f}s total audit time"
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

                Hidden content inspection uses a rendered Chromium browser when Playwright and Chromium are available. If Chromium is unavailable, the system falls back to static HTML inspection.

                Network heavy checks are parallelised and cached. Sitemap inspection has a strict time and file budget so it cannot hold the interface indefinitely.

                Content QA uses an isolated editorial article body and excludes comments, related posts, popular widgets, sidebars, navigation and other page chrome before calculating content results.

                External links and linked image, stylesheet and JavaScript resources are now requested directly instead of receiving PASS from discovery alone.
                """
            )

    except requests.exceptions.RequestException as e:
        if "audit_status" in locals():
            audit_status.update(
                label="Audit stopped because the URL request failed",
                state="error",
                expanded=True,
            )
        st.error(f"Could not fetch the URL: {e}")
    except Exception as e:
        if "audit_status" in locals():
            audit_status.update(
                label="Audit stopped because a check returned an error",
                state="error",
                expanded=True,
            )
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
