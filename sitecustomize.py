"""Boot-time patch for Streamlit Cloud.

Keeps the original Content table, adds a categorized numbered summary above it,
and stops normal image ALT descriptions from being sent to factual verification.
The patch is idempotent and runs before Streamlit executes app.py.
"""
from pathlib import Path
import re

try:
    p = Path(__file__).resolve().parent / "app.py"
    s = p.read_text(encoding="utf-8")

    if "V18.34 CONTENT TABLE + CATEGORY SUMMARY" not in s:
        s = re.sub(
            r'APP_VERSION\s*=\s*"[^"]+"',
            'APP_VERSION = "V18.34 CONTENT TABLE + CATEGORY SUMMARY"',
            s,
            count=1,
        )
        s = re.sub(
            r'ENGINE_BUILD\s*=\s*"[^"]+"',
            'ENGINE_BUILD = "2026.08.13.5"',
            s,
            count=1,
        )

        # ALT text is descriptive metadata, not automatically a factual claim.
        # Remove the block that sends every ALT string to official-source search.
        s = re.sub(
            r'\n\s*# Image ALT and captions are high-value because entity mistakes often live there\.\n'
            r'\s*for alt in fields\.get\("image_alts", \[\]\)\[:80\]:\n'
            r'\s*alt = re\.sub\(r"\\s\+", " ", alt\)\.strip\(\)\n'
            r'\s*if len\(alt\) >= 5:\n'
            r'\s*items\.append\(\{"text": alt, "kind": "Image Alt Text", "priority": 7\}\)',
            '\n    # ALT text is descriptive metadata and is not automatically a factual claim.\n'
            '    # Missing/empty ALT remains handled by the normal Images rule.\n',
            s,
            count=1,
        )

        # In V18.32 Content was rendered as cards. Replace that renderer with the
        # original table plus a categorized summary above it.
        marker_start = '                # Spam and SEO keep the normal rule table. Content is intentionally\n'
        marker_end = '\n        report_generated_at = datetime.now(timezone.utc).isoformat()'
        if marker_start in s:
            start = s.index(marker_start)
            end = s.index(marker_end, start)
            new_render = '''                # Keep the original table for Spam, SEO and Content.\n                # Content also gets a concise categorized issue summary above it.\n                if tab_index == 2:\n                    issue_rows = [r for r in rows if r.get("Status") in {FAIL, REVIEW}]\n\n                    def content_summary_category(row):\n                        finding_type = str(row.get("Finding Type", "") or "").lower()\n                        check = str(row.get("Check", "") or "").lower()\n                        combined = finding_type + " " + check\n                        if any(x in combined for x in ["grammar", "wording", "misspell", "readability"]):\n                            return "Grammar & Wording"\n                        if any(x in combined for x in ["official source", "factual", "fact", "source quality", "data accuracy"]):\n                            return "Facts Verification"\n                        if any(x in combined for x in ["entity", "image alt", "alt text", "caption", "image"]):\n                            return "Entity & Image Accuracy"\n                        if any(x in combined for x in ["search intent", "content relevance", "heading relevance", "title vs content", "h1 vs content"]):\n                            return "Search Intent & Relevance"\n                        if any(x in combined for x in ["outdated", "keyword", "repetition"]):\n                            return "Content Quality & Freshness"\n                        return "Other Content Issues"\n\n                    category_order = [\n                        "Facts Verification",\n                        "Grammar & Wording",\n                        "Entity & Image Accuracy",\n                        "Search Intent & Relevance",\n                        "Content Quality & Freshness",\n                        "Other Content Issues",\n                    ]\n                    grouped = {name: [] for name in category_order}\n                    for row in issue_rows:\n                        grouped[content_summary_category(row)].append(row)\n\n                    st.markdown("### Content Issues by Category")\n                    st.caption("Quick action list. The full Content table remains below exactly as before.")\n                    shown = False\n                    for category in category_order:\n                        category_rows = grouped[category]\n                        if not category_rows:\n                            continue\n                        shown = True\n                        st.markdown(f"#### {category}")\n                        for number, row in enumerate(category_rows, 1):\n                            check = str(row.get("Check", "") or "Issue")\n                            status = str(row.get("Status", ""))\n                            result_text = re.sub(r"\\s+", " ", str(row.get("Result", "") or "")).strip()\n                            if len(result_text) > 220:\n                                result_text = result_text[:217].rstrip() + "..."\n                            st.markdown(f"{number}. **{check}** — **{status}**  \\n{result_text}")\n                    if not shown:\n                        st.success("No Content FAIL or REVIEW items were found.")\n                    st.markdown("### Full Content Results")\n\n                public_rows = [\n                    {\n                        "Check": row["Check"],\n                        "Status": row["Status"],\n                        "Result": row["Result"],\n                        "Action Needed": row["Action Needed"],\n                        "Official Source": row.get("Official Source", ""),\n                        "Why": row["Why"],\n                    }\n                    for row in rows\n                ]\n                df = pd.DataFrame(public_rows)\n                styled_df = df.style.map(status_style, subset=["Status"])\n\n                st.dataframe(\n                    styled_df,\n                    use_container_width=True,\n                    hide_index=True,\n                    column_config={\n                        "Check": st.column_config.TextColumn(width="medium"),\n                        "Status": st.column_config.TextColumn(width="small"),\n                        "Result": st.column_config.TextColumn(width="large"),\n                        "Action Needed": st.column_config.TextColumn(width="large"),\n                        "Official Source": st.column_config.TextColumn(width="large"),\n                        "Why": st.column_config.TextColumn(width="large"),\n                    },\n                )\n'''
            s = s[:start] + new_render + s[end:]

        p.write_text(s, encoding="utf-8")
except Exception as exc:
    try:
        (Path(__file__).resolve().parent / "sitecustomize_patch_error.txt").write_text(str(exc), encoding="utf-8")
    except Exception:
        pass
