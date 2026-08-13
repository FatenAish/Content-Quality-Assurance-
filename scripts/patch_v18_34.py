from pathlib import Path

p = Path('app.py')
s = p.read_text(encoding='utf-8')

s = s.replace('APP_VERSION = "V18.32 GROUPED CONTENT CARDS"', 'APP_VERSION = "V18.34 CONTENT TABLE + CATEGORY SUMMARY"')
s = s.replace('ENGINE_BUILD = "2026.08.13.3"', 'ENGINE_BUILD = "2026.08.13.5"')

start = s.index('def _freeqa_claim_candidates(article_soup, body_text, target_topic=""):\n')
end = s.index('\n\ndef _freeqa_ddg_url', start)
new_claim_candidates = '''def _freeqa_claim_candidates(article_soup, body_text, target_topic=""):
    fields = _qa_editorial_fields(article_soup)
    items = []

    # ALT text is descriptive metadata, not automatically a factual claim.
    # Do not send every ALT through official-source verification. Specific ALT
    # entity mismatches are handled separately by _freeqa_alt_entity_findings().

    # Only research captions when they contain a concrete factual signal.
    for cap in fields.get("image_captions", [])[:80]:
        cap = re.sub(r"\\s+", " ", cap).strip()
        if len(cap) < 5:
            continue
        low = cap.lower()
        has_fact_signal = bool(
            re.search(r"\\b\\d+(?:[.,]\\d+)?\\b", cap)
            or any(x in low for x in [
                "consists of", "comprises", "developed by", "located in",
                "won", "award", "certified", "built to", "completed in",
                "contains", "features", "opened in", "handover"
            ])
        )
        if has_fact_signal:
            items.append({"text": cap, "kind": "Image Caption", "priority": 7})

    for sentence in _freeqa_split_sentences(body_text):
        low = sentence.lower()
        if any(term in low for term in _FREEQA_MARKET_TERMS):
            continue
        tokens = set(_freeqa_tokens(sentence))
        score = 0
        if re.search(r"\\b\\d+(?:[.,]\\d+)?\\b", sentence):
            score += 4
        if any(term in tokens or term in low for term in _FREEQA_FACT_TERMS):
            score += 3
        if _freeqa_entity_phrase(sentence):
            score += 3
        if any(x in low for x in ["consists of", "comprises", "developed by", "located in", "won", "award", "certified", "built to", "completed in"]):
            score += 3
        if score >= 6:
            items.append({"text": sentence, "kind": "Factual Accuracy", "priority": score})

    seen = set()
    unique = []
    for item in sorted(items, key=lambda x: x["priority"], reverse=True):
        key = re.sub(r"\\W+", " ", item["text"].lower()).strip()
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
        if len(unique) >= FREE_MAX_CLAIMS:
            break
    return unique
'''
s = s[:start] + new_claim_candidates + s[end:]

if '_freeqa_alt_entity_findings' not in s:
    marker = '\ndef _freeqa_local_findings(article_soup, body_text, target_topic=""):\n'
    idx = s.index(marker)
    helpers = '''

_FREEQA_ALT_ENTITY_SUFFIXES = {
    "residence", "residences", "tower", "towers", "heights", "club", "city",
    "community", "village", "gardens", "estate", "estates", "park", "school",
    "academy", "hospital", "clinic", "mall", "hotel", "stadium", "centre", "center",
}


def _freeqa_alt_entity_phrases(alt_text):
    text = re.sub(r"\\s+", " ", alt_text or "").strip()
    if not text:
        return []
    suffix_pattern = "|".join(sorted(_FREEQA_ALT_ENTITY_SUFFIXES, key=len, reverse=True))
    pattern = re.compile(
        rf"\\b((?:[A-Z][A-Za-z0-9&'’.-]*\\s+){{0,5}}(?:{suffix_pattern}))\\b",
        flags=re.I,
    )
    out = []
    seen = set()
    for match in pattern.finditer(text):
        value = clean_entity_candidate(match.group(1))
        key = entity_similarity_key(value)
        if not key or key in seen or not looks_like_entity_phrase(value):
            continue
        seen.add(key)
        out.append(value)
    return out


def _freeqa_entity_suffix_key(value):
    tokens = entity_similarity_key(value).split()
    if not tokens:
        return ""
    last = tokens[-1]
    return {"residences": "residence", "towers": "tower", "estates": "estate"}.get(last, last)


def _freeqa_alt_entity_findings(article_soup, target_topic=""):
    """Only flag ALT entity mismatches when an official source confirms the expected name."""
    fields = _qa_editorial_fields(article_soup)
    known_entities = entity_candidates(article_soup, limit=80)
    if not known_entities:
        return []

    known_by_key = {entity_similarity_key(x): x for x in known_entities}
    rows = []
    seen = set()

    for alt in fields.get("image_alts", [])[:120]:
        for alt_entity in _freeqa_alt_entity_phrases(alt):
            alt_key = entity_similarity_key(alt_entity)
            if not alt_key or alt_key in known_by_key:
                continue

            alt_suffix = _freeqa_entity_suffix_key(alt_entity)
            same_suffix = [e for e in known_entities if _freeqa_entity_suffix_key(e) == alt_suffix]
            if not same_suffix:
                continue

            scored = []
            for entity in same_suffix:
                ratio = SequenceMatcher(None, entity_similarity_key(alt_entity), entity_similarity_key(entity)).ratio()
                scored.append((ratio, entity))
            scored.sort(reverse=True)
            best_ratio, expected_entity = scored[0]
            if best_ratio < 0.72 and len(same_suffix) != 1:
                continue

            pair_key = (alt_key, entity_similarity_key(expected_entity))
            if pair_key in seen:
                continue
            seen.add(pair_key)

            verification = _freeqa_verify_claim(expected_entity, "Entity Accuracy", target_topic=target_topic)
            if verification.get("status") != PASS or not verification.get("source"):
                # Do not create noisy REVIEW rows when the free search cannot prove it.
                continue

            rows.append({
                "Check": f"{expected_entity} image alt text",
                "Status": FAIL,
                "Result": (
                    f"Incorrect entity name in image ALT text. The ALT says ‘{alt_entity}’, "
                    f"while the official source confirms ‘{expected_entity}’."
                ),
                "Action Needed": f"Replace ‘{alt_entity}’ with ‘{expected_entity}’ in the image ALT text.",
                "Why": (
                    "The system found a specific entity-name mismatch between the ALT text and the article, "
                    "then required official-source confirmation before flagging it."
                ),
                "Official Source": verification.get("source", ""),
                "Finding Type": "Entity Accuracy",
                "_internal_status": FAIL,
                "_rule": dict(CONTENT_RULES).get("Official Source Verification", ""),
                "_system_uses": "ALT entity extraction + article entity consistency + official source confirmation",
                "_evidence_finding": True,
            })

    return rows
'''
    s = s[:idx] + helpers + s[idx:]

old = '''        target_topic = focus_keyword or title or h1
        rows = _freeqa_local_findings(article_soup, body_text, target_topic=target_topic)

        candidates = _freeqa_claim_candidates(article_soup, body_text, target_topic=target_topic)
'''
new = '''        target_topic = focus_keyword or title or h1
        rows = _freeqa_local_findings(article_soup, body_text, target_topic=target_topic)
        rows.extend(_freeqa_alt_entity_findings(article_soup, target_topic=target_topic))

        candidates = _freeqa_claim_candidates(article_soup, body_text, target_topic=target_topic)
'''
if old in s:
    s = s.replace(old, new, 1)

s = s.replace('"Factual Accuracy & Official Verification",', '"Facts Verification",')
s = s.replace('return "Factual Accuracy & Official Verification"', 'return "Facts Verification"')

render_start = s.index('                # Spam and SEO keep the normal rule table. Content is intentionally')
render_end = s.index('\n        report_generated_at = datetime.now(timezone.utc).isoformat()', render_start)
new_render = '''                # Keep the original table for Spam, SEO AND Content.
                # Content also gets a concise categorized issue summary above the table.
                if tab_index == 2:
                    content_issue_rows = [r for r in rows if r.get("Status") in {FAIL, REVIEW}]
                    grouped = {category: [] for category in CONTENT_CATEGORY_ORDER}
                    for row in content_issue_rows:
                        grouped.setdefault(content_issue_category(row), []).append(row)

                    st.markdown(
                        "<div style='margin:2px 0 14px;'>"
                        "<div style='font-size:18px;font-weight:800;color:#172026;'>Content Issues by Category</div>"
                        "<div style='font-size:12px;color:#667085;margin-top:4px;'>"
                        "Use this summary to see what needs checking. Full details remain in the table below."
                        "</div></div>",
                        unsafe_allow_html=True,
                    )

                    displayed_category = False
                    for category in CONTENT_CATEGORY_ORDER:
                        category_rows = grouped.get(category, [])
                        if not category_rows:
                            continue
                        displayed_category = True
                        st.markdown(f"#### {category}")
                        for number, row in enumerate(category_rows, start=1):
                            status = str(row.get("Status", ""))
                            check = str(row.get("Check", "") or "Issue")
                            result_text = re.sub(r"\\s+", " ", str(row.get("Result", "") or "")).strip()
                            if len(result_text) > 240:
                                result_text = result_text[:237].rstrip() + "..."
                            st.markdown(
                                f"{number}. **{check}** — **{status}**  \\n"
                                f"   {result_text}"
                            )

                    if not displayed_category:
                        st.success("No Content FAIL or REVIEW items were found.")

                    st.markdown("### Full Content Results")

                public_rows = [
                    {
                        "Check": row["Check"],
                        "Status": row["Status"],
                        "Result": row["Result"],
                        "Action Needed": row["Action Needed"],
                        "Official Source": row.get("Official Source", ""),
                        "Why": row["Why"],
                    }
                    for row in rows
                ]
                df = pd.DataFrame(public_rows)
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
                        "Official Source": st.column_config.TextColumn(width="large"),
                        "Why": st.column_config.TextColumn(width="large"),
                    },
                )
'''
s = s[:render_start] + new_render + s[render_end:]

p.write_text(s, encoding='utf-8')
print('Patched app.py to V18.34')
