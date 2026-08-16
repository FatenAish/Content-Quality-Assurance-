from pathlib import Path

path = Path("app.py")
text = path.read_text(encoding="utf-8")


def replace_once(old, new, label):
    global text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected 1 match, found {count}")
    text = text.replace(old, new, 1)


replace_once(
    'APP_VERSION = "V18.53 INTERNAL LINK INTENT FIX"\nENGINE_BUILD = "2026.08.16.53"',
    'APP_VERSION = "V18.54 EDITORIAL QA COVERAGE"\nENGINE_BUILD = "2026.08.16.54"',
    "version",
)

helper = r'''

def _qa_editorial_blocks(article_soup):
    """Return editorial paragraph/list blocks for deterministic QA checks."""
    blocks = []
    for node in article_soup.find_all(["p", "li"]):
        value = re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()
        if value:
            blocks.append((node, value))
    return blocks


def _qa_unique(items, limit=20):
    out = []
    seen = set()
    for item in items:
        value = re.sub(r"\s+", " ", str(item or "")).strip()
        key = value.casefold()
        if not value or key in seen:
            continue
        seen.add(key)
        out.append(value)
        if len(out) >= limit:
            break
    return out


def deterministic_data_quality_issues(article_soup, limit=12):
    """Fast local market-data wording checks with no external requests."""
    issues = []
    for _node, value in _qa_editorial_blocks(article_soup):
        if re.search(
            r"\b(?:notable|significant|moderate|strong|average)\s+%\s+"
            r"(?:increase|decrease|rise|drop|growth|decline)\b",
            value,
            flags=re.I,
        ) or re.search(
            r"(?<![\d.])%\s+(?:increase|decrease|rise|drop|growth|decline)\b",
            value,
            flags=re.I,
        ):
            issues.append(f'Missing percentage value: "{value[:240]}"')

        if re.search(
            r"\b(?:price|prices|rate|rates)\b.{0,70}\b"
            r"(?:rising|increasing|increased|rose|grown|grew)\s+by"
            r"(?:\s+an?\s+average\s+of)?\s+AED\s*[\d,]+(?:\.\d+)?\s+"
            r"(?:per\s+(?:square\s+foot|sq\.?\s*ft\.?)|psf)\b",
            value,
            flags=re.I,
        ):
            issues.append(
                f'Possible change/current-value wording mismatch ("by" vs "to"): "{value[:240]}"'
            )

        match = re.search(
            r"\bprices?\b.{0,55}\b(?:rising|increasing|increased|rose|climbed)\s+to\s+"
            r"AED\s*([\d,]+(?:\.\d+)?)\b",
            value,
            flags=re.I,
        )
        if match:
            try:
                amount = float(match.group(1).replace(",", ""))
            except Exception:
                amount = 0
            tail = value[match.start(): min(len(value), match.end() + 45)]
            has_unit = bool(re.search(
                r"(?:per\s+(?:square\s+foot|sq\.?\s*ft\.?)|sq\.?\s*ft\.?|psf)",
                tail,
                flags=re.I,
            ))
            if 300 <= amount <= 5000 and not has_unit:
                issues.append(
                    f'Possible missing price unit (for example, per sq. ft.): "{value[:240]}"'
                )

        if len(issues) >= limit:
            break
    return _qa_unique(issues, limit=limit)


def authoritative_review_claims(article_soup, limit=10):
    """Surface financing and visa eligibility claims for authoritative verification."""
    issues = []
    for _node, value in _qa_editorial_blocks(article_soup):
        for sentence in re.split(r"(?<=[.!?])\s+", value):
            sentence = sentence.strip()
            if len(sentence) < 20:
                continue
            low = sentence.casefold()

            if (
                re.search(r"\b\d{1,3}(?:\.\d+)?%\b", sentence)
                and re.search(
                    r"\b(?:financing|finance|mortgage|loan|ltv|loan-to-value|off-plan)\b",
                    low,
                )
            ):
                issues.append(
                    "Financing percentage/scope needs authoritative verification and clear eligibility wording: "
                    f'"{sentence[:260]}"'
                )

            if (
                re.search(r"\b(?:golden visa|visa|residency|residence visa)\b", low)
                and re.search(
                    r"\b(?:down[ -]?payment|minimum|threshold|eligible|eligibility|required|requirement|"
                    r"removed|removal|waived|no longer|qualify|qualification)\b",
                    low,
                )
            ):
                issues.append(
                    "Visa/residency eligibility or down-payment claim needs current official verification: "
                    f'"{sentence[:260]}"'
                )

            if len(issues) >= limit:
                break
        if len(issues) >= limit:
            break
    return _qa_unique(issues, limit=limit)


def deterministic_editorial_quality_issues(article_soup, limit=24):
    """High-confidence grammar, punctuation and CMS-formatting checks."""
    issues = []
    blocks = _qa_editorial_blocks(article_soup)

    for node, value in blocks:
        if re.search(r"\s+\.", value):
            issues.append(
                f'Space before full stop / potentially malformed sentence: "{value[:220]}"'
            )
        if re.search(r"%,\.|,\.(?!\d)|\.\.|!!|\?\?", value):
            issues.append(f'Duplicate or conflicting punctuation: "{value[:220]}"')

        if re.search(r"\bamong\s+the\s+two\b", value, flags=re.I):
            issues.append(
                f'Use "of the two" or "between the two" instead of "among the two": "{value[:220]}"'
            )

        if re.search(r"\bfamily\s+friendly\s+[A-Za-z]", value, flags=re.I):
            issues.append(
                f'Compound modifier needs hyphenation ("family-friendly"): "{value[:220]}"'
            )

        if re.search(r"\bhigh\s+net-worth\s+[A-Za-z]", value, flags=re.I):
            issues.append(
                f'Compound modifier needs hyphenation ("high-net-worth"): "{value[:220]}"'
            )

        if re.search(r"\b(?:The\s+)?\d+\s+and\s+\d+-bedroom\b", value, flags=re.I):
            issues.append(
                f'Parallel bedroom-range style should use a suspended hyphen (for example, "1- and 2-bedroom"): "{value[:220]}"'
            )

        for sentence in re.split(r"(?<=[.!?])\s+", value):
            if len(sentence) > 260:
                continue
            if re.search(r"\bsteady\b.{0,120}\bsteady\b", sentence, flags=re.I):
                issues.append(
                    f'Repeated wording in the same sentence ("steady"): "{sentence[:220]}"'
                )
            if re.search(r"\bnotable\b.{0,90}\bnoted\b", sentence, flags=re.I):
                issues.append(
                    f'Repetitive wording ("notable" / "noted"): "{sentence[:220]}"'
                )

        if node.name == "p":
            words = re.findall(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)*", value)
            if (
                1 <= len(words) <= 3
                and len(value) >= 5
                and re.search(r"[.!?]$", value)
                and value.casefold() not in {"read more.", "learn more.", "find out more."}
            ):
                issues.append(
                    f'Very short standalone paragraph may be a fragment or misplaced heading: "{value}"'
                )

        if len(issues) >= limit:
            break

    for list_node in article_soup.find_all(["ul", "ol"]):
        items = []
        for li in list_node.find_all("li", recursive=False):
            txt = re.sub(r"\s+", " ", li.get_text(" ", strip=True)).strip()
            if txt:
                items.append(txt)
        if len(items) < 3:
            continue
        punctuated = [bool(re.search(r"[.!?;:]$", x)) for x in items]
        if sum(punctuated) >= 2 and sum(punctuated) / len(items) >= 0.60:
            for txt, has_punct in zip(items, punctuated):
                if not has_punct and len(re.findall(r"\w+", txt)) >= 7:
                    issues.append(
                        f'List punctuation is inconsistent with neighbouring bullets: "{txt[:220]}"'
                    )

    for anchor in article_soup.find_all("a", href=True):
        if not is_inline_editorial_anchor(anchor):
            continue
        raw = anchor.get_text("", strip=False)
        if not raw or "\n" in raw or "\r" in raw:
            continue
        if raw.endswith((" ", "\xa0")) and raw.strip():
            issues.append(f'Trailing whitespace inside anchor text: "{raw.strip()}"')
        if raw.startswith((" ", "\xa0")) and raw.strip():
            issues.append(f'Leading whitespace inside anchor text: "{raw.strip()}"')

    nbsp_count = sum(
        str(node).count("\xa0") for node in article_soup.find_all(string=True)
    )
    if nbsp_count >= 2:
        issues.append(
            f'CMS formatting contains {nbsp_count} non-breaking space character(s); review for inconsistent/double spacing.'
        )

    body_text = re.sub(r"\s+", " ", article_soup.get_text(" ", strip=True)).strip()

    al_names = []
    for match in re.finditer(r"\bAl\s+([A-Z][A-Za-z'-]{5,})\b", body_text):
        name = match.group(1)
        if name not in al_names:
            al_names.append(name)
    for name in al_names[:30]:
        if re.search(rf"(?<!Al )\b{re.escape(name)}\b(?!\s+[A-Z])", body_text):
            issues.append(
                f'Possible naming inconsistency: both "Al {name}" and standalone "{name}" appear; standardise if they refer to the same place.'
            )

    family_positions = [
        match.start()
        for match in re.finditer(r"\bfamily-friendly\b", body_text, flags=re.I)
    ]
    if any((b - a) <= 260 for a, b in zip(family_positions, family_positions[1:])):
        issues.append(
            'The phrase "family-friendly" is repeated very close together; consider varying the wording.'
        )

    if (
        re.search(r"\bThe\s+Marina\b", body_text)
        and re.search(r"\bthe\s+Marina\b", body_text)
    ):
        issues.append(
            'Capitalisation variant detected: "The Marina" and "the Marina"; standardise the preferred proper-name styling.'
        )

    return _qa_unique(issues, limit=limit)

'''

replace_once(
    "def numeric_statement_conflicts(article_soup):",
    helper + "def numeric_statement_conflicts(article_soup):",
    "insert helpers",
)

source_marker = '''    rows.append(result(\n        "Source Quality",\n        sq,\n        sf,'''
source_insert = '''    authoritative_claim_issues = authoritative_review_claims(article_soup)\n    if authoritative_claim_issues:\n        sq = REVIEW\n        extra_source = (\n            "High-stakes claim(s) require authoritative verification:\\n"\n            + "\\n".join(\n                f"{index}: {item}"\n                for index, item in enumerate(authoritative_claim_issues[:8], start=1)\n            )\n        )\n        if sf == "No official source quality issues found.":\n            sf = extra_source\n        else:\n            sf = sf + "\\n" + extra_source\n        extra_actions = "\\n".join(\n            f"{index}: Verify scope and wording against a current official authority, lender or first-party developer source."\n            for index, _item in enumerate(authoritative_claim_issues[:8], start=1)\n        )\n        source_action = (source_action + "\\n" + extra_actions).strip()\n\n    rows.append(result(\n        "Source Quality",\n        sq,\n        sf,'''
replace_once(source_marker, source_insert, "source supplement")

data_marker = '''    rows.append(result(\n        "Data Accuracy",\n        data_status,\n        data_finding,'''
data_insert = '''    deterministic_data_issues = deterministic_data_quality_issues(article_soup)\n    if deterministic_data_issues:\n        data_status = REVIEW\n        extra_data = (\n            "Additional market-data wording/format issue(s):\\n"\n            + "\\n".join(\n                f"{index}: {item}"\n                for index, item in enumerate(deterministic_data_issues[:10], start=1)\n            )\n        )\n        if data_finding == "No internal numeric contradictions found within the same article context.":\n            data_finding = extra_data\n        else:\n            data_finding = data_finding + "\\n" + extra_data\n        extra_data_actions = "\\n".join(\n            f"{index}: Verify the value, unit and change wording against the article table/source."\n            for index, _item in enumerate(deterministic_data_issues[:10], start=1)\n        )\n        data_action = (data_action + "\\n" + extra_data_actions).strip()\n\n    rows.append(result(\n        "Data Accuracy",\n        data_status,\n        data_finding,'''
replace_once(data_marker, data_insert, "data supplement")

grammar_old = '''    gr = REVIEW if avg > 32 or malformed >= 4 else PASS\n    rows.append(result(\n        "Grammar / Readability",\n        gr,\n        f"Average sentence length: {avg:.1f} words; {malformed} unusually long or potentially malformed sentence fragment(s). "\n        "This is a readability heuristic, not a full grammar proof.",\n        rules["Grammar / Readability"],\n    ))'''
grammar_new = '''    editorial_quality_issues = deterministic_editorial_quality_issues(article_soup)\n    gr = REVIEW if avg > 32 or malformed >= 4 or editorial_quality_issues else PASS\n    grammar_finding = (\n        f"Average sentence length: {avg:.1f} words; {malformed} unusually long or potentially malformed sentence fragment(s). "\n        "Deterministic punctuation, hyphenation, fragment, CMS-spacing and local repetition checks were also run."\n    )\n    if editorial_quality_issues:\n        grammar_finding += (\n            "\\nSpecific issue(s):\\n"\n            + "\\n".join(\n                f"{index}: {item}"\n                for index, item in enumerate(editorial_quality_issues[:20], start=1)\n            )\n        )\n    rows.append(result(\n        "Grammar / Readability",\n        gr,\n        grammar_finding,\n        rules["Grammar / Readability"],\n    ))'''
replace_once(grammar_old, grammar_new, "grammar supplement")

text = text.replace(
    '("Grammar / Readability", "REVIEW when sentence structure is consistently difficult to read or text is obviously malformed."),',
    '("Grammar / Readability", "REVIEW malformed sentences plus high-confidence punctuation, hyphenation, fragment, spacing, naming-variant and close-repetition issues in editorial copy."),',
    1,
)
text = text.replace(
    '("Source Quality", "Check only claims that depend on an official authority or regulation. Examples include laws, government eligibility requirements, visas, permits, licences, official fees, fines and mandatory thresholds. Do not flag project specifications, property details, distances, amenities, unit counts, market data, investment commentary or ordinary descriptive information."),',
    '("Source Quality", "Check claims that depend on an official authority or eligibility rule, including visas and high-stakes financing percentages/scope. Require authoritative verification for these claims; ordinary market commentary remains excluded."),',
    1,
)

path.write_text(text, encoding="utf-8")
