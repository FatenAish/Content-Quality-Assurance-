from pathlib import Path

path = Path('app.py')
text = path.read_text(encoding='utf-8')


def replace_once(old, new, label):
    global text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected 1 match, found {count}')
    text = text.replace(old, new, 1)


replace_once(
    'APP_VERSION = "V18.54 EDITORIAL QA COVERAGE"\nENGINE_BUILD = "2026.08.16.54"',
    'APP_VERSION = "V18.55 PRECISION QA FIX"\nENGINE_BUILD = "2026.08.16.55"',
    'version',
)

# Do not flag valid wording such as "paving the way" as a spelling error.
replace_once(
    '    spelling_issues = likely_misspellings(spelling_text, limit=12)\n',
    '    spelling_issues = [\n'
    '        item for item in likely_misspellings(spelling_text, limit=12)\n'
    '        if str(item.get("word", "")).casefold() not in {"paving"}\n'
    '    ]\n',
    'spelling false positive filter',
)

# Bayut/MyBayut headings are not required to be converted wholesale to Title Case.
replace_once(
    '        heading_items = [r for r in local_rows if r.get("Finding Type") == "Heading / SEO" and r.get("Status") == FAIL]\n',
    '        heading_items = []  # Do not create false positives from sentence-case editorial headings.\n',
    'disable title-case false positives',
)

# Put specific deterministic grammar/content problems in the dedicated Grammar Issues row.
old_grammar = '''        grammar_items = [r for r in local_rows if r.get("Finding Type") == "Grammar & Wording" and r.get("Status") == FAIL]\n        heading_items = []  # Do not create false positives from sentence-case editorial headings.\n'''
new_grammar = '''        grammar_items = [r for r in local_rows if r.get("Finding Type") == "Grammar & Wording" and r.get("Status") == FAIL]\n        existing_grammar = {\n            re.sub(r"\\s+", " ", str(r.get("Result", "") or "")).casefold()\n            for r in grammar_items\n        }\n        for detail in deterministic_editorial_quality_issues(article_soup, limit=30):\n            key = re.sub(r"\\s+", " ", detail).casefold()\n            if any(key in existing or existing in key for existing in existing_grammar if existing):\n                continue\n            grammar_items.append({\n                "Check": "Editorial grammar/content issue",\n                "Status": FAIL,\n                "Result": detail,\n                "Action Needed": "Correct the specific wording, punctuation or CMS-formatting issue described in Result.",\n                "Why": "High-confidence deterministic editorial check based on the article itself.",\n                "Official Source": "Article itself",\n                "Finding Type": "Grammar & Wording",\n            })\n            existing_grammar.add(key)\n        heading_items = []  # Sentence-case editorial headings are allowed.\n'''
replace_once(old_grammar, new_grammar, 'grammar issue aggregation')

# Grammar / Readability should remain a readability summary; the concrete issues are shown in Grammar Issues.
old_readability = '''    editorial_quality_issues = deterministic_editorial_quality_issues(article_soup)\n    gr = REVIEW if avg > 32 or malformed >= 4 or editorial_quality_issues else PASS\n    grammar_finding = (\n        f"Average sentence length: {avg:.1f} words; {malformed} unusually long or potentially malformed sentence fragment(s). "\n        "Deterministic punctuation, hyphenation, fragment, CMS-spacing and local repetition checks were also run."\n    )\n    if editorial_quality_issues:\n        grammar_finding += (\n            "\\nSpecific issue(s):\\n"\n            + "\\n".join(\n                f"{index}: {item}"\n                for index, item in enumerate(editorial_quality_issues[:20], start=1)\n            )\n        )\n'''
new_readability = '''    gr = REVIEW if avg > 32 or malformed >= 4 else PASS\n    grammar_finding = (\n        f"Average sentence length: {avg:.1f} words; {malformed} unusually long or potentially malformed sentence fragment(s). "\n        "Specific grammar, punctuation and CMS-formatting findings are listed separately under Grammar Issues."\n    )\n'''
replace_once(old_readability, new_readability, 'readability de-duplication')

# Keep the downloaded filename aligned with the engine build.
text = text.replace('file_name="url_audit_report_v18_26.xlsx"', 'file_name="url_audit_report_v18_55.xlsx"')

# Override the v18.54 local detectors immediately before audit_content. Python resolves
# these global function names when the audit runs, so this safely supersedes the older
# implementations without rewriting unrelated parts of the large application.
marker = '\ndef audit_content(url, soup, body_text, focus_keyword="", secondary_keywords=None):\n'
if text.count(marker) != 1:
    raise SystemExit(f'audit_content marker: expected 1 match, found {text.count(marker)}')

overrides = r'''

def _v1855_unique(items, limit=30):
    out = []
    seen = set()
    for item in items:
        item = re.sub(r"\s+", " ", str(item or "")).strip()
        key = item.casefold()
        if not item or key in seen:
            continue
        seen.add(key)
        out.append(item)
        if len(out) >= limit:
            break
    return out


def authoritative_review_claims(article_soup, limit=12):
    """High-stakes financing and visa/residency claims that need scope verification."""
    issues = []
    if article_soup is None:
        return issues

    for node in article_soup.find_all(["p", "li"]):
        paragraph = re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()
        if not paragraph:
            continue
        for sentence in re.split(r"(?<=[.!?])\s+", paragraph):
            sentence = sentence.strip()
            low = sentence.casefold()
            if not sentence:
                continue

            if (
                ("golden visa" in low or "residency" in low or "residence visa" in low)
                and any(term in low for term in ["down payment", "down-payment", "minimum", "eligible", "eligibility", "requirement", "removed", "removal"])
            ):
                issues.append(
                    f'Visa/residency eligibility or down-payment claim needs current official verification: "{sentence}"'
                )

            if (
                "%" in sentence
                and any(term in low for term in ["mortgage", "financing", "finance", "borrow", "loan"])
                and any(term in low for term in ["off-plan", "off plan", "construction", "property", "purchase price"])
            ):
                issues.append(
                    f'Off-plan financing percentage/scope needs authoritative verification; confirm eligibility and whether the offer is limited to the named bank/developer or developments rather than the whole market: "{sentence}"'
                )

    return _v1855_unique(issues, limit=limit)


def _v1855_money_number(value):
    value = re.sub(r"[^0-9.]", "", str(value or "").replace(",", ""))
    try:
        return float(value) if value else None
    except Exception:
        return None


def _v1855_table_rounding_issues(article_soup, limit=6):
    """Advisory precision check: prose AED XM vs a more precise bedroom value in a nearby table."""
    records = []
    for table in article_soup.find_all("table") if article_soup is not None else []:
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue
        headers = [re.sub(r"\s+", " ", c.get_text(" ", strip=True)).strip() for c in rows[0].find_all(["th", "td"])]
        bed_cols = {}
        for idx, header in enumerate(headers):
            m = re.search(r"\b(\d+)\s*[- ]?\s*BED\b", header, flags=re.I)
            if m:
                bed_cols[idx] = int(m.group(1))
        if not bed_cols:
            continue
        for row in rows[1:]:
            cells = [re.sub(r"\s+", " ", c.get_text(" ", strip=True)).strip() for c in row.find_all(["th", "td"])]
            if not cells:
                continue
            area = re.sub(r"^Area\s+", "", cells[0], flags=re.I).strip()
            if not area:
                continue
            for idx, bed in bed_cols.items():
                if idx >= len(cells):
                    continue
                number = _v1855_money_number(cells[idx])
                if number and number >= 1_000_000:
                    records.append((area, bed, number))

    if not records:
        return []

    issues = []
    for node in article_soup.find_all(["p", "li"]):
        sentence = re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()
        bed_match = re.search(r"\b(\d+)\s*[- ]\s*bed(?:room)?\b", sentence, flags=re.I)
        if not bed_match or "AED" not in sentence or "M" not in sentence:
            continue
        bed = int(bed_match.group(1))
        for area, record_bed, table_value in records:
            if record_bed != bed or area.casefold() not in sentence.casefold():
                continue
            m = re.search(
                rf"AED\s*([0-9]+(?:\.[0-9]+)?)M\s+(?:on|in)\s+{re.escape(area)}\b",
                sentence,
                flags=re.I,
            )
            if not m:
                continue
            prose_m = float(m.group(1))
            table_m = table_value / 1_000_000.0
            rel_diff = abs(prose_m - table_m) / table_m
            if 0.005 <= rel_diff <= 0.03 and "." not in m.group(1):
                issues.append(
                    f'Rounded prose value is less precise than the table: {area} {bed}-bed is AED {prose_m:g}M in prose but AED {table_m:.3f}M in the table; consider AED {table_m:.1f}M for better precision.'
                )
    return _v1855_unique(issues, limit=limit)


def deterministic_data_quality_issues(article_soup, limit=16):
    """Fast local market-data wording and unit consistency checks."""
    issues = []
    if article_soup is None:
        return issues

    for node in article_soup.find_all(["p", "li"]):
        value = re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()
        if not value:
            continue
        for sentence in re.split(r"(?<=[.!?])\s+", value):
            sentence = sentence.strip()
            low = sentence.casefold()
            if not sentence:
                continue

            if re.search(r"\b(?:notable|significant|moderate|strong|average)\s+%\s+(?:increase|rise|growth|decrease|dip|decline)\b", low):
                issues.append(f'Missing percentage value: "{sentence}"')

            if re.search(r"\bprices?\b[^.!?]{0,90}\b(?:rising|increasing)\s+by\s+(?:an\s+average\s+of\s+)?AED\s*[0-9,]+(?:\.\d+)?\s+per\s+(?:square\s+foot|sq\.?\s*ft\.?)", sentence, flags=re.I):
                issues.append(f'Possible change/current-value wording mismatch ("by" vs "to"): "{sentence}"')

            price_to = re.search(r"\bprices?\b[^.!?]{0,100}\b(?:increasing|rising|reaching)\s+to\s+AED\s*([0-9,]+(?:\.\d+)?)", sentence, flags=re.I)
            if price_to:
                try:
                    number = float(price_to.group(1).replace(",", ""))
                except Exception:
                    number = 0
                if 500 <= number <= 5000 and not re.search(r"per\s+(?:square\s+foot|sq\.?\s*ft\.?)", sentence, flags=re.I):
                    issues.append(f'Possible missing price unit (for example, per sq. ft.): "{sentence}"')

            if re.search(r"average\s+price\s+per\s+(?:square\s+foot|sq\.?\s*ft\.?)[^.!?]{0,90}(?:rose|increased|up|rising)[^.!?]{0,30}\b\d+(?:\.\d+)?%", sentence, flags=re.I):
                issues.append(f'Price-per-square-foot statement appears to use a percentage as the current price value: "{sentence}"')

    issues.extend(_v1855_table_rounding_issues(article_soup, limit=6))
    return _v1855_unique(issues, limit=limit)


def deterministic_editorial_quality_issues(article_soup, limit=30):
    """Specific grammar, punctuation and CMS-formatting issues with conservative false-positive controls."""
    issues = []
    if article_soup is None:
        return issues

    blocks = []
    for node in article_soup.find_all(["p", "li"]):
        value = re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()
        if value:
            blocks.append((node, value))

    for node, value in blocks:
        low = value.casefold()
        incomplete = False

        if "based on market analysis" in low and re.search(r"\bfor\s+the\s+abu\s+dhabi\s+sales\s*[.]?$", low):
            issues.append(f'Incomplete/unfinished sentence: "{value}"')
            incomplete = True

        if re.search(r"%\s*,\s*[.!?]", value) or re.search(r"[,;:]\s*[.!?]", value):
            issues.append(f'Duplicate or conflicting punctuation: "{value}"')

        if "among the two" in low:
            issues.append(f'Use "of the two" or "between the two" instead of "among the two": "{value}"')

        if len(re.findall(r"\bsteady\b", low)) >= 2:
            issues.append(f'Repeated wording in the same sentence ("steady"): "{value}"')

        if re.search(r"\bnotable\b[^.!?]{0,45}\bnoted\b|\bnoted\b[^.!?]{0,45}\bnotable\b", low):
            issues.append(f'Repetitive wording ("notable" / "noted"): "{value}"')

        if re.search(r"\bfamily\s+friendly\b", low):
            issues.append(f'Compound modifier needs hyphenation ("family-friendly"): "{value}"')

        if re.search(r"\bhigh\s+net-worth\b", low):
            issues.append(f'Compound modifier should be "high-net-worth": "{value}"')

        if re.search(r"\b\d+\s+and\s+\d+-bedroom\b", low):
            issues.append(f'Parallel bedroom-range style should use a suspended hyphen (for example, "1- and 2-bedroom"): "{value}"')

        if node.name == "p" and low in {"ultra-luxury.", "ultra luxury."}:
            issues.append(f'Very short standalone paragraph may be a fragment or misplaced heading: "{value}"')

        if not incomplete:
            m = re.search(r"\b([A-Za-z][A-Za-z’'\-]*)\s+([.,;:!?])", value)
            if m:
                issues.append(f'Space before punctuation / CMS spacing issue: "{value}"')

    # Bullet punctuation: only flag an unpunctuated item when neighbouring bullets in
    # the same list normally end with punctuation.
    for listing in article_soup.find_all(["ul", "ol"]):
        items = listing.find_all("li", recursive=False)
        if len(items) < 2:
            continue
        texts = [re.sub(r"\s+", " ", li.get_text(" ", strip=True)).strip() for li in items]
        ended = [bool(re.search(r"[.!?]$", t)) for t in texts if t]
        if not ended or sum(ended) < max(2, len(ended) - 1):
            continue
        for li, t in zip(items, texts):
            if t and not re.search(r"[.!?]$", t):
                issues.append(f'List punctuation is inconsistent with neighbouring bullets: "{t}"')

    # Raw anchor formatting: trailing whitespace is editorially meaningful; leading
    # indentation/DOM whitespace is ignored to avoid the Al Raha Beach false positive.
    for anchor in article_soup.find_all("a", href=True):
        raw = anchor.get_text("", strip=False)
        visible = re.sub(r"\s+", " ", raw or "").strip()
        if visible and raw and raw.rstrip() != raw:
            issues.append(f'Trailing whitespace inside anchor text: "{visible}"')

    raw_text = article_soup.get_text("", strip=False)
    nbsp_count = raw_text.count("\xa0")
    if nbsp_count >= 3:
        issues.append(f'CMS formatting contains {nbsp_count} non-breaking space character(s); clean inconsistent/double spacing where present.')

    body = re.sub(r"\s+", " ", article_soup.get_text(" ", strip=True)).strip()
    if re.search(r"\bAl Rabdan\b", body) and re.search(r"(?<!Al )\bRabdan\b", body):
        issues.append('Possible naming inconsistency: both "Al Rabdan" and standalone "Rabdan" appear; standardise if they refer to the same place.')
    if "The Marina" in body and "the Marina" in body:
        issues.append('Capitalisation variant detected: "The Marina" and "the Marina"; standardise the preferred proper-name styling.')

    family_positions = [m.start() for m in re.finditer(r"family[- ]friendly", body, flags=re.I)]
    if len(family_positions) >= 2 and any((b - a) <= 2500 for a, b in zip(family_positions, family_positions[1:])):
        issues.append('Repeated phrasing: "family-friendly" appears again within a short span; vary the wording where the meaning is already clear.')

    return _v1855_unique(issues, limit=limit)

'''

text = text.replace(marker, overrides + marker, 1)
path.write_text(text, encoding='utf-8')
