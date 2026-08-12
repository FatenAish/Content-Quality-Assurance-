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
import urllib.robotparser
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

APP_VERSION = "V18.14 FACTUAL ACCURACY NON MARKET ONLY"
ENGINE_BUILD = "2026.08.12.18"
CURRENT_YEAR = 2026

# Performance controls
PAGE_FETCH_TIMEOUT = 9
SITEMAP_REQUEST_TIMEOUT = 4
SITEMAP_MAX_FILES = 36
SITEMAP_MAX_DEPTH = 3
SITEMAP_WORKERS = 8
SITEMAP_TIME_BUDGET = 12
PLAYWRIGHT_NAV_TIMEOUT = 12000
PLAYWRIGHT_SETTLE_MS = 450

LINK_CHECK_TIMEOUT = 3
LINK_CHECK_WORKERS = 16
INTERNAL_LINK_CHECK_TIMEOUT = 5
INTERNAL_LINK_CHECK_WORKERS = 24
ROBOTS_REQUEST_TIMEOUT = 4
RESOURCE_CHECK_TIMEOUT = 3
RESOURCE_CHECK_WORKERS = 24

st.set_page_config(
    page_title=f"Bayut URL Quality Auditor {APP_VERSION}",
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
    .version-chip {{
        display:inline-flex;
        align-items:center;
        gap:6px;
        padding:5px 9px;
        border-radius:999px;
        background:#E9F8F1;
        border:1px solid #CDEEE0;
        color:#087A52;
        font-size:12px;
        font-weight:800;
        letter-spacing:.02em;
        white-space:nowrap;
    }}
    .engine-proof {{
        margin-top:10px;
        padding:10px 12px;
        border:1px solid #DCEBE4;
        border-radius:12px;
        background:#F8FCFA;
        font-size:12px;
        line-height:1.45;
        color:#44524B;
    }}
    .engine-proof strong {{
        color:#087A52;
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
    ("Hidden Links", "FAIL when the fetched HTML contains an empty hyperlink or a link hidden by HTML/CSS. Every actual <a href> occurrence is counted separately, even when several links point to the same URL. Self references to the current article are ignored."),
    ("Link Spam", "FAIL when links are clearly created or inserted primarily to manipulate rankings."),
    ("Hacked Content", "FAIL when unauthorized spam text, pages, links or redirects are injected."),
    ("Spam JavaScript", "FAIL when scripts inject spam content, hidden links or deceptive redirects."),
    ("Spam Iframes", "FAIL when unauthorized or suspicious iframes introduce deceptive or spam content."),
    ("User Generated Spam", "FAIL when comments/profiles/UGC contain mass spam or manipulative links."),
    ("Back Button Hijacking", "FAIL when scripts manipulate browser history to prevent users from returning to the previous page."),
    ("Malware / Scam Behaviour", "FAIL when malicious downloads, harmful scripts, impersonation or deliberately deceptive functionality is detected."),
]

SEO_RULES = [
    ("HTTP Status", "PASS when the canonical live article returns HTTP 200."),
    ("Indexability", "FAIL when an intended indexable article contains noindex."),
    ("Robots", "Check both page level robots directives and robots.txt crawler access. FAIL when Googlebot is blocked from an intended crawlable article. REVIEW when crawler access cannot be reliably verified."),
    ("Canonical", "PASS when a valid canonical points to the correct preferred URL."),
    ("Title Tag", "Google does not define a fixed character limit. PASS when the title exists, clearly describes the page, represents the Focus Keyword or its meaning, and is not repetitive or stuffed. Length is an internal quality signal only. Titles from 30 to 70 characters are generally concise. Titles from 71 to 80 characters do not receive REVIEW from length alone. Titles above 80 characters receive REVIEW for possible verbosity. Very short titles receive REVIEW only when they are too vague or weakly related to the page."),
    ("Meta Description", "PASS when a useful and relevant meta description exists. Exact Focus Keyword wording and a fixed character count are not required. REVIEW missing, extremely weak, unusually verbose or poorly related descriptions."),
    ("H1", "PASS when one clear H1 exists and it represents the Focus Keyword meaning or the page topic. Exact phrase matching is not required. REVIEW multiple H1 elements or a weak semantic relationship. FAIL when the H1 is missing or clearly unrelated."),
    ("Heading Structure", "Evaluate the editorial heading hierarchy rather than navigation or sidebar headings. REVIEW empty headings, heavy duplication or clear heading level jumps."),
    ("URL Structure", "REVIEW when the URL is malformed, misleading, or dominated by unnecessary parameters."),
    ("Keyword Stuffing", "Analyse editorial article text only. Exclude embedded widgets and interface content. PASS when keyword use is natural. REVIEW when query phrases are unusually repetitive. FAIL when repetition is clearly excessive and manipulative."),
    ("Internal Links", "Inspect only real inline editorial hyperlinks inside paragraph, list and table text in the isolated article body. Exclude banners, property cards, Find An Agent CTA, image links, social sharing, broker modules, widgets, navigation and other non-editorial modules. Flag only external links, GET-confirmed HTTP 404/410 internal links, generic or spammy anchors, or anchors that appear poorly matched to the linked page. Timeouts, connection failures, temporary 5xx responses and HTTP 401/403/405/406/429 automated restrictions are not treated as broken."),
    ("External Links", "Request every discovered external HTTP link. Treat known social platform login, anti bot and restricted automated responses as expected platform behaviour rather than broken links. PASS when no confirmed broken destination is found. REVIEW confirmed 4xx or 5xx problems outside expected platform behaviour, unreachable URLs or unresolved restricted destinations."),
    ("Images", "Check meaningful images inside the article content. Result shows only the exact image URL when there is an issue such as empty alt text, missing alt attribute or a broken image resource. Decorative images do not require descriptive alt text. Known Bayut TruBroker promotional images, including English and Arabic variants, are excluded from this audit."),
    ("datePublished", "Compare schema datePublished with visible or page metadata publication dates when available. PASS when a valid publication date exists and no material inconsistency is detected. REVIEW missing or materially inconsistent publication dates."),
    ("Sitemap", "Follow sitemap indexes and prioritise editorial post or article sitemap families before generic page, category and tag sitemaps. PASS when the preferred canonical URL is found in an accessible sitemap. REVIEW only when inspection remains incomplete or the URL is not found after the configured inspection budget."),
    ("Mobile Content", "REVIEW/FAIL when mobile receives materially less main content than desktop."),
    ("JavaScript Rendering", "REVIEW when the initial HTML contains very little article text and depends heavily on scripts."),
    ("HTTPS", "PASS when the preferred page uses HTTPS and no HTTP render resources create detected mixed content. FAIL non HTTPS preferred pages and REVIEW mixed content."),
    ("Broken Resources", "Request only render relevant image, stylesheet, font preload and JavaScript resources. Exclude API discovery, oEmbed, canonical, alternate and WordPress endpoint links. PASS when checked render resources resolve successfully. REVIEW confirmed broken or unreachable render resources."),
]

CONTENT_RULES = [
    ("Search Intent", "PASS when the main content directly addresses the topic promised by the title/H1."),
    ("Content Relevance", "Evaluate the isolated article by heading hierarchy and section context. FAQ sections are judged by their answers, and named project or place headings are judged by the content beneath them. REVIEW or FAIL only when substantial article sections remain unrelated after contextual analysis."),
    ("Thin Content", "System heuristic: PASS at 600+ meaningful words, REVIEW at 300–599, FAIL below 300. This is not a Google word count rule."),
    ("Original Value", "PASS when the page adds useful data, examples, analysis or first hand value. External/site comparison may be required."),
    ("Factual Accuracy", "Check non market factual information in the editorial article, such as transport, locations, institutions, laws, routes, services and historical facts. Exclude property prices, rents, ROI, yields and other market data. Do not treat the absence of a nearby source link as a factual error. REVIEW only when the article contains an internal factual contradiction or another concrete factual inconsistency that the system can demonstrate."),
    ("Outdated Information", "Evaluate old year references in context and also compare time sensitive claims with the latest editorial publication or modification date. Historical dates alone PASS. REVIEW stale or undated prices, rents, ROI, fees, laws, routes or project status using an internal freshness heuristic."),
    ("Keyword Use", "Evaluate Focus Keyword and Secondary Keyword use in context. Exact matching is not required for every secondary phrase. Repetition of the primary topic or named entity is allowed when editorially necessary. PASS natural use, REVIEW unusually repetitive wording, FAIL clearly manipulative repetition."),
    ("Repetition", "REVIEW/FAIL when sentences or paragraphs are unnecessarily repeated."),
    ("Generic / Filler Content", "REVIEW when a high share of text adds little topic specific information."),
    ("Title vs Content", "PASS when title terms/topic are strongly represented in the body."),
    ("H1 vs Content", "PASS when H1 accurately represents the main body."),
    ("Heading Relevance", "Respect heading hierarchy when evaluating H2 to H4 sections. FAQ headings include their child questions and answers. Project, building, place and other entity headings can PASS through related section context even without Focus Keyword wording."),
    ("Introduction Quality", "PASS when the opening quickly establishes the promised topic."),
    ("FAQ Quality", "Extract question and answer pairs from the FAQ hierarchy. REVIEW empty or very short answers, heavy answer duplication or a predominantly unrelated FAQ section."),
    ("Unsupported Superlatives", "Evaluate the exact claim context. Objective ranking claims such as cheapest, highest, lowest or most popular require nearby attribution or a source link. Editorial soft wording such as best is not automatically treated as an unsupported factual claim."),
    ("Source Quality", "Judge support at the claim level using nearby attribution and source links, not raw external link count. REVIEW poorly supported quantitative or regulatory claims where sourcing is reasonably expected."),
    ("Data Accuracy", "Check internal numeric consistency by finding substantially repeated statements with conflicting values. PASS when no internal contradiction is detected. External truth verification remains part of Factual Accuracy."),
    ("Entity Accuracy", "Normalize generic property wording and leading prepositions around entity names, merge exact normalized duplicates, and compare only materially different spellings for suspicious near duplicates. REVIEW remaining entities that need external verification or possible inconsistent naming. FAIL only when a connected verification source confirms an entity is incorrect."),
    ("Grammar / Readability", "REVIEW when sentence structure is consistently difficult to read or text is obviously malformed."),
    ("Broken Content", "FAIL obvious placeholders/unfinished output; REVIEW empty headings or duplicated content blocks."),
]


SYSTEM_USES = {
    # Spam
    "Cloaking": "Desktop User Agent, Googlebot User Agent, final URL comparison, main content extraction, text similarity",
    "Sneaky Redirect": "Desktop User Agent, Googlebot User Agent, HTTP redirect handling, final destination comparison",
    "Device Spam Redirect": "Desktop User Agent, Mobile User Agent, final URL comparison, main content similarity",
    "Hidden Text": "Rendered DOM when available, computed CSS, hidden attribute, accessibility attributes, responsive visibility, interface context, text length and hiding reason classification",
    "Hidden Links": "Fetched HTML <a href> elements, per-element occurrence counting, same-page exclusion, empty anchors and HTML/CSS hiding signals",
    "Keyword Stuffing": "Editorial article text only, Focus Keyword, Secondary Keywords, exact phrase counts, repetition per 1,000 words, N gram frequency, primary topic phrase detection, title, H1 and URL context; TruBroker/property widgets, banners, newsletter, social UI and other embedded modules are excluded",
    "Link Spam": "External link count, anchor text, destination domain, anchor length, link pattern analysis",
    "Hacked Content": "Rendered page text, suspicious spam terms, injected content pattern matching",
    "Spam JavaScript": "Inline JavaScript, redirect patterns, obfuscation patterns, location functions, encoded script indicators",
    "Spam Iframes": "Iframe elements, iframe visibility, CSS hiding rules, iframe source information",
    "User Generated Spam": "Comment and user content containers, DOM class and ID patterns, links inside user content areas",
    "Back Button Hijacking": "JavaScript history functions, popstate, pushState, replaceState, redirect and location logic",
    "Malware / Scam Behaviour": "JavaScript source, script obfuscation patterns, script injection patterns, suspicious redirect behaviour",

    # SEO
    "HTTP Status": "HTTP request and returned response status code",
    "Indexability": "Meta robots directive, Googlebot meta directive, noindex detection",
    "Robots": "Meta robots and Googlebot directives, robots.txt HTTP response, robots.txt parsing and Googlebot URL fetch permission",
    "Canonical": "Canonical link element, canonical destination, current final URL, URL path comparison",
    "Title Tag": "HTML title element, character count as an advisory signal, Focus Keyword exact or semantic term overlap, title to article topic overlap, repeated title terms",
    "Meta Description": "Meta description element, advisory length, semantic topic agreement and Focus Keyword meaning rather than exact phrase requirement",
    "H1": "Full page H1 elements including article header H1, H1 count, Focus Keyword exact match, semantic concept overlap and article topic relationship",
    "Heading Structure": "Primary page H1 plus isolated editorial H2 through H6 headings, empty headings, duplicate headings and hierarchy level jumps",
    "URL Structure": "URL scheme, domain, path, query parameters, query length, invalid character patterns",
    "Internal Links": "Only inline editorial text hyperlinks inside paragraph, list and table text in the isolated article body; non-editorial modules are excluded; HEAD is followed by normal GET confirmation when needed; only GET-confirmed HTTP 404/410 is treated as a broken destination",
    "External Links": "External anchor URLs, HTTP HEAD or lightweight GET requests, response code, final destination and request errors",
    "Images": "Isolated editorial article images, TruBroker and broker/property widget exclusion by asset URL and DOM ancestry, decorative image signals, alt attribute and alt text, lazy image source resolution and image resource response status",
    "datePublished": "Schema datePublished, article published metadata, visible time elements and date consistency comparison",
    "Sitemap": "robots.txt sitemap declarations, common sitemap locations, recursive sitemap index traversal, editorial post and article sitemap prioritisation, preferred URL lookup, lastmod extraction, caching and bounded parallel requests",
    "Mobile Content": "Desktop User Agent, Mobile User Agent, extracted main content, text similarity",
    "JavaScript Rendering": "Extracted article word count, script count, initial HTML content availability",
    "HTTPS": "Final URL scheme and HTTPS detection",
    "Broken Resources": "Render relevant image, stylesheet, font preload and JavaScript resource URLs, HTTP response codes, final destinations and request errors while excluding API discovery and metadata links",

    # Content
    "Search Intent": "Focus Keyword when provided, otherwise title and H1, article body, topic keyword overlap",
    "Content Relevance": "Focus Keyword or main topic, hierarchical H2 through H4 sections, FAQ parent and child content, entity heading recognition, semantic heading overlap and section context",
    "Thin Content": "Main content extraction and meaningful article word count",
    "Original Value": "Main content word count, tables, lists, numeric references, useful information signals",
    "Factual Accuracy": "Editorial non market factual claims only, including transport, locations, institutions, laws, routes, services and historical facts; property prices, rents, ROI, yields and market statistics are excluded; nearby source links are optional and are not used as a failure condition",
    "Outdated Information": "Old year context, time sensitive claim detection, schema and visible editorial dates, and age of the latest editorial freshness signal",
    "Keyword Use": "Focus Keyword, Secondary Keywords, exact phrase counts, semantic topic representation, repetition per 1,000 words, N gram frequency and primary topic phrase detection",
    "Repetition": "Normalised sentences, normalised paragraphs, duplicate counts, repetition ratio",
    "Generic / Filler Content": "Substantial paragraphs, Focus Keyword or main topic, paragraph topic overlap",
    "Title vs Content": "HTML title text, main article body, topic keyword overlap",
    "H1 vs Content": "Main H1 text, main article body, topic keyword overlap",
    "Heading Relevance": "Hierarchical H2 through H4 relationships, Focus Keyword or main topic, FAQ child content, entity heading recognition, semantic concept overlap and section context",
    "Introduction Quality": "First section of the article, approximately the first 140 words, Focus Keyword or main topic, topic overlap",
    "FAQ Quality": "FAQ heading hierarchy, extracted question and answer pairs, answer word count, duplicate answers and topic relevance",
    "Unsupported Superlatives": "Exact superlative claim blocks, hard versus editorial soft superlatives, nearby attribution, local source links and section context",
    "Source Quality": "Concrete factual claim extraction, nearby visible attribution, local source links, regulatory claim detection and claim level support ratio",
    "Data Accuracy": "Repeated numeric statement templates, conflicting value tuples, percentages and internal consistency signals",
    "Entity Accuracy": "Normalized entity candidates from proper noun headings, anchor text and proper noun phrases, property wording and preposition removal, exact normalized de duplication, CTA and FAQ filtering, near duplicate spelling similarity and external or first party verification requirement",
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

KEYWORD_STUFFING_REMOVE_SELECTORS = [
    # Bayut dynamic property / broker widgets injected inside article content
    ".area-property-details",
    ".bayut-tru-broker-slider",
    ".property-similar",
    ".property",
    ".listing-heading",
    ".tru-broker-label",

    # Promotional banners / utility modules inside the article body
    ".dubai-transations-banner",
    ".dubai-transactions-banner",
    ".mobile-grid-newsletter-subscription",
    ".newsletter-mobile-listing-wrapper",
    ".google-preferred-source-btn",

    # Social / feedback UI that can sit inside entry-content
    ".swp_social_panel",
    ".swp-content-locator",
    ".current-article-rating",
    ".article-rating",
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

ARTICLE_BOILERPLATE_CONTAINER_TAGS = {
    "div",
    "section",
    "aside",
    "nav",
    "footer",
    "form",
    "header",
}

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
    """
    Identify non-editorial UI containers only.

    Important:
    Do NOT classify headings, paragraphs, anchors, list items or other
    editorial elements as boilerplate merely because their id/class contains
    words such as "most-popular", "related" or "comment".

    Example that must remain:
      <h2 id="Which-are-the-most-popular-areas-...">...</h2>
    """
    if node is None or not getattr(node, "name", None):
        return False

    if node.name.lower() not in ARTICLE_BOILERPLATE_CONTAINER_TAGS:
        return False

    sig = node_signature(node)
    return any(
        pattern in sig
        for pattern in ARTICLE_BOILERPLATE_PATTERNS
    )

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

    # Remove only true UI containers whose IDs/classes strongly identify non article UI.
    # Never remove editorial headings just because their IDs contain words such as most-popular.
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

def keyword_stuffing_editorial_text(soup):
    """
    Return only writer/editorial prose for Keyword Stuffing analysis.

    Dynamic Bayut widgets embedded inside .entry-content are removed so
    repeated interface labels such as TruBroker do not affect keyword
    repetition calculations.
    """
    article = article_content_node(soup)
    clone = BeautifulSoup(str(article), "html.parser")

    for selector in KEYWORD_STUFFING_REMOVE_SELECTORS:
        for node in clone.select(selector):
            node.decompose()

    # Remove remaining forms/buttons and interactive UI text.
    for node in clone.find_all(["form", "button"]):
        node.decompose()

    return clean_text(clone)

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
    Rank likely child sitemaps first.

    Editorial article sitemaps receive a stronger priority than generic page,
    category, tag, author or media sitemaps. This makes the result less likely
    to alternate between PASS and REVIEW because of the time budget.
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

    # Strong editorial sitemap preferences.
    if "post-sitemap" in sm:
        score += 30
    if "article-sitemap" in sm or "articles-sitemap" in sm:
        score += 26
    if "blog-sitemap" in sm:
        score += 22

    # MyBayut article URLs should strongly prefer MyBayut post sitemaps.
    if "/mybayut/" in path and "mybayut" in sm:
        score += 18
    if "/mybayut/" in path and "post-sitemap" in sm:
        score += 18

    # Lower priority for non-editorial sitemap families.
    for low_priority in (
        "category-sitemap",
        "tag-sitemap",
        "author-sitemap",
        "attachment-sitemap",
        "media-sitemap",
        "image-sitemap",
    ):
        if low_priority in sm:
            score -= 20

    if "page-sitemap" in sm:
        score -= 4

    for useful in ("post", "posts", "article", "articles", "blog"):
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


DEFAULT_ACTIONS = {
    "Cloaking": "Serve the same primary editorial content and destination to normal users and Googlebot. Remove crawler specific SEO content or redirects.",
    "Sneaky Redirect": "Remove deceptive or crawler specific redirects. Keep legitimate redirects consistent for users and crawlers.",
    "Device Spam Redirect": "Use the same relevant destination and primary content for desktop and mobile users.",
    "Hidden Text": "Make editorial text visible unless it is legitimately hidden for interface, responsive or accessibility reasons.",
    "Hidden Links": "Remove deliberately concealed links. Keep hidden interface links only when their UI or accessibility purpose is clear.",
    "Keyword Stuffing": "Reduce repeated query phrases that read unnaturally. Keep necessary location and entity names when editorially justified.",
    "Link Spam": "Remove or rewrite manipulative keyword rich links and repeated commercial anchor patterns. Keep editorial links relevant and natural.",
    "Hacked Content": "Remove injected spam content, secure the CMS and plugins, rotate credentials and verify the clean page after remediation.",
    "Spam JavaScript": "Review suspicious redirect or obfuscation scripts. Remove scripts that inject spam, links or deceptive redirects.",
    "Spam Iframes": "Remove unauthorized or unexplained hidden iframes. Keep only legitimate embeds with a clear visible purpose.",
    "User Generated Spam": "Remove spam comments or profile links, strengthen moderation and apply appropriate UGC or nofollow treatment where needed.",
    "Back Button Hijacking": "Remove browser history logic that traps users or forces redirects when they try to return to the previous page.",
    "Malware / Scam Behaviour": "Remove malicious or deceptive scripts and downloads, secure the site and run a security review before republishing.",

    "HTTP Status": "Make the preferred live article return HTTP 200. Fix 404 or 5xx responses and unnecessary redirect chains.",
    "Indexability": "Remove unintended noindex from an article that should appear in search. Keep noindex only when it is intentional.",
    "Robots": "Allow Googlebot to fetch the intended article in robots.txt and remove unintended restrictive page level robots directives.",
    "Canonical": "Point the canonical to the correct preferred live URL and ensure that canonical target returns a successful response.",
    "Title Tag": "Rewrite the title so it clearly represents the page topic without unnecessary repetition or verbosity.",
    "Meta Description": "Add or rewrite a useful description that accurately represents the page. Exact Focus Keyword wording is not required.",
    "H1": "Add one clear editorial H1 that accurately represents the page topic. Exact Focus Keyword matching is not required.",
    "Heading Structure": "Fix empty, duplicated or skipped heading levels in the editorial article structure.",
    "URL Structure": "Use a clean readable preferred URL and remove unnecessary or misleading parameters.",
    "Internal Links": "Fix only the internal hyperlinks reported inside the article content. Correct broken destinations, replace empty or generic anchors with descriptive text and rewrite spammy or misleading anchor text.",
    "External Links": "Fix, replace or remove each confirmed problematic external destination. Social platform anti bot responses do not need fixing by themselves.",
    "Images": "For each meaningful image reported, add useful alt text or fix the broken image resource. Decorative images can use empty alt treatment.",
    "datePublished": "Add or correct the editorial publication date so schema and visible metadata agree.",
    "Sitemap": "Ensure the preferred canonical URL is included in an accessible editorial sitemap and that the sitemap can be completed within the audit.",
    "Mobile Content": "Restore any primary article content missing from mobile so desktop and mobile present materially equivalent information.",
    "JavaScript Rendering": "Ensure important article content is present in initial HTML or reliably server rendered, not dependent on client JavaScript alone.",
    "HTTPS": "Serve the preferred page and render resources over HTTPS and remove mixed HTTP resources.",
    "Broken Resources": "Fix, replace or remove every reported broken image, CSS, font preload or JavaScript resource.",

    "Search Intent": "Rewrite the article so it directly answers the search topic promised by the title, H1 and Focus Keyword meaning.",
    "Content Relevance": "Remove unrelated sections or rewrite them so each H2 to H4 section clearly serves the page topic.",
    "Thin Content": "Add useful information, data, examples, comparisons or guidance. Do not add filler simply to increase word count.",
    "Original Value": "Add original Bayut value such as first party data, useful analysis, comparisons, tables, examples or practical guidance.",
    "Factual Accuracy": "Review and correct only the specific non market factual inconsistency listed in Result. Property market figures are intentionally excluded from this rule.",
    "Outdated Information": "Refresh time sensitive prices, rents, ROI, fees, laws, routes or project status, then update the editorial modification date only after the content is actually updated.",
    "Keyword Use": "Reduce unnatural repeated target phrases while keeping necessary topic and entity wording.",
    "Repetition": "Remove or consolidate repeated sentences and paragraphs.",
    "Generic / Filler Content": "Replace weak generic paragraphs with topic specific information, data, examples or useful guidance.",
    "Title vs Content": "Align the title with what the article actually covers, or update the article so it fulfils the title.",
    "H1 vs Content": "Align the H1 with the actual article body.",
    "Heading Relevance": "Rename, remove or rewrite weak headings and their sections so they clearly belong to the main topic.",
    "Introduction Quality": "Rewrite the opening so it establishes the main topic and user need quickly.",
    "FAQ Quality": "Add complete useful answers, remove duplicate answers and keep FAQ questions relevant to the article topic.",
    "Unsupported Superlatives": "For every objective ranking claim reported, add nearby attribution or a supporting source. Otherwise soften or remove the claim.",
    "Source Quality": "Add an authoritative or first party source beside each important unsupported quantitative, ranking, regulatory or fee claim reported by the system.",
    "Data Accuracy": "Correct the specific conflicting numeric statements reported so the same fact does not appear with different values.",
    "Entity Accuracy": "Verify the exact entity names reported. Standardize possible typo variants to the official project, company, place or building name.",
    "Grammar / Readability": "Rewrite the reported difficult or malformed sentences for clarity and readability.",
    "Broken Content": "Remove placeholders, fill empty headings and remove duplicated unfinished content blocks.",
}

def suggested_source_for_claim(claim):
    low = (claim or "").lower()

    if any(term in low for term in [
        "rent", "rental", "price", "aed", "roi", "yield",
        "average rent", "average price",
        "إيجار", "ايجار", "سعر", "أسعار", "اسعار", "عائد",
    ]):
        return "Bayut first party data or the approved internal property data source used for this article"

    if any(term in low for term in [
        "most popular", "most searched", "draws the most interest",
        "ranked", "top spot", "الأكثر بحث", "الاكثر بحث",
    ]):
        return "Bayut first party search, views or demand data that supports the ranking"

    if any(term in low for term in [
        "developed by", "developer", "completed", "launched", "opened",
        "المطور", "طورته", "اكتمل", "افتتح",
    ]):
        return "the developer official website or another authoritative first party project source"

    if any(term in low for term in [
        "minute", "minutes", "km", "kilomet", "distance",
        "metro", "bus", "route", "دقيقة", "دقائق", "كيلومتر", "مترو", "حافلة",
    ]):
        return "an authoritative transport, map or official location source"

    if any(term in low for term in [
        "law", "regulation", "fee", "fees", "visa", "rule",
        "قانون", "قوانين", "رسوم", "تأشيرة", "تاشيرة",
    ]):
        return "the relevant government or regulatory authority"

    return "a first party or authoritative source that directly supports this statement"

def compact_claim_action(claim, prefix="Verify"):
    clean = re.sub(r"\s+", " ", claim or "").strip()
    if len(clean) > 260:
        clean = clean[:257].rstrip() + "..."
    return f'{prefix}: "{clean}" | Needed source: {suggested_source_for_claim(clean)}'

def action_for(name, status, specific_action=""):
    if status == PASS:
        return "No action required."
    if specific_action:
        return specific_action
    return DEFAULT_ACTIONS.get(
        name,
        "Review the reported issue, correct the affected page element and rerun the audit."
    )

def result(name, status, finding, rule, action_needed=""):
    method = SYSTEM_USES.get(name, "Rule based page analysis")

    if name == "Hidden Links":
        why_text = (
            "Checked the fetched HTML for empty <a href> links "
            "and links hidden by HTML/CSS."
        )
    else:
        why_text = (
            f"The system used {method}. "
            f"The fixed rule applied is: {rule}"
        )

    return {
        "Check": name,
        "Status": status,
        "Result": finding,
        "Action Needed": action_for(name, status, action_needed),
        "Why": why_text,
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


VISIBLE_ANCHOR_CHILD_TAGS = {
    "img", "svg", "picture", "video", "audio",
    "canvas", "object", "embed", "iframe",
}

def anchor_has_visible_html_content(anchor):
    """
    HTML-source test for whether an anchor contains any content that could
    normally be visible to the user.

    Text counts as visible content.
    Common visual media descendants count as visible content.

    aria-label/title do not count as visible page content.
    """
    text_value = re.sub(
        r"\s+",
        " ",
        anchor.get_text(" ", strip=True),
    ).strip()

    if text_value:
        return True

    for tag_name in VISIBLE_ANCHOR_CHILD_TAGS:
        if anchor.find(tag_name) is not None:
            return True

    return False

def nearest_editorial_context(anchor, max_chars=140):
    """
    Return a short nearby text label so the editor can locate the empty
    anchor in the article, e.g. the project paragraph immediately before it.
    """
    # First prefer the closest previous paragraph/list/heading/table text.
    previous = anchor.find_previous(
        ["p", "li", "h2", "h3", "h4", "td", "th"]
    )

    if previous is not None:
        value = re.sub(
            r"\s+",
            " ",
            previous.get_text(" ", strip=True),
        ).strip()

        if value:
            if len(value) > max_chars:
                value = value[: max_chars - 3].rstrip() + "..."
            return value

    parent = anchor.parent
    if parent is not None:
        value = re.sub(
            r"\s+",
            " ",
            parent.get_text(" ", strip=True),
        ).strip()

        if value:
            if len(value) > max_chars:
                value = value[: max_chars - 3].rstrip() + "..."
            return value

    return ""

def is_empty_href_anchor(anchor, base_url):
    """
    Detect an effectively invisible HTML hyperlink:
    an actual HTTP(S) href with no visible text/media content inside <a>.
    """
    href = normalized_link_url(
        anchor.get("href"),
        base_url,
    )

    if not href:
        return False

    if urlparse(href).scheme not in {"http", "https"}:
        return False

    return not anchor_has_visible_html_content(anchor)


def source_hidden_reasons(node):
    """
    Return source-level hiding reasons found directly on one HTML element.

    This intentionally uses fetched HTML attributes and inline styles only.
    It does not depend on browser rendering.
    """
    reasons = []

    if node is None or not getattr(node, "attrs", None):
        return reasons

    if node.has_attr("hidden"):
        reasons.append("hidden attribute")

    if node.has_attr("inert"):
        reasons.append("inert attribute")

    style = str(node.get("style") or "").lower()
    style_compact = re.sub(r"\s+", "", style)

    if "display:none" in style_compact:
        reasons.append("display none")

    if (
        "visibility:hidden" in style_compact
        or "visibility:collapse" in style_compact
    ):
        reasons.append("visibility hidden")

    if re.search(r"opacity\s*:\s*0(?:[;}]|$)", style, flags=re.I):
        reasons.append("opacity zero")

    if re.search(r"font-size\s*:\s*0(?:px|em|rem|%|;|$)", style, flags=re.I):
        reasons.append("font size zero")

    width_zero = bool(
        re.search(r"(?:^|;)\s*width\s*:\s*0(?:px|em|rem|%|;|$)", style, flags=re.I)
    )
    height_zero = bool(
        re.search(r"(?:^|;)\s*height\s*:\s*0(?:px|em|rem|%|;|$)", style, flags=re.I)
    )
    if width_zero or height_zero:
        reasons.append("zero dimensions")

    if (
        re.search(r"(?:left|right|top|bottom)\s*:\s*-\d{3,}(?:px|em|rem)", style, flags=re.I)
        or re.search(r"text-indent\s*:\s*-\d{3,}(?:px|em|rem)", style, flags=re.I)
    ):
        reasons.append("offscreen positioning")

    if (
        "clip:rect(0,0,0,0)" in style_compact
        or "clip-path:inset(50%)" in style_compact
    ):
        reasons.append("clipped")

    if "content-visibility:hidden" in style_compact:
        reasons.append("content visibility hidden")

    if (
        "transform:scale(0)" in style_compact
        or "transform:scalex(0)" in style_compact
        or "transform:scaley(0)" in style_compact
    ):
        reasons.append("scale zero")

    return reasons

def hidden_ancestor_info(anchor):
    """
    Walk the actual fetched-HTML ancestry for an anchor.

    Returns:
      (hidden_element, reasons)

    hidden_element is the first anchor/ancestor that contains a supported
    source-level hiding signal.
    """
    node = anchor

    while node is not None:
        reasons = source_hidden_reasons(node)

        if reasons:
            return node, reasons

        # Stop once we leave the document tree.
        node = getattr(node, "parent", None)

    return None, []


def is_same_page_link(url, base_url):
    """
    Treat links back to the current article as self-links and ignore them
    in Hidden Links.

    Fragments and query strings do not make the same article a different
    destination for this rule.

    Examples ignored:
      #respond
      current-article-url
      current-article-url#comments
      current-article-url?replytocom=123
    """
    try:
        target = urlparse(url)
        base = urlparse(base_url)

        target_host = target.netloc.lower().replace("www.", "")
        base_host = base.netloc.lower().replace("www.", "")

        target_path = re.sub(r"/+$", "", target.path or "/")
        base_path = re.sub(r"/+$", "", base.path or "/")

        if not target_path:
            target_path = "/"
        if not base_path:
            base_path = "/"

        return (
            target_host == base_host
            and target_path == base_path
        )
    except Exception:
        return False

def static_hidden_link_details(soup, base_url):
    """
    Detect hidden/effectively invisible links directly from fetched HTML.

    IMPORTANT:
    Each actual <a href> element is counted separately.

    Four empty anchors pointing to the same URL = four hidden-link instances.

    A single anchor may have more than one issue, e.g.
    "Empty anchor, Hidden HTML link", but it is still counted as one HTML
    link instance.
    """
    details = []

    for occurrence_index, anchor in enumerate(
        soup.find_all("a", href=True),
        start=1,
    ):
        href = normalized_link_url(
            anchor.get("href"),
            base_url,
        )

        if not href:
            continue

        # Ignore links back to the current article, including fragments.
        if is_same_page_link(href, base_url):
            continue

        anchor_text = re.sub(
            r"\s+",
            " ",
            anchor.get_text(" ", strip=True),
        ).strip()

        anchor_html = re.sub(
            r"\s+",
            " ",
            str(anchor),
        ).strip()

        issues = []
        reasons = []
        hidden_element = None

        # Case 1: empty <a href="..."></a>
        if is_empty_href_anchor(anchor, base_url):
            issues.append("Empty anchor")
            reasons.append("no visible text or media inside the anchor")

        # Case 2: anchor or ancestor hidden by source-level HTML/CSS
        detected_hidden_element, hidden_reasons = hidden_ancestor_info(anchor)

        if detected_hidden_element is not None:
            hidden_element = detected_hidden_element
            issues.append("Hidden HTML link")
            reasons.extend(hidden_reasons)

        if not issues:
            continue

        context = nearest_editorial_context(anchor)

        details.append({
            "occurrence": occurrence_index,
            "url": href,
            "anchor_text": anchor_text or "(empty)",
            "hidden_element": element_label(hidden_element or anchor),
            "hidden_because": ", ".join(reasons),
            "status": FAIL,
            "source": "Fetched HTML source",
            "anchor_html": anchor_html[:500],
            "context": context,
            "issue_type": ", ".join(issues),
        })

    return details

def hidden_link_details(soup, base_url):
    """
    Hidden Links uses fetched HTML source only.

    A link is reported only when an actual <a href> exists in the fetched
    HTML and that anchor or one of its HTML ancestors contains a supported
    source-level hiding signal.

    Rendered browser state is intentionally NOT used for this rule.
    """
    details = static_hidden_link_details(
        soup,
        base_url,
    )

    return details, {
        "available": True,
        "source": "Fetched HTML source only",
        "error": "",
    }

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

def _internal_get_probe(url, timeout):
    """
    Normal GET confirmation for an internal URL.
    """
    response = requests.get(
        url,
        headers=UA_DESKTOP,
        timeout=max(float(timeout), 5.0),
        allow_redirects=True,
        stream=True,
    )
    status = response.status_code
    final_url = response.url
    response.close()
    return status, final_url


@lru_cache(maxsize=4096)
def _probe_internal_http_url_cached(url, timeout, _bucket):
    """
    Conservative validation for editorial internal links.

    HEAD is used only as a quick first probe.
    Any HEAD failure or error status is confirmed with normal GET.
    Only GET-confirmed HTTP 404 or 410 is considered broken.
    """
    started = time.time()
    result_data = {
        "url": url,
        "status": None,
        "final_url": url,
        "error": "",
        "elapsed": 0.0,
        "confirmed_broken": False,
        "probe_method": "",
        "attempts": [],
    }

    effective_timeout = max(float(timeout), 5.0)

    # Fast first probe.
    try:
        response = requests.head(
            url,
            headers=UA_DESKTOP,
            timeout=effective_timeout,
            allow_redirects=True,
        )
        head_status = response.status_code
        head_final = response.url
        result_data["attempts"].append(f"HEAD {head_status}")

        if 200 <= head_status < 400:
            result_data["status"] = head_status
            result_data["final_url"] = head_final
            result_data["probe_method"] = "HEAD"
            result_data["elapsed"] = time.time() - started
            return result_data
    except Exception as exc:
        result_data["attempts"].append("HEAD failed")
        result_data["error"] = str(exc)

    # Confirm using normal GET. Retry once on transient failure.
    get_errors = []

    for attempt in range(2):
        try:
            get_status, get_final = _internal_get_probe(
                url,
                effective_timeout,
            )

            result_data["attempts"].append(f"GET {get_status}")
            result_data["status"] = get_status
            result_data["final_url"] = get_final
            result_data["probe_method"] = "GET"

            if get_status in {404, 410}:
                result_data["confirmed_broken"] = True
                break

            # Retry temporary server errors once.
            if get_status >= 500 and attempt == 0:
                continue

            break

        except Exception as exc:
            get_errors.append(str(exc))
            result_data["attempts"].append("GET failed")

            if attempt == 0:
                continue

    if result_data["status"] is None and get_errors:
        result_data["error"] = get_errors[-1]
        result_data["probe_method"] = "GET"

    result_data["elapsed"] = time.time() - started
    return result_data


def probe_internal_http_url(
    url,
    timeout=INTERNAL_LINK_CHECK_TIMEOUT,
):
    return _probe_internal_http_url_cached(
        url,
        timeout,
        cache_bucket(600),
    )


def validate_internal_url_set(
    urls,
    timeout=INTERNAL_LINK_CHECK_TIMEOUT,
    workers=INTERNAL_LINK_CHECK_WORKERS,
):
    """
    Only GET-confirmed HTTP 404/410 responses are classified as broken.

    Automated restrictions, timeouts, connection errors and temporary 5xx
    responses remain diagnostic only and do not become editorial link issues.
    """
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

    with ThreadPoolExecutor(
        max_workers=min(workers, len(urls))
    ) as executor:
        futures = {
            executor.submit(
                probe_internal_http_url,
                url,
                timeout,
            ): url
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

        if item.get("confirmed_broken"):
            broken.append(item)

        elif status is None:
            unreachable.append(item)

        elif 200 <= status < 400:
            working.append(item)

            if (
                item.get("final_url")
                and item["final_url"] != item["url"]
            ):
                redirected.append(item)

        elif status in {401, 403, 405, 406, 429}:
            restricted.append(item)

        elif status >= 500:
            server_errors.append(item)

        else:
            # Other automated responses are inconclusive, not broken.
            restricted.append(item)

    return {
        "checked": checked,
        "working": working,
        "redirected": redirected,
        "broken": broken,
        "restricted": restricted,
        "server_errors": server_errors,
        "unreachable": unreachable,
    }


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


def normalized_link_url(value, base_url=""):
    if not value:
        return ""
    resolved = urljoin(base_url, value) if base_url else value
    parsed = urlparse(resolved)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    # Fragments do not change the fetched document and should not create
    # duplicate link validation requests.
    return parsed._replace(fragment="").geturl()


SPAMMY_ANCHOR_TERMS = {
    "click here", "read more", "learn more", "more", "here",
    "buy now", "cheap", "best price", "free money",
    "casino", "betting", "viagra", "cialis", "loan",
    "اضغط هنا", "اقرأ المزيد", "المزيد",
}

BODY_LINK_EXCLUDE_PATTERNS = [
    "share", "sharing", "social", "facebook", "twitter", "linkedin",
    "whatsapp", "pinterest", "google-news", "google_source",
    "banner", "advert", "ad-", "promo", "promotion",
    "property-card", "listing-card", "property-listing", "listing",
    "recommended", "related", "widget", "sidebar",
    "agent", "broker-card", "find-agent", "find_an_agent",
    "cta", "button", "btn", "carousel", "slider",
    "author", "comment", "newsletter", "subscribe",
]

BODY_LINK_EXCLUDE_HREF_PATTERNS = [
    "facebook.com/share",
    "twitter.com/intent",
    "linkedin.com/cws/share",
    "linkedin.com/share",
    "google.com/preferences/source",
    "/brokers/?utm_source=organic",
    "/property/details-",
]

def body_link_has_excluded_container(anchor):
    """
    Exclude links that visually live inside non-editorial modules even when
    those modules are nested inside the article content container.
    """
    node = anchor

    while node is not None:
        if getattr(node, "name", None) in {
            "nav", "aside", "footer", "form", "button",
        }:
            return True

        attrs = " ".join([
            str(node.get("id") or ""),
            " ".join(node.get("class") or []),
            str(node.get("role") or ""),
        ]).casefold()

        if any(pattern in attrs for pattern in BODY_LINK_EXCLUDE_PATTERNS):
            return True

        node = getattr(node, "parent", None)

    return False

def is_inline_editorial_anchor(anchor):
    """
    A body link must be an actual text hyperlink inside editorial copy.

    Accepted parent content:
    paragraph, list item or table text.

    Excluded:
    image links, cards, banners, buttons, social sharing, agent CTA,
    property listing modules and other widgets.
    """
    if body_link_has_excluded_container(anchor):
        return False

    if anchor.find("img") is not None:
        return False

    # Must live inside actual editorial text, not only inside a generic div.
    textual_parent = anchor.find_parent(["p", "li", "td", "th"])
    if textual_parent is None:
        return False

    anchor_text = re.sub(
        r"\s+",
        " ",
        anchor.get_text(" ", strip=True),
    ).strip()

    if not anchor_text:
        return False

    href = str(anchor.get("href") or "").casefold()
    if any(pattern in href for pattern in BODY_LINK_EXCLUDE_HREF_PATTERNS):
        return False

    return True

def content_internal_link_inventory(article_soup, base_url):
    """
    Inspect only real inline editorial hyperlinks inside the article copy.

    Not included:
    banners, property cards, Find An Agent CTA, social share links,
    image links, broker modules, widgets, related content and other
    non-editorial elements that happen to sit inside the article container.
    """
    base_host = urlparse(base_url).netloc.lower().replace("www.", "")
    base_identity = normalized_destination(base_url)
    inventory = []

    for anchor in article_soup.find_all("a", href=True):
        if not is_inline_editorial_anchor(anchor):
            continue

        href = normalized_link_url(anchor.get("href"), base_url)
        if not href:
            continue

        # Self links are not useful editorial internal-link candidates.
        if normalized_destination(href) == base_identity:
            continue

        parsed = urlparse(href)
        host = parsed.netloc.lower().replace("www.", "")
        is_internal = host == base_host

        anchor_text = re.sub(
            r"\s+",
            " ",
            anchor.get_text(" ", strip=True),
        ).strip()

        low_anchor = anchor_text.casefold()
        anchor_words = tokenize(anchor_text)

        generic_anchor = low_anchor in SPAMMY_ANCHOR_TERMS

        suspicious_anchor = (
            generic_anchor
            or len(anchor_text) > 180
            or (
                len(anchor_words) >= 7
                and repeated_phrase_signal(anchor_text)
            )
        )

        slug_text = " ".join(
            token
            for token in re.findall(
                r"[a-zA-Z0-9]+",
                parsed.path.replace("-", " "),
            )
            if len(token) > 2
        )

        if anchor_text and slug_text:
            anchor_slug_overlap = max(
                keyword_overlap(anchor_text, slug_text),
                semantic_overlap(anchor_text, slug_text),
            )
        else:
            anchor_slug_overlap = 0.0

        inventory.append({
            "url": href,
            "anchor_text": anchor_text,
            "is_internal": is_internal,
            "empty_anchor": False,
            "generic_anchor": generic_anchor,
            "suspicious_anchor": suspicious_anchor,
            "anchor_slug_overlap": anchor_slug_overlap,
        })

    unique = []
    seen = set()

    for item in inventory:
        key = (
            item["url"],
            item["anchor_text"].casefold(),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)

    return unique

def repeated_phrase_signal(text):
    tokens = [t for t in tokenize(text) if len(t) > 2]
    if len(tokens) < 6:
        return False
    counts = Counter(tokens)
    return max(counts.values(), default=0) >= 3

def content_internal_link_urls(article_soup, base_url):
    return unique_http_urls([
        item["url"]
        for item in content_internal_link_inventory(article_soup, base_url)
        if item.get("is_internal")
    ])

def internal_link_issues(inventory, validation):
    """
    Return only actionable issues for inline editorial body links.

    Only GET-confirmed HTTP 404/410 responses are treated as broken.
    Automated restrictions, timeouts, connection errors and temporary 5xx
    responses are not reported as broken editorial links.
    """
    validation_by_url = {
        item.get("url"): item
        for item in validation.get("checked", [])
    }

    issues = []

    for item in inventory:
        reasons = []

        if not item.get("is_internal"):
            reasons.append("External link")
        else:
            checked = validation_by_url.get(item["url"])

            if checked:
                status = checked.get("status")

                # Only a normal GET-confirmed 404 or 410 is actionable.
                # Timeouts, connection errors, bot restrictions and temporary
                # 5xx responses are intentionally not reported as broken.
                if (
                    checked.get("confirmed_broken")
                    and status in {404, 410}
                ):
                    reasons.append(f"Broken link HTTP {status}")

        if item["generic_anchor"]:
            reasons.append("Generic anchor text")
        elif item["suspicious_anchor"]:
            reasons.append("Spammy or over optimised anchor text")

        if (
            item["anchor_text"]
            and len(tokenize(item["anchor_text"])) >= 2
            and item["anchor_slug_overlap"] < 0.12
        ):
            reasons.append("Anchor text may not match the linked page")

        if reasons:
            issues.append({
                "url": item["url"],
                "anchor_text": item["anchor_text"],
                "reasons": reasons,
            })

    return issues

def internal_link_issue_text(issues, limit=20):
    if not issues:
        return "No internal linking issues found inside the article body."

    lines = []

    for item in issues[:limit]:
        lines.append(
            f'{item["url"]} | Anchor: "{item["anchor_text"]}" | '
            f'Issue: {", ".join(item["reasons"])}'
        )

    if len(issues) > limit:
        lines.append(
            f"{len(issues) - limit} additional issue(s) not shown."
        )

    return "\n".join(lines)

def extract_page_links(soup, base_url):
    parsed = urlparse(base_url)
    host = parsed.netloc.lower().replace("www.", "")
    internal = []
    external = []

    for anchor in soup.find_all("a", href=True):
        href = normalized_link_url(anchor.get("href"), base_url)
        if not href:
            continue

        target_host = urlparse(href).netloc.lower().replace("www.", "")
        if target_host == host:
            internal.append(href)
        else:
            external.append(href)

    return unique_http_urls(internal), unique_http_urls(external)


def image_source_url(node, base_url):
    candidates = [
        node.get("src"),
        node.get("data-src"),
        node.get("data-lazy-src"),
        node.get("data-original"),
    ]
    srcset = node.get("srcset") or node.get("data-srcset")
    if srcset:
        first = srcset.split(",")[0].strip().split(" ")[0]
        candidates.append(first)

    for value in candidates:
        if not value or str(value).startswith("data:"):
            continue
        resolved = normalized_link_url(str(value), base_url)
        if resolved:
            return resolved
    return ""

def extract_resource_urls(soup, base_url):
    """
    Extract only resources that materially participate in page rendering.
    """
    urls = []

    for node in soup.find_all("script", src=True):
        resolved = normalized_link_url(node.get("src"), base_url)
        if resolved:
            urls.append(resolved)

    for node in soup.find_all("img"):
        resolved = image_source_url(node, base_url)
        if resolved:
            urls.append(resolved)

    for node in soup.find_all("source"):
        value = node.get("src")
        if not value and node.get("srcset"):
            value = node.get("srcset").split(",")[0].strip().split(" ")[0]
        resolved = normalized_link_url(value, base_url) if value else ""
        if resolved:
            urls.append(resolved)

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

        resolved = normalized_link_url(node.get("href"), base_url)
        if resolved:
            urls.append(resolved)

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
    "facebook.com", "m.facebook.com",
    "instagram.com",
    "linkedin.com",
    "twitter.com",
    "x.com",
    "tiktok.com",
    "pinterest.com",
    "youtube.com",
    "whatsapp.com", "wa.me",
    "threads.net",
}

def is_social_domain(url):
    host = urlparse(url or "").netloc.lower().split("@")[-1].split(":")[0]
    if host.startswith("www."):
        host = host[4:]

    return (
        host in SOCIAL_DOMAINS
        or any(host.endswith("." + domain) for domain in SOCIAL_DOMAINS)
    )

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


def response_redirect_chain(response):
    chain = []
    for item in list(getattr(response, "history", []) or []) + [response]:
        chain.append({
            "status": getattr(item, "status_code", None),
            "url": getattr(item, "url", ""),
        })
    return chain

def normalized_destination(url):
    p = urlparse(url or "")
    scheme = (p.scheme or "").lower()
    host = (p.netloc or "").lower().replace(":80", "").replace(":443", "")
    path = re.sub(r"/+$", "", p.path or "/") or "/"
    return (scheme, host, path, p.query or "")

def redirect_chain_summary(response):
    chain = response_redirect_chain(response)
    return " → ".join(
        f"{item['status']} {item['url']}"
        for item in chain
        if item.get("url")
    )

@lru_cache(maxsize=512)
def _robots_access_cached(page_url, _bucket):
    parsed = urlparse(page_url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    result_data = {
        "robots_url": robots_url,
        "status": None,
        "googlebot_allowed": None,
        "wildcard_allowed": None,
        "error": "",
    }

    try:
        response = requests.get(
            robots_url,
            headers=UA_DESKTOP,
            timeout=ROBOTS_REQUEST_TIMEOUT,
            allow_redirects=True,
        )
        result_data["status"] = response.status_code

        if response.status_code == 200:
            parser = urllib.robotparser.RobotFileParser()
            parser.set_url(robots_url)
            parser.parse(response.text.splitlines())
            result_data["googlebot_allowed"] = parser.can_fetch("Googlebot", page_url)
            result_data["wildcard_allowed"] = parser.can_fetch("*", page_url)
        elif response.status_code in {404, 410}:
            result_data["googlebot_allowed"] = True
            result_data["wildcard_allowed"] = True
    except Exception as exc:
        result_data["error"] = str(exc)

    return result_data

def robots_access_result(page_url):
    return _robots_access_cached(page_url, cache_bucket(600))


def image_should_be_ignored(node, base_url=""):
    """
    Ignore Bayut interface/widget images that are not editorial article images.

    TruBroker images must be excluded in two ways:
    1. Asset filename/URL contains a TruBroker marker.
    2. Image is inside a TruBroker/broker/property widget, even when the
       image URL itself is a generic S3 URL with no TruBroker text.
    """
    src = image_source_url(node, base_url) if base_url else (
        node.get("src")
        or node.get("data-src")
        or node.get("data-lazy-src")
        or node.get("data-original")
        or ""
    )

    low = str(src).lower()

    # Direct TruBroker promotional assets.
    if (
        "trubroker" in low
        or "tru-broker" in low
        or "tru_broker" in low
    ):
        return True

    # Dynamic broker/profile images use generic S3 URLs, so identify them
    # by their widget ancestry instead of the image filename.
    ignored_widget_markers = {
        "area-property-details",
        "bayut-tru-broker-slider",
        "property-similar",
        "broker-image",
        "tru-broker-label",
        "listing-heading",
    }

    parent = node.parent
    while parent is not None and getattr(parent, "name", None):
        classes = {
            str(value).strip().lower()
            for value in (parent.get("class") or [])
            if str(value).strip()
        }

        parent_id = str(parent.get("id") or "").strip().lower()

        if classes.intersection(ignored_widget_markers):
            return True

        if any(marker in parent_id for marker in ignored_widget_markers):
            return True

        parent = parent.parent

    return False

def image_is_decorative(node):
    role = (node.get("role") or "").lower()
    aria_hidden = (node.get("aria-hidden") or "").lower()
    alt = node.get("alt")
    signature = node_signature(node)
    src = " ".join([
        str(node.get("src") or ""),
        str(node.get("data-src") or ""),
        str(node.get("class") or ""),
    ]).lower()

    try:
        width = int(re.sub(r"[^\d]", "", str(node.get("width") or "0")) or 0)
        height = int(re.sub(r"[^\d]", "", str(node.get("height") or "0")) or 0)
    except Exception:
        width = height = 0

    if role in {"presentation", "none"} or aria_hidden == "true":
        return True
    if width and height and width <= 4 and height <= 4:
        return True

    decorative_markers = [
        "icon", "sprite", "spacer", "tracking", "pixel",
        "avatar", "emoji", "badge", "loader", "spinner",
    ]
    if any(marker in signature or marker in src for marker in decorative_markers):
        if not node.find_parent("figure"):
            return True

    # Empty alt is a valid decorative treatment when the image also has
    # an explicit decorative signal.
    if alt == "" and (
        role in {"presentation", "none"}
        or aria_hidden == "true"
        or any(marker in signature or marker in src for marker in decorative_markers)
    ):
        return True

    return False

def meaningful_image_inventory(soup, base_url, resource_validation=None):
    article = main_content_node(soup)
    meaningful = []
    decorative = []
    issues = []

    validation_by_url = {}
    if resource_validation:
        for item in resource_validation.get("checked", []):
            validation_by_url[item.get("url", "")] = item

    for node in article.find_all("img"):
        src = image_source_url(node, base_url)

        # Known Bayut TruBroker promotional/interface images are excluded
        # entirely from the editorial image quality check.
        if image_should_be_ignored(node, base_url):
            continue

        alt_present = node.has_attr("alt")
        alt_value = (node.get("alt") or "").strip()

        if image_is_decorative(node):
            decorative.append(src or "(inline image)")
            continue

        item = {
            "src": src,
            "alt_present": alt_present,
            "alt": alt_value,
        }
        meaningful.append(item)

        if not alt_present:
            issues.append(f"Meaningful image missing alt attribute: {src or '(source unavailable)'}")
        elif not alt_value:
            issues.append(f"Meaningful image has empty alt text: {src or '(source unavailable)'}")

        if src and src in validation_by_url:
            checked = validation_by_url[src]
            status = checked.get("status")
            if status is None or status >= 400:
                issues.append(
                    f"Meaningful image resource problem: {src} "
                    f"returned {status if status is not None else 'request error'}"
                )

    return {
        "meaningful": meaningful,
        "decorative": decorative,
        "issues": issues,
    }

ARTICLE_SCHEMA_TYPES = {
    "article", "blogposting", "newsarticle",
    "report", "analysisnewsarticle",
}

def article_schema_objects(jsonld):
    objects = []
    for root in jsonld:
        for obj in walk_json(root):
            if not isinstance(obj, dict):
                continue
            raw_type = obj.get("@type")
            types = raw_type if isinstance(raw_type, list) else [raw_type]
            normalized = {
                str(t).split("/")[-1].lower()
                for t in types
                if t
            }
            if normalized & ARTICLE_SCHEMA_TYPES:
                objects.append(obj)
    return objects

def schema_object_urls(obj):
    values = []
    for key in ["url", "@id"]:
        value = obj.get(key)
        if isinstance(value, str):
            values.append(value)

    main_entity = obj.get("mainEntityOfPage")
    if isinstance(main_entity, str):
        values.append(main_entity)
    elif isinstance(main_entity, dict):
        for key in ["@id", "url"]:
            value = main_entity.get(key)
            if isinstance(value, str):
                values.append(value)

    return values

def latest_editorial_datetime(soup):
    jsonld, _ = parse_jsonld(soup)
    modified = [
        parse_datetime_value(v)
        for v in get_schema_values(jsonld, "dateModified")
        if isinstance(v, (str, int, float))
    ]
    published = [
        parse_datetime_value(v)
        for v in get_schema_values(jsonld, "datePublished")
        if isinstance(v, (str, int, float))
    ]
    visible = visible_date_signals(soup)
    modified.extend(parse_datetime_value(v) for v in visible["modified"])
    published.extend(parse_datetime_value(v) for v in visible["published"])

    valid_modified = [d for d in modified if d is not None]
    valid_published = [d for d in published if d is not None]

    chosen = max(valid_modified) if valid_modified else max(valid_published) if valid_published else None
    if chosen and chosen.tzinfo is None:
        chosen = chosen.replace(tzinfo=timezone.utc)
    return chosen

ATTRIBUTION_TERMS = [
    "according to", "according to our data", "data experts",
    "based on our data", "bayut data", "our data", "research shows",
    "data shows", "as per", "source:", "sources:",
    "وفقا لبيانات", "وفقاً لبيانات", "بحسب البيانات", "وفق بيانات",
    "استنادا إلى", "استناداً إلى", "المصدر", "بيانات بيوت",
]

def has_attribution(text):
    low = (text or "").lower()
    return any(term.lower() in low for term in ATTRIBUTION_TERMS)

def nearby_support_context(node):
    parts = [node.get_text(" ", strip=True)]
    prev = node.find_previous_sibling()
    steps = 0
    while prev is not None and steps < 2:
        if getattr(prev, "name", None) in {"p", "li", "figcaption", "h2", "h3", "h4"}:
            parts.append(prev.get_text(" ", strip=True))
            steps += 1
        prev = prev.find_previous_sibling()
    return " ".join(parts)

def node_http_links(node, base_url):
    links = []
    for anchor in node.find_all("a", href=True):
        resolved = normalized_link_url(anchor.get("href"), base_url)
        if resolved:
            links.append(resolved)
    return unique_http_urls(links)

def faq_question_answer_pairs(article_soup):
    pairs = []
    for q in article_soup.find_all(re.compile(r"^h[2-4]$")):
        qtext = re.sub(r"\s+", " ", q.get_text(" ", strip=True)).strip()
        if not qtext.endswith(("?", "؟")):
            continue

        level = heading_level(q) or 4
        answer_parts = []
        for node in q.find_all_next():
            if node is q:
                continue
            node_level = heading_level(node)
            if node_level is not None and node_level <= level:
                break
            if node.name in {"p", "li", "td"}:
                value = re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()
                if value:
                    answer_parts.append(value)
            if sum(len(x) for x in answer_parts) > 1200:
                break

        pairs.append({
            "question": qtext,
            "answer": " ".join(answer_parts)[:1600],
        })
    return pairs

SUPERLATIVE_TERMS = [
    "most popular", "cheapest", "highest", "lowest", "number one", "#1",
    "best", "top choice",
    "الأكثر شعبية", "الأرخص", "الأعلى", "الاعلى", "الأفضل", "افضل",
]

HARD_SUPERLATIVE_TERMS = {
    "most popular", "cheapest", "highest", "lowest", "number one", "#1",
    "الأكثر شعبية", "الأرخص", "الأعلى", "الاعلى",
}

def superlative_claim_assessment(article_soup, base_url):
    claims = []
    section_map = {
        item["heading"]: item["section"]
        for item in heading_sections(article_soup)
    }

    for node in article_soup.find_all(["p", "li", "h2", "h3", "h4", "td"]):
        value = re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()
        if not value:
            continue
        low = value.lower()
        terms = [term for term in SUPERLATIVE_TERMS if term.lower() in low]
        if not terms:
            continue

        context = nearby_support_context(node)
        if node.name in {"h2", "h3", "h4"}:
            context += " " + section_map.get(value, "")[:700]

        links = node_http_links(node, base_url)
        supported = bool(links) or has_attribution(context)
        hard = any(term.lower() in HARD_SUPERLATIVE_TERMS for term in terms)

        claims.append({
            "text": value[:300],
            "terms": terms,
            "supported": supported,
            "hard": hard,
            "links": links,
            "attributed": has_attribution(context),
        })

    # De duplicate repeated DOM text.
    unique = []
    seen = set()
    for item in claims:
        key = item["text"].casefold()
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique

def numeric_statement_conflicts(article_soup):
    """
    Detect internal contradictions where essentially the same statement appears
    more than once with different numeric values.
    """
    templates = {}
    conflicts = []

    number_pattern = re.compile(
        r"(?:AED\s*)?\b\d+(?:[.,]\d+)?(?:\s*[KMB])?%?\b",
        flags=re.I,
    )

    for node in article_soup.find_all(["p", "li", "td", "th"]):
        value = re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()
        numbers = number_pattern.findall(value)
        if not numbers or len(value) < 35:
            continue

        template = number_pattern.sub("<num>", value.lower())
        template = re.sub(r"\s+", " ", template).strip()

        if len(template) < 25:
            continue

        normalized_numbers = tuple(
            re.sub(r"\s+", "", n.lower())
            for n in numbers
        )

        if template in templates and templates[template] != normalized_numbers:
            conflicts.append({
                "statement": value[:300],
                "previous_values": templates[template],
                "current_values": normalized_numbers,
            })
        else:
            templates[template] = normalized_numbers

    return conflicts[:8]

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
        has_claim_attribution_signal = bool(re.search(
            r"\b(?:according to|data experts|developed by|developer|completed|launched|located in|located at)\b",
            value,
            flags=re.I,
        ))

        if any(term in low for term in weak_marketing_terms) and not (
            has_numeric_specificity or has_claim_attribution_signal
        ):
            continue

        sources = []
        for anchor in node.find_all("a", href=True):
            resolved = urljoin(base_url, anchor.get("href"))
            if resolved.startswith(("http://", "https://")):
                sources.append(resolved)

        nearby_context = nearby_support_context(node)
        claim_links = unique_http_urls(sources)
        claims.append({
            "claim": value[:360],
            "source_links": claim_links,
            "attributed": has_attribution(nearby_context),
            "supported": bool(claim_links) or has_attribution(nearby_context),
        })

        if len(claims) >= limit:
            break

    return claims


def is_property_market_data_claim(value):
    """
    Return True for property-market data that Factual Accuracy must ignore.

    This intentionally excludes prices, rents, yields, ROI and similar market
    statistics while preserving non-market facts such as station names,
    transport routes, locations, institutions and historical dates.
    """
    value = re.sub(r"\s+", " ", value or "").strip()
    low = value.lower()

    if not value:
        return False

    monetary = bool(re.search(
        r"\bAED\s*[\d,.]+|\b(?:aed|dh|dhs)\b\s*[\d,.]+",
        value,
        flags=re.I,
    ))

    market_terms = [
        "rent", "rents", "rental", "renting",
        "price", "prices", "priced", "pricing",
        "sale price", "selling price", "asking price",
        "roi", "yield", "capital appreciation",
        "average cost", "average price", "average rent",
        "annual rent", "annual outlay", "financial outlay",
        "per sq ft", "per sqft", "psf",
        "market trend", "rental trend", "sales trend",
        "most searched", "search volume",
        "إيجار", "ايجار", "الإيجار", "الايجار",
        "سعر", "أسعار", "اسعار", "عائد", "عوائد",
        "متوسط السعر", "متوسط الإيجار", "متوسط الايجار",
    ]

    market_context = any(term in low for term in market_terms)

    numeric_market_signal = bool(re.search(
        r"\b\d+(?:[.,]\d+)?\s*(?:k|m|million|thousand|%)\b",
        low,
        flags=re.I,
    ))

    bedroom_price_context = bool(re.search(
        r"\b(?:studio|studios|\d+\s*(?:bed|bedroom|bhk))\b",
        low,
        flags=re.I,
    )) and (monetary or market_context)

    # Monetary property statements are market data by definition.
    if monetary:
        return True

    if market_context and numeric_market_signal:
        return True

    if bedroom_price_context:
        return True

    # Explicit ROI / yield percentages are market data.
    if re.search(r"\b(?:roi|yield)\b", low) and re.search(r"\d", low):
        return True

    return False


def non_market_factual_claim_examples(article_soup, limit=30):
    """
    Extract concrete non-market factual claims.

    Examples:
    transport lines and stations, routes, locations, institutions,
    laws/regulations, services, operating facts and historical facts.

    Property prices, rents, ROI, yields and other market data are excluded.
    A nearby source link is NOT required.
    """
    claims = []

    factual_patterns = [
        # Transport / location / service facts
        r"\b(?:metro station|metro stations|red line|green line|route 2020|bus route|bus routes|interchange station)\b",
        r"\b(?:connects?|connected to|served by|operates?|runs?|located in|located at|situated in|situated at|close to|near the)\b",
        r"\b(?:airport|station|terminal|authority|department|ministry|municipality|rta)\b",

        # Historical / institutional facts
        r"\b(?:opened|launched|established|founded|introduced|inaugurated|completed|since)\b",
        r"\b20(?:0\d|1\d|2\d)\b",

        # Legal / regulatory facts
        r"\b(?:law|laws|regulation|regulations|rule|rules|licence|license|visa)\b",

        # Arabic equivalents
        r"\b(?:محطة مترو|الخط الأحمر|الخط الاحمر|الخط الأخضر|الخط الاخضر|مسار 2020|خط حافلات|محطة تبادلية)\b",
        r"\b(?:يربط|تخدمها|يقع في|تقع في|بالقرب من|افتتح|أطلق|اطلق|تأسس|منذ)\b",
        r"\b(?:هيئة|وزارة|بلدية|قانون|قوانين|لائحة|لوائح|تأشيرة|تاشيرة)\b",
    ]

    for node in article_soup.find_all(["p", "li", "td"]):
        value = re.sub(
            r"\s+",
            " ",
            node.get_text(" ", strip=True),
        ).strip()

        if len(value) < 35:
            continue

        if is_property_market_data_claim(value):
            continue

        if not any(
            re.search(pattern, value, flags=re.I)
            for pattern in factual_patterns
        ):
            continue

        claims.append({
            "claim": value[:420],
        })

        if len(claims) >= limit:
            break

    return claims


def non_market_factual_conflicts(claim_examples):
    """
    Detect only concrete internal contradictions that can be demonstrated
    from the article itself.

    The checker is deliberately conservative. It compares substantially
    repeated non-market statements whose numeric/date values differ.
    """
    seen = {}
    conflicts = []

    for item in claim_examples:
        claim = re.sub(
            r"\s+",
            " ",
            item.get("claim", ""),
        ).strip()

        if not claim:
            continue

        # Values worth comparing for factual consistency: years and explicit
        # counts/durations/distances. Property market numbers are already gone.
        values = tuple(re.findall(
            r"\b20(?:0\d|1\d|2\d)\b|\b\d+(?:\.\d+)?\s*(?:minutes?|mins?|km|kilometres?|kilometers?|metres?|meters?)\b",
            claim,
            flags=re.I,
        ))

        if not values:
            continue

        template = claim.lower()

        # Normalize comparison values, punctuation and whitespace.
        template = re.sub(
            r"\b20(?:0\d|1\d|2\d)\b",
            "<value>",
            template,
        )
        template = re.sub(
            r"\b\d+(?:\.\d+)?\s*(?:minutes?|mins?|km|kilometres?|kilometers?|metres?|meters?)\b",
            "<value>",
            template,
            flags=re.I,
        )
        template = re.sub(r"[^a-z0-9<>]+", " ", template)
        template = re.sub(r"\s+", " ", template).strip()

        # Very short templates are too ambiguous.
        if len(template.split()) < 6:
            continue

        previous = seen.get(template)

        if previous and previous["values"] != values:
            conflicts.append({
                "first": previous["claim"],
                "second": claim,
                "first_values": previous["values"],
                "second_values": values,
            })
        else:
            seen[template] = {
                "claim": claim,
                "values": values,
            }

    return conflicts



GENERIC_ENTITY_HEADINGS = {
    "faqs", "faq", "introduction", "conclusion", "overview", "summary",
    "popular", "comments", "leave a reply", "find a reliable agent",
    "frequently asked questions", "find an agent", "read more",
    "rent apartments", "rent villas", "apartments", "villas",
    "where to rent", "where can you rent",
}


ENTITY_GENERIC_PREFIX_PATTERNS = [
    # Generic property wording before a real named entity
    r"^(?:studio|studios)\s+(?:in|at|from|near|within|inside)\s+",
    r"^(?:apartment|apartments|flat|flats)\s+(?:in|at|from|near|within|inside)\s+",
    r"^(?:villa|villas|townhouse|townhouses)\s+(?:in|at|from|near|within|inside)\s+",
    r"^(?:unit|units|property|properties)\s+(?:in|at|from|near|within|inside)\s+",
    r"^(?:rent|rental|renting)\s+(?:in|at|from|near|within|inside)\s+",

    # Standalone English prepositions accidentally captured with a proper noun
    r"^(?:in|at|from|near|within|inside|around|across|by)\s+",

    # Common Arabic location prepositions accidentally captured with an entity
    r"^(?:في|داخل|ضمن|قرب|حول)\s+",
    r"^بالقرب\s+من\s+",
    r"^من\s+(?=[A-Z\u0600-\u06ff])",
]

def clean_entity_candidate(value):
    """
    Remove generic property wording and leading prepositions around a proper noun.

    Examples:
    studio in Elite Sports Residents -> Elite Sports Residents
    in Global Golf Residence -> Global Golf Residence
    near Victory Heights -> Victory Heights
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

    # Remove punctuation or connector remnants after repeated prefix cleaning.
    value = re.sub(r"^(?:[-–—,:;]+\s*)+", "", value).strip()
    value = re.sub(r"\s+", " ", value).strip(" ,.;:-")
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
    Find suspiciously similar entity spellings after full normalization.

    Exact matches after removing wrappers and prepositions are merged and are
    not reported. Legitimate numbered variants are also excluded.

    Real spelling variants such as:
    Elite Sports Residence
    Elite Sports Residents
    remain visible for editorial verification.
    """
    pairs = []

    for i, left in enumerate(entities):
        left_clean = clean_entity_candidate(left)
        left_key = entity_similarity_key(left_clean)
        if not left_key:
            continue

        for right in entities[i + 1:]:
            right_clean = clean_entity_candidate(right)
            right_key = entity_similarity_key(right_clean)

            # Exact normalized entities are the same entity, not a near duplicate.
            if not right_key or left_key == right_key:
                continue

            if roman_variant_pair(left_clean, right_clean):
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

            # Avoid false positives caused only by one extra generic connector token.
            if left_key in right_key or right_key in left_key:
                longer = right_key if len(right_key) > len(left_key) else left_key
                shorter = left_key if len(left_key) <= len(right_key) else right_key
                extra = longer.replace(shorter, "", 1).strip()
                if extra in {
                    "in", "at", "from", "near", "within", "inside",
                    "around", "by", "في", "داخل", "ضمن", "قرب"
                }:
                    continue

            if ratio >= threshold and token_overlap >= 0.60:
                pairs.append({
                    "left": left_clean,
                    "right": right_clean,
                    "similarity": ratio,
                })

    unique = []
    seen = set()

    for item in sorted(
        pairs,
        key=lambda x: x["similarity"],
        reverse=True,
    ):
        key = tuple(sorted([
            entity_similarity_key(item["left"]),
            entity_similarity_key(item["right"]),
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
        key = entity_similarity_key(value)

        if not key or key in seen:
            continue

        # Avoid article title or focus keyword style headings being mistaken for entities.
        if len(tokenize(value)) >= 6 and any(
            token in key
            for token in ["rent", "apartments", "villas", "properties"]
        ):
            continue

        seen.add(key)
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
    desktop_dest = normalized_destination(desktop_r.url)
    bot_dest = normalized_destination(bot_r.url)
    desktop_chain = response_redirect_chain(desktop_r)
    bot_chain = response_redirect_chain(bot_r)

    if desktop_dest != bot_dest:
        rows.append(result(
            "Cloaking",
            FAIL,
            f"User and Googlebot like requests reached different final destinations: {desktop_r.url} vs {bot_r.url}.",
            rules["Cloaking"],
        ))
    elif sim_bot < 0.72 and min(word_count(desktop_text), word_count(bot_text)) > 150:
        rows.append(result(
            "Cloaking",
            FAIL,
            f"Material user versus Googlebot like content difference detected ({sim_bot:.0%} similarity).",
            rules["Cloaking"],
        ))
    elif sim_bot < 0.88:
        rows.append(result(
            "Cloaking",
            REVIEW,
            f"User versus Googlebot like content similarity is {sim_bot:.0%}. Review dynamic or personalised content.",
            rules["Cloaking"],
        ))
    else:
        rows.append(result(
            "Cloaking",
            PASS,
            f"User versus Googlebot like content similarity is {sim_bot:.0%}. Final destination matches.",
            rules["Cloaking"],
        ))

    chains_materially_different = (
        desktop_dest != bot_dest
        or (
            len(desktop_chain) != len(bot_chain)
            and (len(desktop_chain) > 1 or len(bot_chain) > 1)
        )
    )
    if desktop_dest != bot_dest:
        st_redirect = FAIL
        note = (
            f"Different final destinations. User chain: {redirect_chain_summary(desktop_r)}. "
            f"Crawler chain: {redirect_chain_summary(bot_r)}."
        )
    elif chains_materially_different:
        st_redirect = REVIEW
        note = (
            "Final destination matches, but user and crawler redirect chains differ. "
            f"User chain: {redirect_chain_summary(desktop_r)}. "
            f"Crawler chain: {redirect_chain_summary(bot_r)}."
        )
    else:
        st_redirect = PASS
        note = f"User and crawler reach the same destination with no material redirect-chain difference: {desktop_r.url}"
    rows.append(result("Sneaky Redirect", st_redirect, note, rules["Sneaky Redirect"]))

    mobile_dest = normalized_destination(mobile_r.url)
    if mobile_dest != desktop_dest:
        rows.append(result(
            "Device Spam Redirect",
            FAIL,
            f"Mobile final destination differs from desktop. Desktop: {desktop_r.url}. Mobile: {mobile_r.url}.",
            rules["Device Spam Redirect"],
        ))
    else:
        sm = similarity(desktop_text, mobile_text)
        chain_diff = len(response_redirect_chain(mobile_r)) != len(desktop_chain)
        device_status = REVIEW if sm < 0.80 or chain_diff else PASS
        rows.append(result(
            "Device Spam Redirect",
            device_status,
            f"Desktop and mobile final destination matches; content similarity {sm:.0%}. "
            f"Redirect chain difference: {'yes' if chain_diff else 'no'}.",
            rules["Device Spam Redirect"],
        ))

    hidden_text_items = hidden_text_details(soup)
    if hidden_text_items:
        hidden_text_statuses = [x["status"] for x in hidden_text_items]
        hidden_text_status = FAIL if FAIL in hidden_text_statuses else REVIEW if REVIEW in hidden_text_statuses else PASS

        text_details = []
        for index, item in enumerate(hidden_text_items[:6], 1):
            text_details.append(
                f"Hidden text {index}. Purpose: {item['purpose']}. "
                f"Hidden Because: {item['hidden_because']}. Element: {item['hidden_element']}. "
                f"Example Text: {item['text']}. Assessment: {item['explanation']}"
            )

        if hidden_text_status == PASS:
            text_summary = "Hidden text was detected, but every detected block had a recognised legitimate hiding reason. "
        elif hidden_text_status == REVIEW:
            text_summary = "Hidden text was detected and at least one block has an unconfirmed hiding reason. "
        else:
            text_summary = "Hidden text was detected and at least one block uses a strongly concealed method without a recognised legitimate reason. "

        rows.append(result("Hidden Text", hidden_text_status, text_summary + " ".join(text_details), rules["Hidden Text"]))
    else:
        rows.append(result(
            "Hidden Text",
            PASS,
            "No substantial visually hidden text blocks were detected by the available static hiding checks.",
            rules["Hidden Text"],
        ))

    hidden_links, hidden_inventory = hidden_link_details(
        soup,
        desktop_r.url,
    )

    if hidden_links:
        hidden_status = FAIL

        issue_lines = [
            f"{len(hidden_links)} hidden link instance(s) found."
        ]

        for index, item in enumerate(hidden_links, start=1):
            link_url = item.get("url") or "(URL unavailable)"
            issue_type = item.get("issue_type") or "Hidden link"

            issue_lines.append(
                f"{index}. {link_url} | {issue_type}"
            )

        hidden_result = "\n".join(issue_lines)
        hidden_action = "Remove or fix the hidden link instances listed in Result."

    else:
        hidden_status = PASS
        hidden_result = "No hidden links found."
        hidden_action = ""

    rows.append(result(
        "Hidden Links",
        hidden_status,
        hidden_result,
        rules["Hidden Links"],
        hidden_action,
    ))

    article_soup = main_content_node(soup)
    page_internal, page_external = extract_page_links(soup, url)
    article_internal, article_external = extract_page_links(article_soup, url)
    article_host = urlparse(url).netloc.lower().replace("www.", "")

    article_anchors = []
    for a in article_soup.find_all("a", href=True):
        href = normalized_link_url(a.get("href"), url)
        if not href:
            continue
        host = urlparse(href).netloc.lower().replace("www.", "")
        if host != article_host and not is_social_domain(href):
            article_anchors.append((a, href))

    keyword_rich = 0
    repeated_anchor_counts = Counter()
    for a, href in article_anchors:
        txt = re.sub(r"\s+", " ", a.get_text(" ", strip=True)).strip().lower()
        if len(tokenize(txt)) >= 4:
            keyword_rich += 1
        if txt:
            repeated_anchor_counts[txt] += 1

    repeated_manipulative = [
        anchor for anchor, count in repeated_anchor_counts.items()
        if count >= 4 and len(tokenize(anchor)) >= 3
    ]

    if repeated_manipulative:
        link_status = REVIEW
        finding = (
            f"{len(article_anchors)} editorial external link(s) found. "
            f"Repeated keyword rich anchor patterns need review: {', '.join(repeated_manipulative[:5])}."
        )
    elif len(article_anchors) > 40 or (
        len(article_anchors) >= 12
        and keyword_rich / max(1, len(article_anchors)) > .70
    ):
        link_status = REVIEW
        finding = (
            f"{len(article_anchors)} editorial external links; {keyword_rich} use long keyword rich anchor text. "
            "Review link intent."
        )
    else:
        link_status = PASS
        finding = (
            f"{len(article_anchors)} non social editorial external link(s) and "
            f"{len(page_external)} page wide external link(s) found; no clear automated link spam pattern."
        )
    rows.append(result("Link Spam", link_status, finding, rules["Link Spam"]))

    paid_candidates = 0
    paid_bad = 0
    for a, href in article_anchors:
        context = (
            a.get_text(" ", strip=True)
            + " "
            + (a.parent.get_text(" ", strip=True) if a.parent else "")
        ).lower()
        if any(k in context for k in [
            "sponsored", "advertisement", "advertorial",
            "paid partnership", "affiliate",
        ]):
            paid_candidates += 1
            rel = {str(x).lower() for x in (a.get("rel") or [])}
            if not ({"sponsored", "nofollow"} & rel):
                paid_bad += 1

    script_text = "\n".join((s.string or s.get_text() or "") for s in soup.find_all("script"))
    suspicious_js = []
    for pattern in [
        "window.location", "location.replace(", "document.location",
        "eval(atob(", "fromCharCode(",
    ]:
        if pattern.lower() in script_text.lower():
            suspicious_js.append(pattern)
    js_status = REVIEW if len(suspicious_js) >= 2 else PASS
    rows.append(result(
        "Spam JavaScript",
        js_status,
        f"Suspicious redirect or obfuscation indicators: {', '.join(suspicious_js) if suspicious_js else 'none detected'}.",
        rules["Spam JavaScript"],
    ))

    iframes = soup.find_all("iframe")
    hidden_iframes = [i for i in iframes if obvious_hidden(i)]
    suspicious_iframe_sources = []
    for iframe in hidden_iframes:
        src = normalized_link_url(iframe.get("src"), url)
        if src and urlparse(src).netloc.lower().replace("www.", "") != article_host:
            suspicious_iframe_sources.append(src)

    if hidden_iframes and suspicious_iframe_sources:
        iframe_status = REVIEW
        iframe_find = (
            f"Found {len(hidden_iframes)} hidden iframe(s), including external hidden source(s): "
            + ", ".join(suspicious_iframe_sources[:4]) + "."
        )
    elif hidden_iframes:
        iframe_status = REVIEW
        iframe_find = f"Found {len(hidden_iframes)} hidden iframe(s); verify legitimate interface purpose."
    else:
        iframe_status = PASS
        iframe_find = f"{len(iframes)} iframe(s) found; none obviously hidden."
    rows.append(result("Spam Iframes", iframe_status, iframe_find, rules["Spam Iframes"]))


    comment_nodes = soup.select(".comment, .comments, [id*='comment'], [class*='comment']")
    ugc_links = []
    for n in comment_nodes:
        for a in n.find_all("a", href=True):
            href = normalized_link_url(a.get("href"), url)
            if href:
                ugc_links.append((a.get_text(" ", strip=True), href, a.get("rel") or []))

    ugc_domains = Counter(
        urlparse(href).netloc.lower().replace("www.", "")
        for _, href, _ in ugc_links
    )
    ugc_anchor_counts = Counter(
        re.sub(r"\s+", " ", anchor).strip().lower()
        for anchor, _, _ in ugc_links
        if anchor.strip()
    )
    spammy_ugc = (
        len(ugc_links) >= 10
        and (
            max(ugc_domains.values(), default=0) >= 6
            or max(ugc_anchor_counts.values(), default=0) >= 5
        )
    )

    if spammy_ugc:
        ugc_status = REVIEW
        ugc_finding = (
            f"Detected {len(ugc_links)} UGC link(s) with concentrated domain or repeated anchor patterns. "
            "Review comment moderation."
        )
    else:
        ugc_status = PASS
        ugc_finding = (
            f"Detected {len(ugc_links)} link(s) in comment or UGC like containers; "
            "no mass repeated UGC link pattern was detected."
        )
    rows.append(result("User Generated Spam", ugc_status, ugc_finding, rules["User Generated Spam"]))

    lower_js = script_text.lower()
    hijack = (
        "popstate" in lower_js
        and ("pushstate" in lower_js or "replacestate" in lower_js)
        and any(x in lower_js for x in ["location.href", "location.replace", "window.location"])
    )
    rows.append(result(
        "Back Button Hijacking",
        FAIL if hijack else PASS,
        "Browser-history redirect pattern detected."
        if hijack
        else "No obvious browser-history hijacking pattern detected.",
        rules["Back Button Hijacking"],
    ))

    malware_signals = sum(
        1
        for x in ["eval(atob(", "unescape(", "document.write('<script", 'document.write("<script']
        if x in lower_js
    )
    if malware_signals >= 2:
        ms = REVIEW
        mf = "Multiple script obfuscation or injection patterns detected; security review required."
    else:
        ms = PASS
        mf = "No strong malware or scam script signature detected by the static HTML and JavaScript scan."
    rows.append(result("Malware / Scam Behaviour", ms, mf, rules["Malware / Scam Behaviour"]))

    return rows


def audit_seo(
    url,
    desktop_r,
    desktop_elapsed,
    mobile_r,
    soup,
    body_text,
    focus_keyword="",
    secondary_keywords=None,
    sitemap_result=None,
    internal_validation=None,
    external_validation=None,
    resource_validation=None,
    robots_txt_result=None,
):
    rows = []
    rules = dict(SEO_RULES)
    secondary_keywords = secondary_keywords or []
    article_soup = main_content_node(soup)

    code = desktop_r.status_code
    redirect_count = len(getattr(desktop_r, "history", []) or [])
    if code == 200:
        http_status = PASS
    elif 300 <= code < 400:
        http_status = REVIEW
    else:
        http_status = FAIL
    rows.append(result(
        "HTTP Status",
        http_status,
        f"Final HTTP {code}. Redirects followed: {redirect_count}. Final URL: {desktop_r.url}. Response time: {desktop_elapsed:.2f}s.",
        rules["HTTP Status"],
    ))

    robots = robots_directives(soup)
    if "noindex" in robots:
        rows.append(result(
            "Indexability",
            FAIL,
            f"Page level robots directive contains noindex: {robots}",
            rules["Indexability"],
        ))
    else:
        rows.append(result(
            "Indexability",
            PASS,
            f"No page level noindex detected{': ' + robots if robots else ''}.",
            rules["Indexability"],
        ))

    if robots_txt_result is None:
        robots_txt_result = robots_access_result(desktop_r.url)

    robots_status = PASS
    robots_notes = []

    if "noindex" in robots:
        robots_status = FAIL
        robots_notes.append(f"Page meta contains noindex: {robots}.")
    elif "nofollow" in robots or "none" in robots:
        robots_status = REVIEW
        robots_notes.append(f"Page meta contains a restrictive follow directive: {robots}.")
    else:
        robots_notes.append(robots or "No restrictive page level robots meta detected.")

    rt_status = robots_txt_result.get("status")
    if rt_status == 200:
        if robots_txt_result.get("googlebot_allowed") is False:
            robots_status = FAIL
            robots_notes.append(
                f"robots.txt blocks the URL for Googlebot: {robots_txt_result['robots_url']}."
            )
        else:
            robots_notes.append(
                f"robots.txt allows Googlebot to fetch this URL: {robots_txt_result['robots_url']}."
            )
    elif rt_status in {404, 410}:
        robots_notes.append("robots.txt was not found; no URL level robots.txt block was detected.")
    elif rt_status is None or (rt_status and rt_status >= 500):
        if robots_status == PASS:
            robots_status = REVIEW
        robots_notes.append(
            f"robots.txt could not be reliably verified. "
            f"HTTP: {rt_status if rt_status is not None else 'request error'}."
        )
    else:
        if robots_status == PASS:
            robots_status = REVIEW
        robots_notes.append(f"robots.txt returned HTTP {rt_status}; verify crawler access manually.")

    rows.append(result("Robots", robots_status, " ".join(robots_notes), rules["Robots"]))

    canonical = canonical_href(soup)
    if not canonical:
        cs = REVIEW
        cf = "Canonical tag not found."
    else:
        can_abs = normalized_link_url(canonical, desktop_r.url)
        current_identity = normalized_destination(desktop_r.url)
        canonical_identity = normalized_destination(can_abs)
        canonical_probe = probe_http_url(can_abs) if can_abs else None

        if not can_abs:
            cs = FAIL
            cf = f"Canonical is malformed: {canonical}"
        elif canonical_identity != current_identity:
            cs = REVIEW
            cf = f"Canonical points to a different preferred URL: {can_abs}."
        elif canonical_probe and canonical_probe.get("status") not in range(200, 300):
            cs = REVIEW
            cf = (
                f"Canonical matches the page URL but the target did not return a successful response. "
                f"Canonical: {can_abs}. HTTP: {canonical_probe.get('status')}."
            )
        else:
            cs = PASS
            cf = f"Canonical matches the preferred final URL and resolves successfully: {can_abs}."
    rows.append(result("Canonical", cs, cf, rules["Canonical"]))

    title = title_text(soup)
    title_len = len(title)
    if not title:
        ts = FAIL
        title_reason = "Title is missing."
    else:
        ts = PASS
        title_reason_parts = []
        title_body_overlap = max(
            keyword_overlap(title, body_text),
            semantic_overlap(title, body_text),
        )
        focus_exact = keyword_in_text(focus_keyword, title) if focus_keyword else True
        focus_overlap = max(
            keyword_overlap(focus_keyword, title),
            semantic_overlap(focus_keyword, title),
        ) if focus_keyword else 1.0
        focus_represented = focus_exact or focus_overlap >= 0.60

        title_words = [
            w for w in tokenize(title)
            if len(w) > 2 and w not in {
                "the", "and", "for", "with", "from", "this", "that", "your", "you",
                "are", "our", "in", "on", "of", "to", "a", "an", "is",
                "في", "من", "على", "إلى", "الى", "عن", "هذا", "هذه", "مع", "و", "أو", "او",
            }
        ]
        repeated_title_terms = [
            word for word, count in Counter(title_words).items()
            if count >= 3
        ]

        if title_len > 80:
            ts = REVIEW
            title_reason_parts.append(
                f"The title contains {title_len} characters and may be more verbose than necessary."
            )
        elif title_len < 30 and title_body_overlap < 0.55:
            ts = REVIEW
            title_reason_parts.append(
                f"The title contains {title_len} characters and has weak topic coverage."
            )
        else:
            title_reason_parts.append(
                f"The title contains {title_len} characters. Length is treated as an internal quality signal only."
            )

        if title_body_overlap < 0.35:
            ts = REVIEW
            title_reason_parts.append(
                f"Title to article topic agreement is only {title_body_overlap:.0%}."
            )
        else:
            title_reason_parts.append(
                f"Title to article topic agreement is {title_body_overlap:.0%}."
            )

        if focus_keyword:
            if not focus_represented:
                ts = REVIEW
                title_reason_parts.append(
                    f"The Focus Keyword meaning is weakly represented in the title ({focus_overlap:.0%})."
                )
            elif focus_exact:
                title_reason_parts.append("The Focus Keyword is directly represented in the title.")
            else:
                title_reason_parts.append(
                    f"The Focus Keyword is represented semantically ({focus_overlap:.0%})."
                )

        if repeated_title_terms:
            ts = REVIEW
            title_reason_parts.append(
                "Repeated title terms detected: " + ", ".join(repeated_title_terms[:6]) + "."
            )

        title_reason = " ".join(title_reason_parts)

    rows.append(result(
        "Title Tag",
        ts,
        f"Title: {title or 'missing'}. {title_reason}",
        rules["Title Tag"],
    ))

    meta = meta_content(soup, name="description")
    ml = len(meta)
    if not meta:
        md = REVIEW
        meta_note = "Meta description is missing."
    else:
        meta_topic = max(
            semantic_overlap(focus_keyword or title, meta),
            keyword_overlap(focus_keyword or title, meta),
        )
        md = PASS
        notes = [f"{ml} characters.", f"Topic agreement {meta_topic:.0%}."]

        # Google does not define a fixed description character limit.
        if ml < 50 and meta_topic < 0.55:
            md = REVIEW
            notes.append("Description is very short and weakly represents the topic.")
        elif ml > 320:
            md = REVIEW
            notes.append("Description is unusually long and may be unnecessarily verbose.")

        if meta_topic < 0.35:
            md = REVIEW
            notes.append("Description has weak semantic relevance to the page topic.")
        elif focus_keyword and keyword_in_text(focus_keyword, meta):
            notes.append("Focus Keyword is directly represented.")
        elif focus_keyword:
            notes.append("Exact Focus Keyword wording is not required because the meaning is represented semantically.")

        meta_note = " ".join(notes) + f" Description: {meta[:220]}"

    rows.append(result("Meta Description", md, meta_note, rules["Meta Description"]))

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
                    f"The H1 strongly represents the article topic at {h1_page_topic:.0%} concept overlap."
                )
            else:
                h1_status = REVIEW
                relation_note = (
                    f"The H1 has weak semantic representation of the Focus Keyword ({h1_semantic:.0%}) "
                    f"and article topic ({h1_page_topic:.0%})."
                )
        else:
            h1_page_topic = semantic_overlap(h1_text, body_text)
            if h1_page_topic < 0.45:
                h1_status = REVIEW
            relation_note = f"H1 to article semantic concept overlap is {h1_page_topic:.0%}."

        count_note = (
            "One H1 was found."
            if len(h1s) == 1
            else f"{len(h1s)} H1 elements were found."
        )
        h1_finding = f"{count_note} H1: {h1_text}. {relation_note}"

    rows.append(result("H1", h1_status, h1_finding, rules["H1"]))

    heading_nodes = []
    primary_h1 = page_primary_h1(soup)
    if primary_h1:
        heading_nodes.append(("h1", primary_h1))

    for tag in article_soup.find_all(re.compile(r"^h[2-6]$")):
        txt = re.sub(r"\s+", " ", tag.get_text(" ", strip=True)).strip()
        heading_nodes.append((tag.name, txt))

    empty_headings = sum(1 for _, txt in heading_nodes if not txt)
    populated = [(tag, txt) for tag, txt in heading_nodes if txt]
    duplicate_count = len(populated) - len(set(txt.casefold() for _, txt in populated))

    level_jumps = []
    last_level = None
    for tag, txt in populated:
        level = int(tag[1])
        if last_level is not None and level > last_level + 1:
            level_jumps.append(
                f"H{last_level} to H{level} before '{txt[:70]}'"
            )
        last_level = level

    hs = REVIEW if empty_headings or duplicate_count >= 3 or level_jumps else PASS
    heading_finding = (
        f"{len(populated)} editorial headings; {empty_headings} empty; "
        f"{duplicate_count} duplicate occurrence(s); {len(level_jumps)} hierarchy jump(s)."
    )
    if level_jumps:
        heading_finding += " Examples: " + "; ".join(level_jumps[:4]) + "."
    rows.append(result("Heading Structure", hs, heading_finding, rules["Heading Structure"]))

    parsed = urlparse(desktop_r.url)
    q = parsed.query
    bad_chars = bool(re.search(r"\s|[<>\"{}|\\^`]", desktop_r.url))
    if bad_chars:
        us = FAIL
    elif len(q) > 80 or q.count("&") >= 4:
        us = REVIEW
    else:
        us = PASS
    rows.append(result(
        "URL Structure",
        us,
        f"Path: {parsed.path}" + (f" | Query: {q[:120]}" if q else ""),
        rules["URL Structure"],
    ))

    title_for_kw = title_text(soup)
    h1_for_kw = page_primary_h1(soup)
    keyword_body_text = keyword_stuffing_editorial_text(soup)

    kw_assessment = keyword_repetition_assessment(
        keyword_body_text,
        focus_keyword,
        secondary_keywords,
        title=title_for_kw,
        h1=h1_for_kw,
        url=url,
    )

    if kw_assessment["status"] == PASS:
        keyword_result = "No unnatural keyword repetition found in the editorial content."
    else:
        keyword_result = kw_assessment["reason"]

        if kw_assessment["gram"]:
            keyword_result += (
                f" Repeated phrase: '{kw_assessment['gram']}' "
                f"({kw_assessment['count']} uses; {kw_assessment['density']:.1%} of two word phrases)."
            )

        # Show only target phrases that are actually repeated enough to matter.
        material_targets = [
            (kw, exact, per_1000)
            for kw, exact, per_1000 in kw_assessment["targets"]
            if exact > 0 and per_1000 >= 10
        ]

        if material_targets:
            keyword_result += " Target phrase repetition: " + "; ".join(
                f"{kw}: {exact} use(s), {per_1000:.1f} per 1,000 words"
                for kw, exact, per_1000 in material_targets[:5]
            ) + "."

    rows.append(result(
        "Keyword Stuffing",
        kw_assessment["status"],
        keyword_result,
        rules["Keyword Stuffing"],
    ))


    internal, external = extract_page_links(soup, desktop_r.url)

    content_link_inventory = content_internal_link_inventory(
        article_soup,
        desktop_r.url,
    )

    content_internal_urls = unique_http_urls([
        item["url"]
        for item in content_link_inventory
        if item.get("is_internal")
    ])

    if internal_validation is None:
        internal_validation = validate_internal_url_set(
            content_internal_urls,
            timeout=INTERNAL_LINK_CHECK_TIMEOUT,
            workers=INTERNAL_LINK_CHECK_WORKERS,
        )

    internal_issues = internal_link_issues(
        content_link_inventory,
        internal_validation,
    )

    internal_status = REVIEW if internal_issues else PASS
    internal_finding = internal_link_issue_text(internal_issues)

    if internal_issues:
        internal_action = "Fix only the editorial body links listed in Result."
    else:
        internal_action = ""

    rows.append(result(
        "Internal Links",
        internal_status,
        internal_finding,
        rules["Internal Links"],
        internal_action,
    ))

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
        external_finding = "No broken external links found."
    elif external_problem_items:
        external_status = REVIEW
        external_problems = validation_problem_examples({
            "broken": external_classified["broken"],
            "server_errors": external_classified["server_errors"],
            "restricted": external_classified["restricted"],
            "unreachable": external_classified["unreachable"],
        })
        external_finding = (
            f"{len(external_classified['checked'])} unique external links were requested. "
            f"{len(external_classified['working'])} resolved successfully. "
            f"{len(external_classified['expected_platform'])} social platform link(s) returned expected automated access restrictions. "
            "Problems requiring review: " + "; ".join(external_problems) + "."
        )
    else:
        external_status = PASS
        external_finding = "No broken external links found."
    rows.append(result("External Links", external_status, external_finding, rules["External Links"]))

    image_inventory = meaningful_image_inventory(
        soup,
        desktop_r.url,
        resource_validation=resource_validation,
    )

    if image_inventory["issues"]:
        image_status = REVIEW

        simple_image_issues = []
        for issue in image_inventory["issues"][:10]:
            cleaned = issue

            if issue.startswith("Meaningful image has empty alt text: "):
                url_value = issue.split(": ", 1)[1]
                cleaned = f"{url_value} | Issue: Empty alt text"

            elif issue.startswith("Meaningful image missing alt attribute: "):
                url_value = issue.split(": ", 1)[1]
                cleaned = f"{url_value} | Issue: Missing alt attribute"

            elif issue.startswith("Meaningful image resource problem: "):
                rest = issue.split(": ", 1)[1]
                cleaned = f"{rest} | Issue: Broken image resource"

            simple_image_issues.append(cleaned)

        image_finding = "\n".join(simple_image_issues)
        image_action = "Fix only the images listed in Result."
    else:
        image_status = PASS
        image_finding = "No image issues found inside the article content."
        image_action = ""

    rows.append(result(
        "Images",
        image_status,
        image_finding,
        rules["Images"],
        image_action,
    ))

    # JSON LD remains only as a source for datePublished and other internal freshness signals.
    jsonld, _json_errors = parse_jsonld(soup)

    published = [
        str(value)
        for value in get_schema_values(jsonld, "datePublished")
        if isinstance(value, (str, int, float))
    ]
    visible_dates = visible_date_signals(soup)

    published_status = PASS if published else REVIEW
    published_notes = [
        f"Schema datePublished: {published[:3] if published else 'not found'}."
    ]
    if visible_dates["published"]:
        published_notes.append(f"Visible or metadata published dates: {visible_dates['published'][:3]}.")
        if published:
            diffs = [
                datetime_difference_hours(published[0], value)
                for value in visible_dates["published"]
            ]
            diffs = [d for d in diffs if d is not None]
            if diffs and min(diffs) > 24:
                published_status = REVIEW
                published_notes.append("Publication date signals differ by more than 24 hours.")
    rows.append(result("datePublished", published_status, " ".join(published_notes), rules["datePublished"]))

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
            "Accessible sitemap files were fully inspected but the preferred URL was not found. "
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
            "No accessible XML sitemap could be confirmed from robots.txt or common sitemap locations. "
            f"Endpoints attempted: {len(sitemap_result['checked'])}."
        )
    rows.append(result("Sitemap", ss, sf, rules["Sitemap"]))

    mobile_text = main_content_text(soup_of(mobile_r.text))
    sm = similarity(body_text, mobile_text)
    rows.append(result(
        "Mobile Content",
        PASS if sm >= .80 else REVIEW,
        f"Desktop and mobile main content similarity: {sm:.0%}.",
        rules["Mobile Content"],
    ))

    script_count = len(soup.find_all("script"))
    wc = word_count(body_text)
    if wc < 150 and script_count >= 20:
        jr = REVIEW
        jf = f"Only {wc} extracted words with {script_count} scripts; rendered content verification is recommended."
    else:
        jr = PASS
        jf = (
            f"{wc} meaningful article words were already present in initial HTML with {script_count} scripts. "
            "No obvious empty HTML shell pattern was detected."
        )
    rows.append(result("JavaScript Rendering", jr, jf, rules["JavaScript Rendering"]))

    resource_urls = extract_resource_urls(soup, desktop_r.url)
    mixed_content = [
        u for u in resource_urls
        if parsed.scheme == "https" and urlparse(u).scheme == "http"
    ]
    if parsed.scheme != "https":
        https_status = FAIL
        https_finding = f"Preferred page scheme is {parsed.scheme}, not HTTPS."
    elif mixed_content:
        https_status = REVIEW
        https_finding = (
            f"Preferred page uses HTTPS, but {len(mixed_content)} HTTP render resource(s) create potential mixed content. "
            f"Examples: {', '.join(mixed_content[:4])}."
        )
    else:
        https_status = PASS
        https_finding = "Preferred page and discovered render resources use HTTPS without detected mixed content."
    rows.append(result("HTTPS", https_status, https_finding, rules["HTTPS"]))

    if resource_validation is None:
        resource_validation = validate_url_set(
            resource_urls,
            timeout=RESOURCE_CHECK_TIMEOUT,
            workers=RESOURCE_CHECK_WORKERS,
        )

    resource_problems = validation_problem_examples(resource_validation)
    if not resource_urls:
        resource_status = REVIEW
        resource_finding = "No image, stylesheet, font preload or JavaScript resource URLs were discovered."
    elif resource_problems:
        resource_status = REVIEW
        resource_finding = (
            f"{len(resource_validation['checked'])} unique render resource URLs were requested. "
            f"{len(resource_validation['working'])} resolved successfully. "
            "Problems: " + "; ".join(resource_problems) + "."
        )
    else:
        resource_status = PASS
        resource_finding = (
            f"All {len(resource_validation['checked'])} unique image, stylesheet, font preload and JavaScript resource URLs resolved successfully."
        )
    rows.append(result("Broken Resources", resource_status, resource_finding, rules["Broken Resources"]))

    return rows


def audit_content(url, soup, body_text, focus_keyword="", secondary_keywords=None):
    rows = []
    rules = dict(CONTENT_RULES)
    secondary_keywords = secondary_keywords or []

    article_soup = main_content_node(soup)
    body_text = clean_text(article_soup)

    title = title_text(soup)
    h1 = page_primary_h1(soup)
    wc = word_count(body_text)
    target_topic = focus_keyword or title or h1

    intent_overlap = max(
        keyword_overlap(target_topic, body_text),
        semantic_overlap(target_topic, body_text),
    )
    if intent_overlap >= .65:
        s = PASS
    elif intent_overlap >= .35:
        s = REVIEW
    else:
        s = FAIL
    intent_label = f"focus keyword ‘{focus_keyword}’" if focus_keyword else "title topic"
    rows.append(result(
        "Search Intent",
        s,
        f"Meaning or terms from the {intent_label} are represented in the article at {intent_overlap:.0%} topic agreement.",
        rules["Search Intent"],
    ))

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

        if entity_heading_context_relevant(item["heading"], item["section"], target_topic):
            continue

        if heading_score < 0.20 and section_score < 0.35:
            weak_sections.append(item["heading"])

    if content_sections:
        weak_share = len(weak_sections) / len(content_sections)
        rel_status = FAIL if weak_share > 0.65 else REVIEW if weak_share > 0.45 else PASS
        rel_finding = (
            f"{len(weak_sections)} of {len(content_sections)} H2 to H4 sections remain weakly related "
            "after heading hierarchy, entity context and FAQ content analysis."
        )
        if weak_sections:
            rel_finding += " Weak sections: " + "; ".join(weak_sections[:6]) + "."
    else:
        rel_status = PASS
        rel_finding = "No H2 to H4 sections were available; no unrelated section pattern was detected."
    rows.append(result("Content Relevance", rel_status, rel_finding, rules["Content Relevance"]))

    thin_status = PASS if wc >= 600 else REVIEW if wc >= 300 else FAIL
    rows.append(result("Thin Content", thin_status, f"{wc:,} extracted meaningful article words.", rules["Thin Content"]))

    value_signals = {
        "tables": len(article_soup.find_all("table")),
        "lists": len(article_soup.find_all(["ul", "ol"])),
        "numbers": len(re.findall(r"\b\d+(?:[.,]\d+)?%?\b", body_text)),
        "headings": len(content_sections),
    }
    if wc >= 800 and (
        value_signals["tables"]
        or value_signals["numbers"] >= 12
        or value_signals["lists"] >= 3
    ):
        ov = PASS
        of = (
            f"Internal useful value signals: {value_signals['tables']} table(s), "
            f"{value_signals['lists']} list(s), {value_signals['numbers']} numeric references and "
            f"{value_signals['headings']} structured sections. "
            "External originality comparison is separate."
        )
    else:
        ov = REVIEW
        of = (
            "The page has limited internal evidence of added value. "
            f"Signals: {value_signals}. External or site comparison may still be required."
        )
    rows.append(result("Original Value", ov, of, rules["Original Value"]))

    factual_claims = non_market_factual_claim_examples(
        article_soup,
        limit=40,
    )
    factual_conflicts = non_market_factual_conflicts(
        factual_claims,
    )

    if factual_conflicts:
        factual_status = REVIEW
        factual_finding = (
            f"{len(factual_conflicts)} internal non market factual contradiction(s) found. "
            "Examples: "
            + " | ".join(
                f"{item['first']} <> {item['second']}"
                for item in factual_conflicts[:5]
            )
        )
        factual_action = " || ".join(
            f"Verify and correct the conflicting factual statements: {item['first']} <> {item['second']}"
            for item in factual_conflicts[:6]
        )
    else:
        factual_status = PASS
        factual_finding = (
            "No factual inconsistencies found in non market article information."
        )
        factual_action = ""

    rows.append(result(
        "Factual Accuracy",
        factual_status,
        factual_finding,
        rules["Factual Accuracy"],
        factual_action,
    ))

    year_contexts = contextual_old_years(body_text)
    risky_years = [item for item in year_contexts if item["sensitive"]]
    uncertain_years = [
        item for item in year_contexts
        if not item["sensitive"] and item["classification"] == "Context needs review"
    ]

    freshness_date = latest_editorial_datetime(soup)
    freshness_days = None
    if freshness_date is not None:
        freshness_days = max(
            0,
            (datetime.now(timezone.utc) - freshness_date).total_seconds() / 86400,
        )

    time_sensitive = looks_time_sensitive(body_text)

    if risky_years:
        od = REVIEW
        examples = " | ".join(
            f"{item['year']}: {item['sentence']}"
            for item in risky_years[:5]
        )
        odf = (
            f"{len(risky_years)} old year reference(s) occur inside time sensitive claims. "
            f"Examples: {examples}"
        )
    elif time_sensitive and freshness_days is not None and freshness_days > 365:
        od = REVIEW
        odf = (
            f"The article contains time sensitive information such as prices, rents, ROI, fees, routes or project status, "
            f"while the latest editorial date signal is about {freshness_days:.0f} days old "
            f"({freshness_date.isoformat()}). Verify current data."
        )
    elif time_sensitive and freshness_date is None:
        od = REVIEW
        odf = (
            "The article contains time sensitive information, but no reliable editorial publication or modification date "
            "was available to judge freshness."
        )
    elif uncertain_years:
        od = REVIEW
        examples = " | ".join(
            f"{item['year']}: {item['sentence']}"
            for item in uncertain_years[:4]
        )
        odf = f"Old year references need context review: {examples}"
    elif year_contexts:
        od = PASS
        examples = " | ".join(
            f"{item['year']}: {item['sentence']}"
            for item in year_contexts[:4]
        )
        odf = f"Old year references appear historical or contextual rather than stale current claims. Examples: {examples}"
    else:
        od = PASS
        odf = (
            "No stale year signal was found in the isolated article body."
            + (
                f" Latest editorial date signal is about {freshness_days:.0f} days old."
                if freshness_days is not None
                else ""
            )
        )
    if od == REVIEW:
        if time_sensitive:
            outdated_action = (
                "Refresh the current time sensitive data in this article: prices, rents, ROI, fees, routes and project status wherever present. "
                "Use the current approved Bayut or authoritative source, then update the article content and its editorial freshness signals only when a real change is made."
            )
        else:
            outdated_action = "Review the old year references shown in Result and either update the current claim or make the historical context explicit."
    else:
        outdated_action = ""

    rows.append(result(
        "Outdated Information",
        od,
        odf,
        rules["Outdated Information"],
        outdated_action,
    ))

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

    rows.append(result(
        "Keyword Use",
        kw_assessment["status"],
        f"Most repeated two word phrase: '{kw_assessment['gram']}' with {kw_assessment['count']} uses "
        f"({kw_assessment['density']:.1%}). {kw_assessment['reason']}{semantic_note}{target_note}",
        rules["Keyword Use"],
    ))

    sent_ratio, repeated_sents = repeated_sentence_ratio(body_text)
    para_ratio, repeated_paras = repeated_paragraph_ratio(article_soup)
    rep = max(sent_ratio, para_ratio)
    if rep >= .10:
        rp = FAIL
    elif rep >= .04:
        rp = REVIEW
    else:
        rp = PASS
    repetition_note = f"Estimated duplicate sentence or paragraph ratio: {rep:.1%}."
    if repeated_sents or repeated_paras:
        examples = (repeated_sents + repeated_paras)[:3]
        repetition_note += " Examples: " + " | ".join(x[:180] for x in examples) + "."
    rows.append(result("Repetition", rp, repetition_note, rules["Repetition"]))

    paragraphs = [
        p.get_text(" ", strip=True)
        for p in article_soup.find_all("p")
        if len(p.get_text(" ", strip=True)) >= 60
    ]
    if paragraphs:
        low_specific = sum(
            1
            for p in paragraphs
            if max(
                keyword_overlap(target_topic, p),
                semantic_overlap(target_topic, p),
            ) < .08
        )
        filler_share = low_specific / len(paragraphs)
    else:
        filler_share = 1

    filler_status = REVIEW if filler_share > .55 else PASS
    rows.append(result(
        "Generic / Filler Content",
        filler_status,
        f"{filler_share:.0%} of substantial paragraphs have very weak semantic and lexical relationship to the main topic. "
        "This is a review signal, not proof of filler.",
        rules["Generic / Filler Content"],
    ))

    tc = max(keyword_overlap(title, body_text), semantic_overlap(title, body_text))
    rows.append(result(
        "Title vs Content",
        PASS if tc >= .55 else REVIEW if tc >= .30 else FAIL,
        f"Title to body topic agreement: {tc:.0%}.",
        rules["Title vs Content"],
    ))

    hc = max(keyword_overlap(h1, body_text), semantic_overlap(h1, body_text)) if h1 else 0
    rows.append(result(
        "H1 vs Content",
        PASS if h1 and hc >= .55 else REVIEW if h1 else FAIL,
        f"H1 to body topic agreement: {hc:.0%}." if h1 else "H1 missing.",
        rules["H1 vs Content"],
    ))

    section_items = heading_sections(article_soup)
    if section_items:
        relevant = 0
        contextual = 0
        weak_examples = []
        detail_examples = []

        for item in section_items:
            heading_score = semantic_overlap(target_topic, item["heading"])
            section_score = semantic_overlap(target_topic, item["section"]) if item["section"] else 0.0

            if is_faq_heading(item["heading"]):
                is_relevant = faq_section_relevant(item["section"], target_topic)
                relevance_reason = "FAQ section context"
            elif entity_heading_context_relevant(item["heading"], item["section"], target_topic):
                is_relevant = True
                relevance_reason = "entity heading with related section context"
            else:
                is_relevant = heading_score >= 0.20 or section_score >= 0.45
                relevance_reason = "semantic heading or section overlap"

            if is_relevant:
                relevant += 1
                if heading_score < 0.20:
                    contextual += 1
                    if len(detail_examples) < 5:
                        detail_examples.append(
                            f"'{item['heading']}' accepted through {relevance_reason}; section topic overlap {section_score:.0%}."
                        )
            elif len(weak_examples) < 5:
                weak_examples.append(
                    f"'{item['heading']}' heading overlap {heading_score:.0%}, section overlap {section_score:.0%}"
                )

        hr = relevant / len(section_items)
        hstatus = PASS if hr >= 0.70 else REVIEW if hr >= 0.45 else FAIL
        hfind = (
            f"{relevant}/{len(section_items)} H2 to H4 sections are related to the main topic. "
            f"{contextual} section(s) were accepted through contextual relevance."
        )
        if detail_examples:
            hfind += " Context examples: " + " ".join(detail_examples)
        if weak_examples:
            hfind += " Weakest sections: " + "; ".join(weak_examples) + "."
    else:
        hstatus = REVIEW
        hfind = "No H2 to H4 headings were available for contextual heading relevance assessment."
    rows.append(result("Heading Relevance", hstatus, hfind, rules["Heading Relevance"]))

    intro_words = " ".join(tokenize(body_text)[:140])
    intro_overlap = max(
        keyword_overlap(target_topic, intro_words),
        semantic_overlap(target_topic, intro_words),
    )
    iq = PASS if intro_overlap >= .45 else REVIEW
    rows.append(result(
        "Introduction Quality",
        iq,
        f"Opening 140 word topic agreement: {intro_overlap:.0%}.",
        rules["Introduction Quality"],
    ))

    faq_pairs = faq_question_answer_pairs(article_soup)
    faq_headers = [h for h in headings if is_faq_heading(h)]
    if faq_headers or faq_pairs:
        short_answers = [
            item for item in faq_pairs
            if word_count(item["answer"]) < 15
        ]
        unrelated_answers = [
            item for item in faq_pairs
            if item["answer"]
            and max(
                semantic_overlap(target_topic, item["answer"]),
                keyword_overlap(target_topic, item["answer"]),
            ) < .12
        ]
        normalized_answers = [
            re.sub(r"\W+", " ", item["answer"].lower()).strip()
            for item in faq_pairs
            if item["answer"]
        ]
        duplicate_answers = len(normalized_answers) - len(set(normalized_answers))

        if not faq_pairs and faq_headers:
            fq = REVIEW
            ff = "FAQ heading detected but no question and answer pairs were extracted."
        elif short_answers or duplicate_answers >= 2 or len(unrelated_answers) > len(faq_pairs) / 2:
            fq = REVIEW
            ff = (
                f"{len(faq_pairs)} FAQ pair(s); {len(short_answers)} short or empty answer(s); "
                f"{duplicate_answers} duplicate answer occurrence(s); {len(unrelated_answers)} weakly related answer(s)."
            )
        else:
            fq = PASS
            ff = (
                f"{len(faq_pairs)} FAQ question and answer pair(s) checked. "
                "No empty, very short, heavily duplicated or predominantly unrelated FAQ answer pattern was detected."
            )
    else:
        fq = PASS
        ff = "No FAQ section detected; no FAQ quality issue to evaluate."
    rows.append(result("FAQ Quality", fq, ff, rules["FAQ Quality"]))

    super_claims = superlative_claim_assessment(article_soup, url)
    unsupported_hard = [
        item for item in super_claims
        if item["hard"] and not item["supported"]
    ]
    unsupported_soft = [
        item for item in super_claims
        if not item["hard"] and not item["supported"]
    ]

    if unsupported_hard:
        ss = REVIEW
        sf = (
            f"{len(super_claims)} superlative claim(s) detected. "
            f"{len(unsupported_hard)} objective or ranking superlative claim(s) lack nearby attribution or a source link. "
            "Examples: " + " | ".join(item["text"] for item in unsupported_hard[:4])
        )
    else:
        ss = PASS
        sf = (
            f"{len(super_claims)} superlative claim(s) detected. "
            "No hard ranking, cheapest, highest, lowest or most popular claim was found without nearby attribution or a source link."
        )
        if unsupported_soft:
            sf += (
                f" {len(unsupported_soft)} editorial soft superlative wording instance(s), such as best, "
                "were treated as editorial framing rather than automatically unsupported factual claims."
            )
    if unsupported_hard:
        super_actions = []
        for item in unsupported_hard[:8]:
            claim_text = item["text"]
            super_actions.append(
                compact_claim_action(
                    claim_text,
                    prefix="Support or rewrite"
                )
            )
        super_action = " || ".join(super_actions)
    else:
        super_action = ""

    rows.append(result(
        "Unsupported Superlatives",
        ss,
        sf,
        rules["Unsupported Superlatives"],
        super_action,
    ))

    source_claims = factual_claim_examples(article_soup, url, limit=40)
    supported = [item for item in source_claims if item.get("supported")]
    unsupported = [item for item in source_claims if not item.get("supported")]

    regulatory_terms = [
        "law", "regulation", "visa", "fee", "fees", "rule",
        "قانون", "قوانين", "رسوم", "تأشيرة", "تاشيرة",
    ]
    regulatory_unsourced = [
        item for item in unsupported
        if any(term in item["claim"].lower() for term in regulatory_terms)
    ]

    support_ratio = len(supported) / len(source_claims) if source_claims else 1.0

    if regulatory_unsourced:
        sq = REVIEW
        source_targets = regulatory_unsourced
        sf = (
            f"{len(source_claims)} concrete source sensitive statement(s) assessed; "
            f"{len(supported)} have nearby attribution or source links. "
            f"{len(regulatory_unsourced)} regulatory or fee statement(s) lack visible support. "
            "Unsupported examples: " + " | ".join(item["claim"] for item in source_targets[:6])
        )
    elif len(source_claims) >= 4 and support_ratio < .35:
        sq = REVIEW
        source_targets = unsupported
        sf = (
            f"{len(source_claims)} concrete source sensitive statement(s) assessed; only {len(supported)} "
            f"({support_ratio:.0%}) have nearby attribution or source links. "
            f"{len(unsupported)} statement(s) need stronger local sourcing. "
            "Unsupported examples: " + " | ".join(item["claim"] for item in source_targets[:6])
        )
    else:
        sq = PASS
        source_targets = []
        sf = (
            f"{len(source_claims)} concrete source sensitive statement(s) assessed; {len(supported)} "
            f"({support_ratio:.0%} if statements exist) have nearby visible attribution or source links. "
            "Source Quality is based on statement level support, not raw external link count."
        )

    if sq == REVIEW:
        source_actions = [
            compact_claim_action(item["claim"], prefix="Add source beside")
            for item in source_targets[:10]
        ]
        source_action = " || ".join(source_actions)
    else:
        source_action = ""

    rows.append(result(
        "Source Quality",
        sq,
        sf,
        rules["Source Quality"],
        source_action,
    ))

    conflicts = numeric_statement_conflicts(article_soup)
    percents = re.findall(r"\b\d+(?:\.\d+)?%", body_text)
    if conflicts:
        data_status = REVIEW
        data_finding = (
            f"{len(conflicts)} possible internal numeric contradiction(s) were detected where substantially the same statement "
            "appears with different values. Examples: "
            + " | ".join(
                f"{item['statement']} | previous values {item['previous_values']} | current values {item['current_values']}"
                for item in conflicts[:5]
            )
        )
        data_action = " || ".join(
            f"Check and correct: {item['statement']} | choose the verified value between previous {item['previous_values']} and current {item['current_values']}."
            for item in conflicts[:8]
        )
    else:
        data_status = PASS
        data_finding = (
            f"No repeated statement template with conflicting numeric values was detected. "
            f"{len(percents)} percentage reference(s) were found. "
            "This checks internal consistency only; external data verification remains part of Factual Accuracy."
        )
        data_action = ""

    rows.append(result(
        "Data Accuracy",
        data_status,
        data_finding,
        rules["Data Accuracy"],
        data_action,
    ))

    entities = entity_candidates(article_soup)
    near_duplicates = near_duplicate_entities(entities)

    if entities:
        entity_status = REVIEW
        entity_finding = (
            f"{len(entities)} normalized entity candidate(s) were extracted and require external or first party verification. "
            f"Examples: {', '.join(entities[:10])}."
        )

        if near_duplicates:
            duplicate_parts = []
            for item in near_duplicates[:5]:
                left_key = entity_similarity_key(item["left"])
                right_key = entity_similarity_key(item["right"])
                likely_typo = (
                    len(left_key.split()) == len(right_key.split())
                    and item["similarity"] >= 0.90
                )
                label = "possible typo" if likely_typo else "possible naming variation"
                duplicate_parts.append(
                    f"{item['left']} vs {item['right']} "
                    f"({item['similarity']:.0%} spelling similarity; {label})"
                )
            entity_finding += (
                " Possible near duplicate entity spellings should be checked: "
                + " | ".join(duplicate_parts)
                + "."
            )
        else:
            entity_finding += " No suspicious near duplicate entity spelling was detected internally."
    else:
        entity_status = PASS
        entity_finding = "No clear named entity candidate requiring separate verification was extracted."
    if entity_status == REVIEW:
        entity_actions = []
        if near_duplicates:
            for item in near_duplicates[:8]:
                entity_actions.append(
                    f"Verify official name and standardize this pair: {item['left']} vs {item['right']}."
                )
        else:
            for entity in entities[:10]:
                entity_actions.append(
                    f"Verify official first party name: {entity}."
                )
        entity_action = " || ".join(entity_actions)
    else:
        entity_action = ""

    rows.append(result(
        "Entity Accuracy",
        entity_status,
        entity_finding,
        rules["Entity Accuracy"],
        entity_action,
    ))

    sentences = re.split(r"(?<=[.!?؟])\s+", body_text)
    lens = [len(tokenize(s)) for s in sentences if len(tokenize(s)) >= 3]
    avg = sum(lens) / len(lens) if lens else 0
    malformed = sum(
        1 for s in sentences
        if len(s.strip()) > 180 and not re.search(r"[.!?؟]$", s.strip())
    )
    gr = REVIEW if avg > 32 or malformed >= 4 else PASS
    rows.append(result(
        "Grammar / Readability",
        gr,
        f"Average sentence length: {avg:.1f} words; {malformed} unusually long or potentially malformed sentence fragment(s). "
        "This is a readability heuristic, not a full grammar proof.",
        rules["Grammar / Readability"],
    ))

    placeholders = [
        p for p in [
            "lorem ipsum", "todo", "tbd", "[insert", "placeholder",
            "coming soon", "xx", "xxx",
        ]
        if p in body_text.lower()
    ]
    empty_heads = sum(
        1 for h in article_soup.find_all(re.compile(r"^h[1-6]$"))
        if not h.get_text(" ", strip=True)
    )
    _, repeated_paras = repeated_paragraph_ratio(article_soup)
    if placeholders:
        bc = FAIL
    elif empty_heads or repeated_paras:
        bc = REVIEW
    else:
        bc = PASS

    rows.append(result(
        "Broken Content",
        bc,
        f"Placeholder indicators: {placeholders if placeholders else 'none'}; "
        f"empty editorial headings: {empty_heads}; repeated substantial paragraph templates: {len(repeated_paras)}.",
        rules["Broken Content"],
    ))

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
        <div class="engine-proof"><strong>Engine {APP_VERSION}</strong><br>Build {ENGINE_BUILD}</div>
        """,
        unsafe_allow_html=True,
    )
    show_rules = st.checkbox("Show rule library", value=False)

    if st.button("Clear audit cache", use_container_width=True):
        for fn in [
            _robots_sitemaps_cached,
            _fetch_sitemap_document_cached,
            _find_url_in_sitemaps_cached,
            _rendered_hidden_inventory_cached,
            _probe_http_url_cached,
            _robots_access_cached,
        ]:
            try:
                fn.cache_clear()
            except Exception:
                pass

        for key in [
            "article_url",
            "focus_keyword",
            "secondary_keywords",
        ]:
            if key in st.session_state:
                # Keep user input; only network and analysis caches are cleared.
                pass

        st.success(f"{APP_VERSION} audit cache cleared.")

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
      <div style="display:flex;gap:8px;align-items:center"><div class="version-chip">{APP_VERSION}</div><div class="audit-pill">URL by URL audit</div></div>
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

        audit_status.write(f"{APP_VERSION}  1 of 4  Fetching Desktop, Mobile and Googlebot versions in parallel")
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

        page_internal_urls, external_urls = extract_page_links(soup, desktop_r.url)
        article_soup_for_links = main_content_node(soup)
        internal_urls = content_internal_link_urls(
            article_soup_for_links,
            desktop_r.url,
        )
        resource_urls = extract_resource_urls(soup, desktop_r.url)

        audit_status.write(
            "2 of 4  Running Spam, Content, Sitemap, Robots, Internal Link, External Link and Resource checks in parallel"
        )

        parallel_results = {}
        with ThreadPoolExecutor(max_workers=7) as executor:
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
                    validate_internal_url_set,
                    internal_urls,
                    INTERNAL_LINK_CHECK_TIMEOUT,
                    INTERNAL_LINK_CHECK_WORKERS,
                ): "Internal Links",
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
                executor.submit(
                    robots_access_result,
                    desktop_r.url,
                ): "Robots",
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
                elif label == "Internal Links":
                    audit_status.write(
                        f"Internal link validation completed for {len(parallel_results[label].get('checked', []))} link(s)"
                    )
                elif label == "External Links":
                    audit_status.write(
                        f"External link validation completed for {len(parallel_results[label].get('checked', []))} link(s)"
                    )
                elif label == "Robots":
                    audit_status.write(
                        f"robots.txt validation completed with HTTP {parallel_results[label].get('status')}"
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
        internal_validation = parallel_results["Internal Links"]
        external_validation = parallel_results["External Links"]
        resource_validation = parallel_results["Resources"]
        robots_txt_result = parallel_results["Robots"]

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
            internal_validation=internal_validation,
            external_validation=external_validation,
            resource_validation=resource_validation,
            robots_txt_result=robots_txt_result,
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
                Each rule shows its status, exactly what was found, the action you need to take, and why the system reached that result.
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
                        "Action Needed": row["Action Needed"],
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
                        "Action Needed": st.column_config.TextColumn(width="large"),
                        "Why": st.column_config.TextColumn(width="large"),
                    },
                )

        export = {
            "app_version": APP_VERSION,
            "engine_build": ENGINE_BUILD,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
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
            file_name="url_audit_v18_14_factual_accuracy_non_market_only.json",
            mime="application/json",
        )

        with st.expander("Important interpretation notes"):
            st.markdown(
                """
                This export was generated by the engine version displayed at the top of the app and stored in the JSON under app_version.

                Every rule receives one of three statuses: PASS, REVIEW or FAIL.

                Result shows exactly what the system found.

                Why explains the data and rule used to reach that status and result.

                When a rule cannot be fully verified from one URL, it can receive REVIEW and the Result explains what additional verification is required.

                The Googlebot check uses a Googlebot User Agent comparison. It does not reproduce Google's full rendering and indexing infrastructure.

                External plagiarism and entity accuracy may require external verification.

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
        (a, ICON_SHIELD, f'<span>Spam</span> {len(SPAM_RULES)} rules', 'Cloaking, redirects, hidden content, links, hacked content, scripts, UGC, malware and related spam risks.'),
        (b, ICON_SEARCH, f'<span>SEO</span> {len(SEO_RULES)} rules', 'Status, indexability, canonical, titles, headings, keyword stuffing, links, images, dates, sitemap, mobile, HTTPS and more.'),
        (c, ICON_DOC, f'<span>Content</span> {len(CONTENT_RULES)} rules', 'Intent, relevance, thinness, originality, freshness, repetition, FAQs, sourcing, accuracy and readability.'),
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
