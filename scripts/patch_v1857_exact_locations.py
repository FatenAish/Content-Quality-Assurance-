from pathlib import Path
import re

path = Path('app.py')
text = path.read_text(encoding='utf-8')

text = text.replace('APP_VERSION = "V18.56 CLEAR ISSUE SUMMARY"', 'APP_VERSION = "V18.57 CLEAR EXACT LOCATIONS"')
text = text.replace('ENGINE_BUILD = "2026.08.16.56"', 'ENGINE_BUILD = "2026.08.16.57"')
text = text.replace('file_name="url_audit_report_v18_56.xlsx"', 'file_name="url_audit_report_v18_57.xlsx"')

start = text.find('def deterministic_editorial_quality_issues(article_soup, limit=30):')
end = text.find('\ndef audit_content(', start)
if start < 0 or end < 0:
    raise SystemExit('editorial function boundary not found')

new_func = r'''def deterministic_editorial_quality_issues(article_soup, limit=30):
    """Return concise issues with short exact location examples, not full paragraphs."""
    if article_soup is None:
        return []

    issues = []
    blocks = []
    for node in article_soup.find_all(["p", "li"]):
        value = re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()
        if value:
            blocks.append((node, value))

    def short_context(text, start, end, pad=28):
        left = max(0, start - pad)
        right = min(len(text), end + pad)
        snippet = re.sub(r"\s+", " ", text[left:right]).strip()
        if left > 0:
            snippet = "…" + snippet
        if right < len(text):
            snippet += "…"
        return snippet

    def compact_examples(values, max_items=4):
        values = list(dict.fromkeys(v for v in values if v))
        if not values:
            return ""
        shown = values[:max_items]
        extra = len(values) - len(shown)
        result = "; ".join(f'“{x}”' for x in shown)
        if extra:
            result += f"; +{extra} more"
        return result

    space_examples = []
    duplicate_examples = []
    trailing_anchor_labels = []
    missing_bullet_examples = []

    for node, value in blocks:
        low = value.casefold()

        if "based on market analysis" in low and re.search(r"\bfor\s+the\s+abu\s+dhabi\s+sales\s*[.]?$", low):
            excerpt = short_context(value, max(0, len(value) - 85), len(value), pad=0)
            issues.append(f'Incomplete sentence — Found: “{excerpt}”')

        for m in re.finditer(r"%\s*,\s*[.!?]|[,;:]\s*[.!?]", value):
            duplicate_examples.append(short_context(value, m.start(), m.end(), pad=18))

        if "among the two" in low:
            issues.append('Grammar — Found: “among the two” → use “of the two”.')

        steady = list(re.finditer(r"\bsteady\b", low))
        if len(steady) >= 2:
            issues.append(f'Repeated wording — Found: “{short_context(value, steady[0].start(), steady[-1].end(), pad=22)}”')

        m = re.search(r"\bnotable\b[^.!?]{0,45}\bnoted\b|\bnoted\b[^.!?]{0,45}\bnotable\b", low)
        if m:
            issues.append(f'Repeated wording — Found: “{short_context(value, m.start(), m.end(), pad=18)}”')

        for m in re.finditer(r"\bfamily\s+friendly\b", value, flags=re.I):
            issues.append(f'Hyphenation — Found: “{m.group(0)}” → “family-friendly”.')
            break

        for m in re.finditer(r"\bhigh\s+net-worth\b", value, flags=re.I):
            issues.append(f'Hyphenation — Found: “{m.group(0)}” → “high-net-worth”.')
            break

        m = re.search(r"\b\d+\s+and\s+\d+-bedroom\b", value, flags=re.I)
        if m:
            issues.append(f'Parallel wording — Found: “{m.group(0)}” → use the “1- and 2-bedroom” form.')

        if node.name == "p" and low in {"ultra-luxury.", "ultra luxury."}:
            issues.append(f'Standalone fragment — Found: “{value}”')

        for m in re.finditer(r"\b([A-Za-z][A-Za-z’'\-]*)\s+([.,;:!?])", value):
            bad = m.group(0)
            fixed = f"{m.group(1)}{m.group(2)}"
            space_examples.append(f"{bad} → {fixed}")

    if duplicate_examples:
        issues.insert(0, f"Duplicate punctuation — Found: {compact_examples(duplicate_examples, 3)}")
    if space_examples:
        issues.insert(0, f"Space before punctuation — Found: {compact_examples(space_examples, 5)}")

    for listing in article_soup.find_all(["ul", "ol"]):
        items = listing.find_all("li", recursive=False)
        if len(items) < 2:
            continue
        texts = [re.sub(r"\s+", " ", li.get_text(" ", strip=True)).strip() for li in items]
        ended = [bool(re.search(r"[.!?]$", t)) for t in texts if t]
        if not ended or sum(ended) < max(2, len(ended) - 1):
            continue
        for t in texts:
            if t and not re.search(r"[.!?]$", t):
                missing_bullet_examples.append(t if len(t) <= 90 else "…" + t[-90:])

    if missing_bullet_examples:
        issues.append(f"Bullet punctuation — Missing ending punctuation at: {compact_examples(missing_bullet_examples, 3)}")

    for anchor in article_soup.find_all("a", href=True):
        raw = anchor.get_text("", strip=False)
        visible = re.sub(r"\s+", " ", raw or "").strip()
        if visible and raw and raw.rstrip() != raw:
            trailing_anchor_labels.append(visible)

    if trailing_anchor_labels:
        issues.append(f"Trailing whitespace in anchor text — Found in: {compact_examples(trailing_anchor_labels, 4)}")

    raw_text = article_soup.get_text("", strip=False)
    nbsp_positions = [m.start() for m in re.finditer("\xa0", raw_text)]
    if len(nbsp_positions) >= 3:
        nbsp_examples = []
        for pos in nbsp_positions[:3]:
            left = max(0, pos - 24)
            right = min(len(raw_text), pos + 25)
            snippet = raw_text[left:pos] + "⟦NBSP⟧" + raw_text[pos + 1:right]
            snippet = re.sub(r"[\r\n\t ]+", " ", snippet).strip()
            nbsp_examples.append(snippet)
        issues.append(
            f"Excess non-breaking spaces — {len(nbsp_positions)} found. Examples: {compact_examples(nbsp_examples, 3)}"
        )

    body = re.sub(r"\s+", " ", article_soup.get_text(" ", strip=True)).strip()
    if re.search(r"\bAl Rabdan\b", body) and re.search(r"(?<!Al )\bRabdan\b", body):
        issues.append('Naming inconsistency — Found both “Rabdan” and “Al Rabdan”.')
    if "The Marina" in body and "the Marina" in body:
        issues.append('Capitalisation inconsistency — Found both “The Marina” and “the Marina”.')

    family_matches = list(re.finditer(r"family[- ]friendly", body, flags=re.I))
    if len(family_matches) >= 2:
        for first, second in zip(family_matches, family_matches[1:]):
            if second.start() - first.start() <= 2500:
                first_ctx = short_context(body, first.start(), first.end(), pad=24)
                second_ctx = short_context(body, second.start(), second.end(), pad=24)
                issues.append(f'Repeated phrasing — “family-friendly” appears close together: “{first_ctx}”; “{second_ctx}”')
                break

    return _v1855_unique(issues, limit=limit)
'''

text = text[:start] + new_func + text[end:]
path.write_text(text, encoding='utf-8')
