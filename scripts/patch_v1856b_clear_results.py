from pathlib import Path
import re

path = Path('app.py')
text = path.read_text(encoding='utf-8')

text = text.replace('APP_VERSION = "V18.55 PRECISION QA FIX"', 'APP_VERSION = "V18.56 CLEAR ISSUE SUMMARY"')
text = text.replace('ENGINE_BUILD = "2026.08.16.55"', 'ENGINE_BUILD = "2026.08.16.56"')

new_func = r'''def deterministic_editorial_quality_issues(article_soup, limit=30):
    """Return short grouped editorial issues instead of repeating full sentences."""
    if article_soup is None:
        return []

    issues = []
    blocks = []
    for node in article_soup.find_all(["p", "li"]):
        value = re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()
        if value:
            blocks.append((node, value))

    space_before_punct = 0
    duplicate_punct = 0
    trailing_anchor_labels = []
    missing_bullet_punct = 0

    for node, value in blocks:
        low = value.casefold()

        if "based on market analysis" in low and re.search(r"\bfor\s+the\s+abu\s+dhabi\s+sales\s*[.]?$", low):
            issues.append("Incomplete sentence — An unfinished sentence was detected in the market-analysis text.")

        if re.search(r"%\s*,\s*[.!?]", value) or re.search(r"[,;:]\s*[.!?]", value):
            duplicate_punct += 1

        if "among the two" in low:
            issues.append('Grammar — Use "of the two" instead of "among the two".')
        if len(re.findall(r"\bsteady\b", low)) >= 2:
            issues.append('Repeated wording — "steady" is repeated in the same sentence.')
        if re.search(r"\bnotable\b[^.!?]{0,45}\bnoted\b|\bnoted\b[^.!?]{0,45}\bnotable\b", low):
            issues.append('Repeated wording — "notable" and "noted" are used too close together.')
        if re.search(r"\bfamily\s+friendly\b", low):
            issues.append('Hyphenation — "family friendly" should be "family-friendly".')
        if re.search(r"\bhigh\s+net-worth\b", low):
            issues.append('Hyphenation — "high net-worth" should be "high-net-worth".')
        if re.search(r"\b\d+\s+and\s+\d+-bedroom\b", low):
            issues.append('Parallel wording — Use the "1- and 2-bedroom" form.')
        if node.name == "p" and low in {"ultra-luxury.", "ultra luxury."}:
            issues.append('Standalone fragment — "Ultra-luxury." should be removed or turned into a proper heading.')
        if re.search(r"\b[A-Za-z][A-Za-z’'\-]*\s+[.,;:!?]", value):
            space_before_punct += 1

    if duplicate_punct:
        issues.insert(0, "Duplicate punctuation — Conflicting punctuation such as ',.' was detected.")
    if space_before_punct == 1:
        issues.insert(0, "Space before punctuation — One sentence contains an unnecessary space before punctuation.")
    elif space_before_punct > 1:
        issues.insert(0, "Space before punctuation — Multiple sentences contain unnecessary spaces before full stops or commas.")

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
                missing_bullet_punct += 1

    if missing_bullet_punct == 1:
        issues.append("Bullet punctuation — One bullet is missing ending punctuation.")
    elif missing_bullet_punct > 1:
        issues.append(f"Bullet punctuation — {missing_bullet_punct} bullets are missing ending punctuation.")

    for anchor in article_soup.find_all("a", href=True):
        raw = anchor.get_text("", strip=False)
        visible = re.sub(r"\s+", " ", raw or "").strip()
        if visible and raw and raw.rstrip() != raw:
            trailing_anchor_labels.append(visible)

    trailing_anchor_labels = list(dict.fromkeys(trailing_anchor_labels))
    if len(trailing_anchor_labels) == 1:
        issues.append(f'Trailing whitespace in anchor text — “{trailing_anchor_labels[0]}” contains extra trailing space.')
    elif len(trailing_anchor_labels) > 1:
        shown = '”, “'.join(trailing_anchor_labels[:3])
        issues.append(f'Trailing whitespace in anchor text — “{shown}” contain extra trailing spaces.')

    raw_text = article_soup.get_text("", strip=False)
    nbsp_count = raw_text.count("\xa0")
    if nbsp_count >= 3:
        issues.append(f"Excess non-breaking spaces — {nbsp_count} non-breaking spaces were detected, which may create inconsistent or double spacing.")

    body = re.sub(r"\s+", " ", article_soup.get_text(" ", strip=True)).strip()
    if re.search(r"\bAl Rabdan\b", body) and re.search(r"(?<!Al )\bRabdan\b", body):
        issues.append('Naming inconsistency — Both "Rabdan" and "Al Rabdan" appear; standardise if they refer to the same place.')
    if "The Marina" in body and "the Marina" in body:
        issues.append('Capitalisation inconsistency — Both "The Marina" and "the Marina" appear.')

    family_positions = [m.start() for m in re.finditer(r"family[- ]friendly", body, flags=re.I)]
    if len(family_positions) >= 2 and any((b - a) <= 2500 for a, b in zip(family_positions, family_positions[1:])):
        issues.append('Repeated phrasing — "family-friendly" appears again within a short span.')

    return _v1855_unique(issues, limit=limit)
'''

func_pattern = re.compile(r'def deterministic_editorial_quality_issues\(article_soup, limit=30\):.*?\n\ndef audit_content\(', re.S)
text, n = func_pattern.subn(new_func + '\n\ndef audit_content(', text, count=1)
if n != 1:
    raise SystemExit('editorial function not replaced')

# Replace only the verbose grammar summary section, keeping the existing rows.append call.
grammar_pattern = re.compile(
    r'    grammar_finding = \(.*?\n    rows\.append\(result\(\n        "Grammar / Readability",',
    re.S,
)
grammar_replacement = '''    if editorial_quality_issues:\n        grammar_finding = "\\n".join(\n            f"{index}: {item}"\n            for index, item in enumerate(editorial_quality_issues[:20], start=1)\n        )\n    elif avg > 32 or malformed >= 4:\n        grammar_finding = f"Readability issue — Average sentence length is {avg:.1f} words with {malformed} unusually long or potentially malformed fragment(s)."\n    else:\n        grammar_finding = "No high-confidence grammar or CMS-formatting issues found."\n    rows.append(result(\n        "Grammar / Readability",'''
text, n = grammar_pattern.subn(grammar_replacement, text, count=1)
if n != 1:
    raise SystemExit('grammar summary not replaced')

# Use colon numbering across compact issue summaries.
text = text.replace('result_lines.append(f"{number}. {title}: {detail}")', 'result_lines.append(f"{number}: {title}: {detail}")')
text = text.replace('action_lines.append(f"{number}. {action}")', 'action_lines.append(f"{number}: {action}")')
text = text.replace('source_lines.append(f"{number}. {source}")', 'source_lines.append(f"{number}: {source}")')
text = text.replace('file_name="url_audit_report_v18_55.xlsx"', 'file_name="url_audit_report_v18_56.xlsx"')

path.write_text(text, encoding='utf-8')
