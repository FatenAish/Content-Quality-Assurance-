import re
import json
import os
import io
import zipfile
import time
import html as html_lib
import gzip
import base64
import xml.etree.ElementTree as ET
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
from difflib import SequenceMatcher
from urllib.parse import urljoin, urlparse, parse_qs, unquote
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

APP_VERSION = "V18.37 CLOAKING ACCESS FIX"
ENGINE_BUILD = "2026.08.13.8"
CURRENT_YEAR = 2026

# Free official-source Content QA. No API key is required.
# The verifier uses public search result pages plus direct HTTP requests to source pages.
# Search/network failures never stop the audit; unresolved claims become REVIEW.
FREE_SEARCH_TIMEOUT = int(os.getenv("MYBAYUT_FREE_SEARCH_TIMEOUT", "10"))
FREE_SOURCE_TIMEOUT = int(os.getenv("MYBAYUT_FREE_SOURCE_TIMEOUT", "8"))
FREE_MAX_CLAIMS = int(os.getenv("MYBAYUT_FREE_MAX_CLAIMS", "12"))
FREE_MAX_SEARCH_RESULTS = int(os.getenv("MYBAYUT_FREE_MAX_SEARCH_RESULTS", "8"))
FREE_SEARCH_URL = os.getenv("MYBAYUT_FREE_SEARCH_URL", "https://html.duckduckgo.com/html/").strip()

AI_BLOCKED_SOURCE_DOMAINS = [
    "bayut.com", "dubizzle.com", "propertyfinder.ae", "wikipedia.org",
    "reddit.com", "tripadvisor.com", "quora.com", "pinterest.com",
    "facebook.com", "instagram.com", "linkedin.com", "youtube.com", "x.com",
    "medium.com", "thenationalnews.com", "gulfnews.com", "khaleejtimes.com",
]

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



def build_audit_excel_report(
    url_requested,
    url_final,
    focus_keyword,
    secondary_keywords,
    spam_rows,
    seo_rows,
    content_rows,
    spam_status,
    spam_counts,
    seo_status,
    seo_counts,
    content_status,
    content_counts,
    generated_at_utc,
    total_audit_time,
    desktop_status_code,
    extracted_words,
):
    # Generate a real XLSX file using Python standard library only.

    def xml_escape(value):
        return html_lib.escape("" if value is None else str(value), quote=False)

    def safe_text(value):
        if value is None:
            return ""
        if isinstance(value, (list, tuple)):
            return ", ".join(str(v) for v in value)
        return str(value)

    def col_letter(number):
        letters = ""
        while number:
            number, remainder = divmod(number - 1, 26)
            letters = chr(65 + remainder) + letters
        return letters

    def cell_ref(row, col):
        return f"{col_letter(col)}{row}"

    STYLE_DEFAULT = 0
    STYLE_TITLE = 1
    STYLE_SECTION = 2
    STYLE_LABEL = 3
    STYLE_VALUE = 4
    STYLE_URL = 5
    STYLE_HEADER = 6
    STYLE_TEXT = 7
    STYLE_CHECK = 8
    STYLE_PASS = 9
    STYLE_REVIEW = 10
    STYLE_FAIL = 11
    STYLE_NEUTRAL = 12
    STYLE_NOTE = 13
    STYLE_INTEGER = 14

    def status_style(status):
        if status == "PASS":
            return STYLE_PASS
        if status == "REVIEW":
            return STYLE_REVIEW
        if status == "FAIL":
            return STYLE_FAIL
        return STYLE_NEUTRAL

    def inline_cell(row, col, value, style=STYLE_DEFAULT):
        ref = cell_ref(row, col)
        return (
            f'<c r="{ref}" s="{style}" t="inlineStr">'
            f'<is><t xml:space="preserve">{xml_escape(safe_text(value))}</t></is>'
            f'</c>'
        )

    def number_cell(row, col, value, style=STYLE_INTEGER):
        ref = cell_ref(row, col)
        return f'<c r="{ref}" s="{style}" t="n"><v>{value}</v></c>'

    def row_xml(row_number, cells, height=None):
        attrs = [f'r="{row_number}"']
        if height is not None:
            attrs.extend([f'ht="{height}"', 'customHeight="1"'])
        return f'<row {" ".join(attrs)}>{"".join(cells)}</row>'

    def row_height_from_values(*values):
        longest = max((len(safe_text(v)) for v in values), default=0)
        line_count = max((safe_text(v).count("\n") + 1 for v in values), default=1)

        if longest > 900 or line_count >= 8:
            return 135
        if longest > 600 or line_count >= 6:
            return 110
        if longest > 350 or line_count >= 4:
            return 85
        if longest > 180 or line_count >= 3:
            return 65
        if longest > 90 or line_count >= 2:
            return 48
        return 32

    def worksheet_xml(
        rows,
        column_widths,
        merges=None,
        freeze_rows=1,
        freeze_cols=0,
        auto_filter=None,
    ):
        merges = merges or []

        cols = "".join(
            f'<col min="{idx}" max="{idx}" width="{width}" customWidth="1"/>'
            for idx, width in enumerate(column_widths, start=1)
        )

        if freeze_rows or freeze_cols:
            top_left = cell_ref(max(1, freeze_rows + 1), max(1, freeze_cols + 1))
            pane_attrs = ['state="frozen"', f'topLeftCell="{top_left}"']

            if freeze_rows:
                pane_attrs.append(f'ySplit="{freeze_rows}"')
            if freeze_cols:
                pane_attrs.append(f'xSplit="{freeze_cols}"')

            if freeze_rows and freeze_cols:
                pane_attrs.append('activePane="bottomRight"')
            elif freeze_rows:
                pane_attrs.append('activePane="bottomLeft"')
            else:
                pane_attrs.append('activePane="topRight"')

            views = (
                '<sheetViews><sheetView workbookViewId="0">'
                f'<pane {" ".join(pane_attrs)}/>'
                '</sheetView></sheetViews>'
            )
        else:
            views = '<sheetViews><sheetView workbookViewId="0"/></sheetViews>'

        merge_xml = ""
        if merges:
            merge_xml = (
                f'<mergeCells count="{len(merges)}">'
                + "".join(f'<mergeCell ref="{ref}"/>' for ref in merges)
                + '</mergeCells>'
            )

        filter_xml = f'<autoFilter ref="{auto_filter}"/>' if auto_filter else ""

        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f'{views}'
            '<sheetFormatPr defaultRowHeight="15"/>'
            f'<cols>{cols}</cols>'
            f'<sheetData>{"".join(rows)}</sheetData>'
            f'{merge_xml}'
            f'{filter_xml}'
            '<pageMargins left="0.3" right="0.3" top="0.5" bottom="0.5" header="0.2" footer="0.2"/>'
            '</worksheet>'
        )

    # Summary.
    summary_rows_xml = []
    summary_merges = ["A1:F2", "A4:F4"]

    summary_rows_xml.append(
        row_xml(
            1,
            [inline_cell(1, 1, "Bayut URL Quality Audit Report", STYLE_TITLE)],
            28,
        )
    )
    summary_rows_xml.append(row_xml(2, [], 12))
    summary_rows_xml.append(row_xml(3, [], 8))
    summary_rows_xml.append(
        row_xml(4, [inline_cell(4, 1, "Audit Information", STYLE_SECTION)], 24)
    )

    info_rows = [
        ("Requested URL", safe_text(url_requested)),
        ("Final URL", safe_text(url_final)),
        ("Focus Keyword", safe_text(focus_keyword)),
        ("Secondary Keywords", safe_text(secondary_keywords)),
        ("Generated UTC", safe_text(generated_at_utc)),
        ("App Version", APP_VERSION),
        ("Engine Build", ENGINE_BUILD),
        ("HTTP Status", safe_text(desktop_status_code)),
        ("Extracted Words", f"{int(extracted_words):,}"),
        ("Total Audit Time", f"{float(total_audit_time):.1f} seconds"),
    ]

    row_num = 5
    for label, value in info_rows:
        summary_merges.append(f"B{row_num}:F{row_num}")
        summary_rows_xml.append(
            row_xml(
                row_num,
                [
                    inline_cell(row_num, 1, label, STYLE_LABEL),
                    inline_cell(
                        row_num,
                        2,
                        value,
                        STYLE_URL if label in {"Requested URL", "Final URL"} else STYLE_VALUE,
                    ),
                ],
                row_height_from_values(value),
            )
        )
        row_num += 1

    row_num += 1
    summary_merges.append(f"A{row_num}:F{row_num}")
    summary_rows_xml.append(
        row_xml(row_num, [inline_cell(row_num, 1, "Audit Summary", STYLE_SECTION)], 24)
    )

    row_num += 1
    headers = ["Category", "Overall Status", "PASS", "REVIEW", "FAIL", "Rules"]
    summary_rows_xml.append(
        row_xml(
            row_num,
            [
                inline_cell(row_num, idx, header, STYLE_HEADER)
                for idx, header in enumerate(headers, start=1)
            ],
            28,
        )
    )

    summary_data = [
        ("Spam", spam_status, spam_counts, len(spam_rows)),
        ("SEO", seo_status, seo_counts, len(seo_rows)),
        ("Content", content_status, content_counts, len(content_rows)),
    ]

    for category, overall_status, counts, rule_count in summary_data:
        row_num += 1
        summary_rows_xml.append(
            row_xml(
                row_num,
                [
                    inline_cell(row_num, 1, category, STYLE_CHECK),
                    inline_cell(row_num, 2, overall_status, status_style(overall_status)),
                    number_cell(row_num, 3, int(counts.get("PASS", 0))),
                    number_cell(row_num, 4, int(counts.get("REVIEW", 0))),
                    number_cell(row_num, 5, int(counts.get("FAIL", 0))),
                    number_cell(row_num, 6, int(rule_count)),
                ],
                28,
            )
        )

    row_num += 2
    summary_merges.append(f"A{row_num}:F{row_num}")
    summary_rows_xml.append(
        row_xml(
            row_num,
            [inline_cell(row_num, 1, "How to Read This Report", STYLE_SECTION)],
            24,
        )
    )

    row_num += 1
    summary_merges.append(f"A{row_num}:F{row_num + 3}")
    summary_rows_xml.append(
        row_xml(
            row_num,
            [
                inline_cell(
                    row_num,
                    1,
                    (
                        "PASS means no issue was found by that rule. REVIEW means the rule found "
                        "something that needs checking or improvement. FAIL means a clear issue was "
                        "detected. Start with the Issues Only sheet for the action list, then use "
                        "Spam, SEO and Content for the complete Result, Action Needed and Why details."
                    ),
                    STYLE_NOTE,
                )
            ],
            72,
        )
    )
    summary_rows_xml.extend(
        [
            row_xml(row_num + 1, [], 20),
            row_xml(row_num + 2, [], 20),
            row_xml(row_num + 3, [], 20),
        ]
    )

    summary_xml = worksheet_xml(
        rows=summary_rows_xml,
        column_widths=[24, 24, 14, 14, 14, 14],
        merges=summary_merges,
        freeze_rows=4,
    )

    # Detail sheets.
    detail_headers = ["Check", "Status", "Result", "Action Needed", "Why"]

    def build_detail_sheet(category_rows):
        rows_xml = [
            row_xml(
                1,
                [
                    inline_cell(1, idx, header, STYLE_HEADER)
                    for idx, header in enumerate(detail_headers, start=1)
                ],
                28,
            )
        ]

        row_number = 2
        for item in category_rows:
            check = safe_text(item.get("Check"))
            status = safe_text(item.get("Status"))
            result_value = safe_text(item.get("Result"))
            action_value = safe_text(item.get("Action Needed"))
            why_value = safe_text(item.get("Why"))

            rows_xml.append(
                row_xml(
                    row_number,
                    [
                        inline_cell(row_number, 1, check, STYLE_CHECK),
                        inline_cell(row_number, 2, status, status_style(status)),
                        inline_cell(row_number, 3, result_value, STYLE_TEXT),
                        inline_cell(row_number, 4, action_value, STYLE_TEXT),
                        inline_cell(row_number, 5, why_value, STYLE_TEXT),
                    ],
                    row_height_from_values(result_value, action_value, why_value),
                )
            )
            row_number += 1

        last_row = max(1, row_number - 1)

        return worksheet_xml(
            rows=rows_xml,
            column_widths=[28, 13, 62, 52, 62],
            freeze_rows=1,
            freeze_cols=2,
            auto_filter=f"A1:E{last_row}",
        )

    # Issues Only.
    issues = []
    for category, category_rows in [
        ("Spam", spam_rows),
        ("SEO", seo_rows),
        ("Content", content_rows),
    ]:
        for item in category_rows:
            if item.get("Status") in {"REVIEW", "FAIL"}:
                issues.append({"Category": category, **item})

    issue_headers = ["Category", "Check", "Status", "Result", "Action Needed", "Why"]
    issues_rows_xml = [
        row_xml(
            1,
            [
                inline_cell(1, idx, header, STYLE_HEADER)
                for idx, header in enumerate(issue_headers, start=1)
            ],
            28,
        )
    ]
    issues_merges = []

    if issues:
        row_number = 2
        for item in issues:
            category = safe_text(item.get("Category"))
            check = safe_text(item.get("Check"))
            status = safe_text(item.get("Status"))
            result_value = safe_text(item.get("Result"))
            action_value = safe_text(item.get("Action Needed"))
            why_value = safe_text(item.get("Why"))

            issues_rows_xml.append(
                row_xml(
                    row_number,
                    [
                        inline_cell(row_number, 1, category, STYLE_CHECK),
                        inline_cell(row_number, 2, check, STYLE_CHECK),
                        inline_cell(row_number, 3, status, status_style(status)),
                        inline_cell(row_number, 4, result_value, STYLE_TEXT),
                        inline_cell(row_number, 5, action_value, STYLE_TEXT),
                        inline_cell(row_number, 6, why_value, STYLE_TEXT),
                    ],
                    row_height_from_values(result_value, action_value, why_value),
                )
            )
            row_number += 1
        issue_last_row = row_number - 1
    else:
        issues_merges.append("A2:F4")
        issues_rows_xml.append(
            row_xml(
                2,
                [
                    inline_cell(
                        2,
                        1,
                        "No REVIEW or FAIL items were found in this audit.",
                        STYLE_NOTE,
                    )
                ],
                55,
            )
        )
        issues_rows_xml.extend([row_xml(3, [], 20), row_xml(4, [], 20)])
        issue_last_row = 1

    issues_xml = worksheet_xml(
        rows=issues_rows_xml,
        column_widths=[15, 28, 13, 62, 52, 62],
        merges=issues_merges,
        freeze_rows=1,
        freeze_cols=3,
        auto_filter=f"A1:F{issue_last_row}" if issues else None,
    )

    spam_xml = build_detail_sheet(spam_rows)
    seo_xml = build_detail_sheet(seo_rows)
    content_xml = build_detail_sheet(content_rows)

    sheet_names = ["Summary", "Issues Only", "Spam", "SEO", "Content"]

    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        + "".join(
            f'<Override PartName="/xl/worksheets/sheet{i}.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            for i in range(1, 6)
        )
        + '</Types>'
    )

    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/>'
        '</Relationships>'
    )

    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<bookViews><workbookView/></bookViews>'
        '<sheets>'
        + "".join(
            f'<sheet name="{xml_escape(name)}" sheetId="{idx}" r:id="rId{idx}"/>'
            for idx, name in enumerate(sheet_names, start=1)
        )
        + '</sheets>'
        '</workbook>'
    )

    workbook_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + "".join(
            f'<Relationship Id="rId{i}" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            f'Target="worksheets/sheet{i}.xml"/>'
            for i in range(1, 6)
        )
        + '<Relationship Id="rId6" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
        'Target="styles.xml"/>'
        '</Relationships>'
    )

    styles_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="12">
    <font><sz val="11"/><name val="Calibri"/><family val="2"/></font>
    <font><b/><sz val="18"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font>
    <font><b/><sz val="12"/><color rgb="FF1F2D2A"/><name val="Calibri"/></font>
    <font><b/><sz val="11"/><color rgb="FF33413D"/><name val="Calibri"/></font>
    <font><u/><sz val="11"/><color rgb="FF0563C1"/><name val="Calibri"/></font>
    <font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font>
    <font><b/><sz val="11"/><color rgb="FF1F2D2A"/><name val="Calibri"/></font>
    <font><b/><sz val="11"/><color rgb="FF14804A"/><name val="Calibri"/></font>
    <font><b/><sz val="11"/><color rgb="FF9A6700"/><name val="Calibri"/></font>
    <font><b/><sz val="11"/><color rgb="FFB42318"/><name val="Calibri"/></font>
    <font><b/><sz val="11"/><color rgb="FF475467"/><name val="Calibri"/></font>
    <font><i/><sz val="11"/><color rgb="FF66736F"/><name val="Calibri"/></font>
  </fonts>
  <fills count="9">
    <fill><patternFill patternType="none"/></fill>
    <fill><patternFill patternType="gray125"/></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FF00A66A"/><bgColor indexed="64"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFEAF7F1"/><bgColor indexed="64"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFF6F9F7"/><bgColor indexed="64"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFE9F8EF"/><bgColor indexed="64"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFFFF6D8"/><bgColor indexed="64"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFFDECEC"/><bgColor indexed="64"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFF2F4F7"/><bgColor indexed="64"/></patternFill></fill>
  </fills>
  <borders count="2">
    <border><left/><right/><top/><bottom/><diagonal/></border>
    <border>
      <left style="thin"><color rgb="FFE4E9E7"/></left>
      <right style="thin"><color rgb="FFE4E9E7"/></right>
      <top style="thin"><color rgb="FFE4E9E7"/></top>
      <bottom style="thin"><color rgb="FFE4E9E7"/></bottom>
      <diagonal/>
    </border>
  </borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs count="15">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
    <xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1"><alignment vertical="center"/></xf>
    <xf numFmtId="0" fontId="2" fillId="3" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment vertical="center"/></xf>
    <xf numFmtId="0" fontId="3" fillId="4" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment vertical="top"/></xf>
    <xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>
    <xf numFmtId="0" fontId="4" fillId="0" borderId="1" xfId="0" applyFont="1" applyBorder="1" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>
    <xf numFmtId="0" fontId="5" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>
    <xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>
    <xf numFmtId="0" fontId="6" fillId="0" borderId="1" xfId="0" applyFont="1" applyBorder="1" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>
    <xf numFmtId="0" fontId="7" fillId="5" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="top" wrapText="1"/></xf>
    <xf numFmtId="0" fontId="8" fillId="6" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="top" wrapText="1"/></xf>
    <xf numFmtId="0" fontId="9" fillId="7" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="top" wrapText="1"/></xf>
    <xf numFmtId="0" fontId="10" fillId="8" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="top" wrapText="1"/></xf>
    <xf numFmtId="0" fontId="11" fillId="0" borderId="0" xfId="0" applyFont="1" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>
    <xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
  </cellXfs>
  <cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>"""

    output = io.BytesIO()

    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as xlsx:
        xlsx.writestr("[Content_Types].xml", content_types)
        xlsx.writestr("_rels/.rels", root_rels)
        xlsx.writestr("xl/workbook.xml", workbook_xml)
        xlsx.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        xlsx.writestr("xl/styles.xml", styles_xml)
        xlsx.writestr("xl/worksheets/sheet1.xml", summary_xml)
        xlsx.writestr("xl/worksheets/sheet2.xml", issues_xml)
        xlsx.writestr("xl/worksheets/sheet3.xml", spam_xml)
        xlsx.writestr("xl/worksheets/sheet4.xml", seo_xml)
        xlsx.writestr("xl/worksheets/sheet5.xml", content_xml)

    output.seek(0)
    return output.getvalue()



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
    ("Cloaking", "Compare normal user and Googlebot-like responses only when both return usable page content. FAIL only for a confirmed material crawler-specific content or destination difference. Access errors, CAPTCHA, bot challenges and blocked requests are not cloaking by themselves."),
    ("Crawler Access Issue", "REVIEW when the normal user and Googlebot-like requests do not have equivalent usable access, including HTTP 401/403/405/406/429, CAPTCHA, bot challenge, timeout-style error pages or other access restrictions. This is an access/bot-handling signal, not proof of cloaking."),
    ("Sneaky Redirect", "FAIL when crawler and user are sent to materially different destinations after both responses are successfully accessible. Access-block or challenge redirects are REVIEW, not deceptive redirect FAILs."),
    ("Device Spam Redirect", "FAIL when mobile or device users are redirected to unrelated or spam destinations while other visitors are not."),
    ("Hidden Text", "Inspect why text is hidden before assigning a result. Legitimate interface, responsive and accessibility hiding should PASS. Unexplained hiding should REVIEW. Hiding intended to manipulate search rankings should FAIL."),
    ("Hidden Links", "FAIL only when an actual <a href> link is deliberately concealed by supported HTML/CSS hiding signals and no legitimate interface, responsive or accessibility purpose is detected. Empty anchors are not hidden links by themselves. Self references to the current article are ignored."),
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
    ("Official Source Verification", "Free official-source research for factual claims and entity details. FAIL only with a direct contradiction on an official page, REVIEW when official evidence is insufficient, and PASS when an official page directly confirms the claim. No paid API key is required."),
    ("Outdated Information", "Evaluate old year references in context and also compare time sensitive claims with the latest editorial publication or modification date. Historical dates alone PASS. REVIEW stale or undated prices, rents, ROI, fees, laws, routes or project status using an internal freshness heuristic."),
    ("Keyword Use", "Evaluate Focus Keyword and Secondary Keyword use only in the editorial article text. Exclude TruBroker, property widgets, banners, newsletters, social UI and other embedded modules. Exact matching is not required for every secondary phrase. PASS natural use, REVIEW unusually repetitive target wording, FAIL clearly manipulative repetition."),
    ("Repetition", "REVIEW/FAIL when sentences or paragraphs are unnecessarily repeated."),
    ("Title vs Content", "PASS when title terms/topic are strongly represented in the body."),
    ("H1 vs Content", "PASS when H1 accurately represents the main body."),
    ("Heading Relevance", "Respect heading hierarchy when evaluating H2 to H4 sections. FAQ headings include their child questions and answers. Project, building, place and other entity headings can PASS through related section context even without Focus Keyword wording."),
    ("Source Quality", "Check only claims that depend on an official authority or regulation. Examples include laws, government eligibility requirements, visas, permits, licences, official fees, fines and mandatory thresholds. Do not flag project specifications, property details, distances, amenities, unit counts, market data, investment commentary or ordinary descriptive information."),
    ("Data Accuracy", "Check internal numeric consistency only within the same editorial section or project context. Do not compare repeated sentence patterns across different projects, areas or headings. REVIEW only when substantially the same statement inside the same context contains conflicting numeric values."),
    ("Misspelling", "Check only high confidence English spelling errors in editorial article text. Unknown words are not automatically treated as misspellings. Ignore proper names, brands, project and place names, loanwords, short ambiguous terms, acronyms, URLs, contractions, normal inflections, British English, property terminology and embedded widgets. REVIEW only when a strong correction candidate exists."),
    ("Grammar / Readability", "REVIEW when sentence structure is consistently difficult to read or text is obviously malformed."),
    ("Broken Content", "FAIL obvious placeholders/unfinished output; REVIEW empty headings or duplicated content blocks."),
]


SYSTEM_USES = {
    # Spam
    "Cloaking": "Desktop User Agent and Googlebot-like User Agent, HTTP access-state validation, final URL comparison, main content extraction and text similarity only when both responses contain usable page content",
    "Crawler Access Issue": "Desktop, Mobile and Googlebot-like HTTP status codes, short challenge/error-page detection, final response availability and bot/access restriction comparison",
    "Sneaky Redirect": "Desktop User Agent, Googlebot-like User Agent, HTTP access-state validation, redirect handling and final destination comparison only after successful access",
    "Device Spam Redirect": "Desktop User Agent, Mobile User Agent, final URL comparison, main content similarity",
    "Hidden Text": "Rendered DOM when available, computed CSS, hidden attribute, accessibility attributes, responsive visibility, interface context, text length and hiding reason classification",
    "Hidden Links": "Fetched HTML <a href> elements, same-page exclusion, HTML/CSS hiding signals, and legitimate UI/accessibility context classification; empty anchors alone are excluded",
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
    "Official Source Verification": "Free public web search result retrieval, blocked secondary-source domains, direct official-page HTTP fetching, claim/entity/numeric comparison, article headings, body text, image ALT text and captions; no paid API key",
    "Outdated Information": "Old year context, time sensitive claim detection, schema and visible editorial dates, and age of the latest editorial freshness signal",
    "Keyword Use": "Editorial article text only, Focus Keyword, Secondary Keywords, semantic topic representation, target phrase frequency and N gram repetition; TruBroker, broker/property widgets, banners, newsletter and social UI are excluded",
    "Repetition": "Normalised sentences, normalised paragraphs, duplicate counts, repetition ratio",
    "Title vs Content": "HTML title text, main article body, topic keyword overlap",
    "H1 vs Content": "Main H1 text, main article body, topic keyword overlap",
    "Heading Relevance": "Hierarchical H2 through H4 relationships, Focus Keyword or main topic, FAQ child content, entity heading recognition, semantic concept overlap and section context",
    "Source Quality": "Sentence level official authority claim extraction. Checks laws, regulations, government eligibility requirements, visas, permits, licences, official fees, fines and mandatory thresholds. Project specifications, distances, property details, amenities, market data and investment commentary are excluded",
    "Data Accuracy": "Repeated numeric statement templates scoped to the nearest editorial H2, H3 or H4 context; different projects, areas and sections are not compared against each other",
    "Misspelling": "Editorial article text only, embedded offline English word frequency dictionary, one edit spelling candidates, capitalization and proper noun filtering, Bayut real estate allow list and widget exclusions",
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


# =========================================================
# MISSPELLING CHECK
# Offline dictionary embedded in app.py for standalone deployment.
# =========================================================

SPELLING_FREQ_GZIP_B64 = """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"""

@lru_cache(maxsize=1)
def spelling_frequency_dictionary():
    try:
        raw = gzip.decompress(base64.b64decode(SPELLING_FREQ_GZIP_B64.encode("ascii")))
        data = json.loads(raw.decode("utf-8"))
        return {str(k).lower(): int(v) for k, v in data.items()}
    except Exception:
        return {}


SPELLING_ALLOW_WORDS = {
    # Bayut / UAE / property terminology
    "bayut", "dubizzle", "uae", "emirates", "emirati", "dubai", "dhabi",
    "jumeirah", "deira", "barsha", "furjan", "nahda", "jebel", "jafza",
    "meydan", "mirdif", "qusais", "karama", "satwa", "wasl", "jaddaf",
    "marina", "downtown", "burjuman", "trubroker", "freehold", "leasehold",
    "offplan", "off-plan", "townhouse", "townhouses", "studio", "studios",
    "bedroom", "bedrooms", "bhk", "sqft", "psf", "roi", "rta", "dld",
    "gdrfa", "icp", "reits", "amenity", "amenities", "masterplan",
    "masterplanned", "subcommunity", "subcommunities", "waterfront",
    "mixeduse", "mixed-use", "coworking", "co-working",

    # Common development naming words
    "residences", "residence", "developers", "developer",
    "realty", "skyline", "skyblade",

    # British English commonly used by Bayut
    "centre", "centres", "metre", "metres", "kilometre", "kilometres",
    "neighbour", "neighbours", "neighbourhood", "neighbourhoods",
    "licence", "licences", "licensed", "travelling", "travelled",
    "labelled", "modelling", "favour", "favourite", "favourites",
    "organisation", "organisations", "organised", "organise",
    "colour", "colours", "grey", "storey", "storeys",
    "programme", "programmes", "theatre", "theatres",

    # Publishing / SEO terminology
    "seo", "faq", "faqs", "url", "urls", "html", "json", "schema",
    "blogpost", "wordpress", "mybayut",

    # Common editorial / property words
    "metro", "metros",
    "emirate", "emirates", "emirati",
    "expansive", "expansively",
    "gym", "gyms",
    "onsen", "onsens",
    "pod", "pods",
    "vida",
    "handover", "handovers",
    "launch", "launches", "launched", "launching",
    "finish", "finishes", "finished", "finishing",
    "combine", "combines", "combined", "combining",
    "eco", "eco-friendly",
    "emphasise", "emphasises", "emphasised", "emphasising",
    "emphasize", "emphasizes", "emphasized", "emphasizing",
    "landscape", "landscapes", "landscaped", "landscaping",
    "polo", "spa", "spas", "blog", "blogs",
    "capitalise", "capitalises", "capitalised", "capitalising",
    "capitalize", "capitalizes", "capitalized", "capitalizing",

    # Common contractions
    "it's", "that's", "there's", "here's", "what's", "who's",
    "isn't", "aren't", "wasn't", "weren't", "doesn't", "don't",
    "didn't", "can't", "cannot", "couldn't", "shouldn't", "wouldn't",
    "won't", "hasn't", "haven't", "hadn't", "we're", "they're",
    "you're", "i'm", "i've", "we've", "they've", "you've",
}

SPELLING_ENTITY_SUFFIXES = {
    "residence", "residences", "tower", "towers", "villas", "villa",
    "heights", "gardens", "estate", "estates", "city", "community",
    "school", "academy", "hospital", "clinic", "mall", "hotel",
    "park", "centre", "center", "developers", "developer",
    "properties", "realty", "house", "houses", "place", "plaza",
}


def _known_spelling_word(word):
    """Return True for a dictionary word, approved term or normal inflection."""
    word = (word or "").lower().strip()
    if not word:
        return True

    freq = spelling_frequency_dictionary()

    if word in SPELLING_ALLOW_WORDS or word in freq:
        return True

    if word.endswith("'s") and word[:-2] in freq:
        return True

    candidates = set()

    # Plural / third-person singular
    if word.endswith("ies") and len(word) > 4:
        candidates.add(word[:-3] + "y")
    if word.endswith("es") and len(word) > 4:
        candidates.add(word[:-2])
        candidates.add(word[:-1])
    if word.endswith("s") and len(word) > 3:
        candidates.add(word[:-1])

    # Past tense
    if word.endswith("ied") and len(word) > 4:
        candidates.add(word[:-3] + "y")
    if word.endswith("ed") and len(word) > 4:
        candidates.add(word[:-2])
        candidates.add(word[:-1])
        if len(word) > 5 and word[-3] == word[-4]:
            candidates.add(word[:-3])

    # Continuous form
    if word.endswith("ing") and len(word) > 5:
        candidates.add(word[:-3])
        candidates.add(word[:-3] + "e")
        if len(word) > 6 and word[-4] == word[-5]:
            candidates.add(word[:-4])

    # Comparative / superlative
    if word.endswith("er") and len(word) > 4:
        candidates.add(word[:-2])
        candidates.add(word[:-1])
    if word.endswith("est") and len(word) > 5:
        candidates.add(word[:-3])
        candidates.add(word[:-2])

    return any(
        candidate in SPELLING_ALLOW_WORDS or candidate in freq
        for candidate in candidates
        if candidate
    )


def _spelling_edits1(word):
    """Generate one edit distance spelling candidates."""
    alphabet = "abcdefghijklmnopqrstuvwxyz"
    splits = [(word[:i], word[i:]) for i in range(len(word) + 1)]

    deletes = [left + right[1:] for left, right in splits if right]
    transposes = [
        left + right[1] + right[0] + right[2:]
        for left, right in splits
        if len(right) > 1
    ]
    replaces = [
        left + char + right[1:]
        for left, right in splits
        if right
        for char in alphabet
        if char != right[0]
    ]
    inserts = [
        left + char + right
        for left, right in splits
        for char in alphabet
    ]

    return set(deletes + transposes + replaces + inserts)


SPELLING_NEVER_AUTOCORRECT = {
    "emirate", "emirates", "emirati",
    "expansive", "expansively",
    "gym", "gyms",
    "onsen", "onsens",
    "pod", "pods",
    "vida",
    "spa", "spas", "polo", "eco", "metro", "metros",
    "blog", "blogs", "handover", "handovers",
    "landscaped", "capitalise", "capitalised", "capitalising",
    "emphasise", "emphasises", "emphasised", "emphasising",
}


def _correction_is_high_confidence(word, candidate):
    """
    Unknown does not mean misspelled.

    Only accept a spelling suggestion when the source token is not already
    recognised and the replacement is a reasonably established word.
    """
    word = (word or "").lower().strip()
    candidate = (candidate or "").lower().strip()

    if not word or not candidate or word == candidate:
        return False

    if word in SPELLING_NEVER_AUTOCORRECT:
        return False

    if _known_spelling_word(word):
        return False

    # Short tokens are too risky: many are brands, acronyms, loanwords,
    # amenities or product names.
    if len(word) <= 4:
        return False

    freq = spelling_frequency_dictionary()
    candidate_freq = freq.get(candidate, 0)

    # Explicit Bayut allow-list words are trusted. Otherwise require a
    # meaningful dictionary signal. Threshold 10 still catches clear errors
    # such as apartmant -> apartment while avoiding weak dictionary guesses.
    if candidate not in SPELLING_ALLOW_WORDS and candidate_freq < 10:
        return False

    return True


@lru_cache(maxsize=4096)
def likely_spelling_correction(word):
    """Return a high confidence one edit correction, otherwise None."""
    freq = spelling_frequency_dictionary()
    low = (word or "").lower().strip()

    if not low or _known_spelling_word(low):
        return None

    candidates = [
        candidate
        for candidate in _spelling_edits1(low)
        if candidate in freq or candidate in SPELLING_ALLOW_WORDS
    ]

    if not candidates:
        return None

    candidates = sorted(
        set(candidates),
        key=lambda candidate: (
            candidate in SPELLING_ALLOW_WORDS,
            freq.get(candidate, 0),
            -abs(len(candidate) - len(low)),
            candidate,
        ),
        reverse=True,
    )

    best = candidates[0]
    best_freq = freq.get(best, 0)

    if best not in SPELLING_ALLOW_WORDS and best_freq < 2:
        return None

    if not _correction_is_high_confidence(low, best):
        return None

    return best


def _word_is_sentence_initial(source_text, start_index):
    prefix = source_text[max(0, start_index - 10):start_index]
    if not prefix.strip():
        return True
    stripped = prefix.rstrip()
    return bool(stripped and stripped[-1] in ".!?؟")


def _looks_like_title_case_entity(source_text, match):
    """Protect likely brands, project names, place names and proper nouns."""
    raw = match.group(0)

    if not raw[:1].isupper():
        return False

    if not _word_is_sentence_initial(source_text, match.start()):
        return True

    tail = source_text[match.end():match.end() + 60]
    next_match = re.search(r"^\s+([A-Za-z][A-Za-z'’\-]{2,})", tail)

    if next_match:
        next_word = next_match.group(1)
        next_low = next_word.lower()

        if next_word[:1].isupper() or next_low in SPELLING_ENTITY_SUFFIXES:
            return True

    # Sentence-initial unknown title-case tokens are too ambiguous to
    # autocorrect. This protects standalone brands such as Vida.
    low = raw.lower()
    if len(raw) <= 12 and low not in spelling_frequency_dictionary():
        return True

    return False


def likely_misspellings(source_text, limit=12):
    """
    Conservative English spelling checker for editorial content.
    """
    if not source_text:
        return []

    latin_chars = len(re.findall(r"[A-Za-z]", source_text))
    arabic_chars = len(re.findall(r"[\u0600-\u06FF]", source_text))
    if arabic_chars > latin_chars * 1.5:
        return []

    found = {}
    freq = spelling_frequency_dictionary()
    word_pattern = re.compile(r"\b[A-Za-z][A-Za-z'’\-]{2,}\b")

    for match in word_pattern.finditer(source_text):
        raw = match.group(0)
        normalized = raw.replace("’", "'").strip("'").lower()

        if not normalized or len(normalized) < 3:
            continue

        around = source_text[max(0, match.start() - 12):match.end() + 12].lower()
        if "http://" in around or "https://" in around or "www." in around or "@" in around:
            continue

        if normalized.endswith("'s") and len(normalized) > 4:
            normalized = normalized[:-2]

        # Hyphenated compounds are checked component by component.
        if "-" in normalized:
            parts = [part for part in normalized.split("-") if len(part) >= 3]
            for part in parts:
                if _known_spelling_word(part):
                    continue
                suggestion = likely_spelling_correction(part)
                if suggestion and suggestion != part:
                    item = found.setdefault(part, {
                        "word": part,
                        "suggestion": suggestion,
                        "count": 0,
                    })
                    item["count"] += 1
            continue

        # Acronyms and mixed-case tokens are not spelling candidates.
        if raw.isupper() or any(ch.isupper() for ch in raw[1:]):
            continue

        # Proper names / project names / places / brands.
        if _looks_like_title_case_entity(source_text, match):
            continue

        if _known_spelling_word(normalized):
            continue

        suggestion = likely_spelling_correction(normalized)
        if not suggestion or suggestion == normalized:
            continue

        item = found.setdefault(normalized, {
            "word": normalized,
            "suggestion": suggestion,
            "count": 0,
        })
        item["count"] += 1

    return sorted(
        found.values(),
        key=lambda item: (-item["count"], item["word"]),
    )[:limit]


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


CONTENT_CATEGORY_ORDER = [
    "Grammar & Wording",
    "Entity & Image Accuracy",
    "Facts Verification",
    "Search Intent & Relevance",
    "Data & Freshness",
    "Keyword & Repetition",
    "Structure & Content Quality",
    "Other Content Issues",
]


def content_issue_category(row):
    """Map a Content QA row to one editor-friendly issue category."""
    finding_type = str(row.get("Finding Type", "") or "").strip().lower()
    check = str(row.get("Check", "") or "").strip().lower()
    result_text = str(row.get("Result", "") or "").strip().lower()
    combined = f"{finding_type} {check} {result_text}"

    if any(x in combined for x in [
        "grammar", "wording", "misspelling", "spelling", "readability",
        "subject-verb", "typographical", "typo", "punctuation",
    ]):
        return "Grammar & Wording"

    if any(x in combined for x in [
        "image alt", "image caption", "entity accuracy", "entity name",
        "incorrect entity", "building name", "project name", "community name",
    ]):
        return "Entity & Image Accuracy"

    if any(x in combined for x in [
        "factual accuracy", "official source", "source verification",
        "source quality", "needs verification", "official-source",
        "official verification",
    ]):
        return "Facts Verification"

    if any(x in combined for x in [
        "search intent", "content relevance", "heading relevance",
        "title vs content", "h1 vs content", "intent mismatch",
    ]):
        return "Search Intent & Relevance"

    if any(x in combined for x in [
        "outdated", "freshness", "data accuracy", "stale", "old year",
    ]):
        return "Data & Freshness"

    if any(x in combined for x in [
        "keyword use", "keyword stuffing", "repetition", "duplicate sentence",
        "duplicate paragraph",
    ]):
        return "Keyword & Repetition"

    if any(x in combined for x in [
        "thin content", "original value", "broken content", "content quality",
        "placeholder", "empty heading",
    ]):
        return "Structure & Content Quality"

    return "Other Content Issues"


DEFAULT_ACTIONS = {
    "Cloaking": "Serve the same primary editorial content and destination to normal users and Googlebot. Remove crawler-specific SEO content or redirects only when a material crawler-specific difference is confirmed.",
    "Crawler Access Issue": "Check CDN, WAF, firewall, cache and bot-management rules. Make sure legitimate crawlers can access the intended article. Do not treat an access error by itself as cloaking.",
    "Sneaky Redirect": "Remove deceptive or crawler-specific redirects only when both user and crawler requests are successfully accessible and the destination difference is confirmed. Investigate access-block redirects separately.",
    "Device Spam Redirect": "Use the same relevant destination and primary content for desktop and mobile users.",
    "Hidden Text": "Make editorial text visible unless it is legitimately hidden for interface, responsive or accessibility reasons.",
    "Hidden Links": "Remove only deliberately concealed links. Do not treat empty anchors, visible card links, image/icon links, or recognised interface/accessibility controls as hidden-link spam.",
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
    "Title vs Content": "Align the title with what the article actually covers, or update the article so it fulfils the title.",
    "H1 vs Content": "Align the H1 with the actual article body.",
    "Heading Relevance": "Rename, remove or rewrite weak headings and their sections so they clearly belong to the main topic.",
    "Source Quality": "Add an official or authoritative source beside each numbered official requirement listed in Result.",
    "Data Accuracy": "Verify and correct only the numbered numeric contradiction listed within the same article section.",
    "Misspelling": "Correct only the numbered likely misspellings listed in Result after confirming the intended word.",
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
            "Checked actual <a href> elements for supported HTML/CSS hiding signals. "
            "Empty anchors alone are not classified as hidden links, and recognised "
            "interface, responsive and accessibility controls are excluded."
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
    Detect deliberately concealed links directly from fetched HTML.

    IMPORTANT:
    - An empty <a href> is NOT a hidden link by itself.
    - Visible property/listing cards, image links, icon links and CTA wrappers are
      not hidden-link spam merely because the anchor has no text.
    - A link is reported only when the anchor or an ancestor has a supported
      source-level hiding signal and there is no recognised legitimate UI,
      responsive or accessibility reason for that hiding.
    - Each genuinely concealed <a href> occurrence is counted separately.
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

        # Empty anchors are not hidden links. Hidden Links requires an actual
        # concealment signal on the anchor or one of its ancestors.
        hidden_element, hidden_reasons = hidden_ancestor_info(anchor)
        if hidden_element is None:
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

        # Determine whether the hiding is a recognised interface/accessibility
        # behaviour rather than an SEO concealment pattern.
        context = nearest_editorial_context(anchor)
        ui_context = _token_string(
            element_label(anchor),
            element_label(hidden_element),
            anchor_text,
            anchor.get("aria-label"),
            anchor.get("title"),
            anchor.get("role"),
            href,
            context,
        )
        legitimate_reason = known_ui_reason_from_text(ui_context)

        # Property/listing modules can contain hidden inactive carousel cards or
        # clickable wrappers. Treat those as legitimate UI, not hidden-link spam.
        widget_context = ui_context.casefold()
        property_widget_patterns = (
            "property-card", "property_card", "listing-card", "listing_card",
            "property-listing", "property_listing", "listing-widget",
            "listing_widget", "trubroker", "featured-property",
            "featured_property", "property/details-",
        )
        if not legitimate_reason and any(p in widget_context for p in property_widget_patterns):
            legitimate_reason = "Property/listing widget"

        if legitimate_reason:
            continue

        details.append({
            "occurrence": occurrence_index,
            "url": href,
            "anchor_text": anchor_text or "(empty)",
            "hidden_element": element_label(hidden_element),
            "hidden_because": ", ".join(hidden_reasons),
            "status": FAIL,
            "source": "Fetched HTML source",
            "anchor_html": anchor_html[:500],
            "context": context,
            "issue_type": "Hidden HTML link",
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


@lru_cache(maxsize=512)
def _internal_target_identity_cached(url, bucket):
    """Fetch destination title/H1 for internal-link destination relevance checks."""
    try:
        r = requests.get(
            url,
            headers={**UA_DESKTOP, "Accept-Language": "en-US,en;q=0.8"},
            timeout=max(INTERNAL_LINK_CHECK_TIMEOUT, 5),
            allow_redirects=True,
        )
        ctype = (r.headers.get("content-type") or "").lower()
        if r.status_code >= 400 or "html" not in ctype:
            return {"ok": False, "url": r.url, "status": r.status_code, "title": "", "h1": ""}
        soup = BeautifulSoup(r.text, "html.parser")
        title = re.sub(r"\s+", " ", soup.title.get_text(" ", strip=True) if soup.title else "").strip()
        h1_node = soup.find("h1")
        h1 = re.sub(r"\s+", " ", h1_node.get_text(" ", strip=True) if h1_node else "").strip()
        return {"ok": True, "url": r.url, "status": r.status_code, "title": title, "h1": h1}
    except Exception:
        return {"ok": False, "url": url, "status": None, "title": "", "h1": ""}


def internal_target_identity(url):
    return _internal_target_identity_cached(url, cache_bucket(900))


def internal_link_title_mismatches(inventory, max_workers=8):
    """
    Detect entity-like internal anchors whose destination title tag is unrelated.

    This catches cases such as anchor 'Royal Residence' pointing to a page whose
    title tag says 'Executive Towers Business Bay Guide'.
    """
    candidates = []
    seen_urls = set()
    for item in inventory:
        if not item.get("is_internal"):
            continue
        anchor = re.sub(r"\s+", " ", item.get("anchor_text", "") or "").strip()
        if not anchor or item.get("generic_anchor") or len(tokenize(anchor)) < 2:
            continue
        # Restrict destination-title comparison to named entities/places/projects to
        # avoid false positives for broad editorial anchors.
        if not looks_like_entity_phrase(anchor):
            continue
        if item["url"] in seen_urls:
            continue
        seen_urls.add(item["url"])
        candidates.append((item["url"], anchor))

    if not candidates:
        return []

    identities = {}
    with ThreadPoolExecutor(max_workers=min(max_workers, len(candidates))) as executor:
        futures = {
            executor.submit(internal_target_identity, url): (url, anchor)
            for url, anchor in candidates
        }
        for future in as_completed(futures):
            url, anchor = futures[future]
            try:
                identities[url] = future.result()
            except Exception:
                identities[url] = {"ok": False, "url": url, "status": None, "title": "", "h1": ""}

    issues = []
    for url, anchor in candidates:
        identity = identities.get(url, {})
        if not identity.get("ok"):
            continue
        target_title = identity.get("title", "")
        if not target_title:
            continue

        title_score = max(
            keyword_overlap(anchor, target_title),
            semantic_overlap(anchor, target_title),
        )
        if title_score >= 0.20:
            continue

        # Strong mismatch: named anchor has essentially no relationship with the
        # destination title tag. Report the exact destination title for editorial QA.
        issues.append({
            "url": url,
            "final_url": identity.get("url", url),
            "anchor_text": anchor,
            "target_title": target_title,
            "target_h1": identity.get("h1", ""),
            "title_score": title_score,
        })

    return issues

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
    title_mismatches = {
        (x.get("url"), x.get("anchor_text", "").casefold()): x
        for x in internal_link_title_mismatches(inventory)
    }

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

        title_issue = title_mismatches.get((item["url"], item["anchor_text"].casefold()))
        if title_issue:
            reasons.append(
                f'Destination title tag does not match the linked entity: "{title_issue.get("target_title", "")}"'
            )

        if reasons:
            issues.append({
                "url": item["url"],
                "anchor_text": item["anchor_text"],
                "reasons": reasons,
                "target_title": title_issue.get("target_title", "") if title_issue else "",
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
    Detect internal numeric contradictions only inside the same editorial context.

    The previous implementation compared repeated sentence templates across the
    whole article. That caused false positives when different projects or areas
    legitimately had different values, for example:

    Property types: Studios to 3-bedroom apartments
    Property types: Studios to 2-bedroom apartments

    These are not contradictions when they appear under different project or
    area headings.

    Comparison is now scoped to the nearest H2/H3/H4 heading. If no editorial
    heading exists, the statement is placed in a document-level context.
    """
    templates = {}
    conflicts = []

    number_pattern = re.compile(
        r"(?:AED\s*)?\b\d+(?:[.,]\d+)?(?:\s*[KMB])?%?\b",
        flags=re.I,
    )

    def nearest_editorial_context(node):
        heading = node.find_previous(["h2", "h3", "h4"])
        if not heading:
            return "__document__"

        heading_text = re.sub(
            r"\s+",
            " ",
            heading.get_text(" ", strip=True),
        ).strip().casefold()

        return heading_text or "__document__"

    for node in article_soup.find_all(["p", "li", "td", "th"]):
        value = re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()

        numbers = number_pattern.findall(value)
        if not numbers or len(value) < 35:
            continue

        template = number_pattern.sub("<num>", value.casefold())
        template = re.sub(r"\s+", " ", template).strip()

        if len(template) < 25:
            continue

        normalized_numbers = tuple(
            re.sub(r"\s+", "", number.casefold())
            for number in numbers
        )

        context = nearest_editorial_context(node)
        key = (context, template)

        previous = templates.get(key)

        if previous and previous["numbers"] != normalized_numbers:
            conflicts.append({
                "section": context if context != "__document__" else "Article body",
                "statement": value[:300],
                "previous_statement": previous["statement"][:300],
                "previous_values": previous["numbers"],
                "current_values": normalized_numbers,
            })
        else:
            templates[key] = {
                "numbers": normalized_numbers,
                "statement": value,
            }

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



def is_source_sensitive_non_market_claim(value):
    """
    Source Quality is intentionally narrow.

    It checks only claims that depend on an official authority, law,
    regulation or government eligibility rule.

    It does NOT flag:
    project specifications
    floors, units or amenity counts
    distances or travel times
    property prices, rents, ROI or yields
    investment commentary
    launch narrative
    ordinary descriptive/location information
    """
    value = re.sub(r"\s+", " ", value or "").strip()
    low = value.lower()

    if not value:
        return False

    # Explicit legal / regulatory language.
    explicit_regulatory = bool(re.search(
        r"\b(?:law|laws|regulation|regulations|legislation|"
        r"mandatory|required|requirement|requirements|must comply|"
        r"permit|permits|licen[cs]e|licen[cs]es|fine|fines|"
        r"official fee|official fees)\b",
        low,
        flags=re.I,
    )) or bool(re.search(
        r"\b(?:قانون|قوانين|لائحة|لوائح|تشريع|تشريعات|"
        r"إلزامي|الزامي|مطلوب|متطلبات|يجب الالتزام|"
        r"تصريح|تصاريح|ترخيص|تراخيص|غرامة|غرامات|رسوم رسمية)\b",
        value,
        flags=re.I,
    ))

    if explicit_regulatory:
        return True

    # Visa / residency eligibility rules.
    visa_context = (
        "visa" in low
        or "golden visa" in low
        or "residency" in low
        or "residence visa" in low
        or "تأشيرة" in value
        or "تاشيرة" in value
        or "إقامة" in value
        or "اقامة" in value
    )

    eligibility_terms = bool(re.search(
        r"\b(?:eligible|eligibility|threshold|minimum|required|requirement|"
        r"must meet|qualify|qualification|valid for|duration|"
        r"\d+\s*(?:years?|months?))\b",
        low,
        flags=re.I,
    )) or bool(re.search(
        r"\b(?:مؤهل|أهلية|اهلية|حد أدنى|حد ادنى|مطلوب|شرط|شروط|"
        r"يجب|مدة|سنوات|أشهر|اشهر)\b",
        value,
        flags=re.I,
    ))

    if visa_context and eligibility_terms:
        return True

    # Named authority claims only when they state a rule, fee, requirement,
    # eligibility condition or mandatory process.
    authority_context = bool(re.search(
        r"\b(?:rta|dubai land department|dld|dubai municipality|"
        r"government|ministry|authority|department|icp|gdrfa)\b",
        low,
        flags=re.I,
    )) or bool(re.search(
        r"\b(?:هيئة الطرق والمواصلات|دائرة الأراضي والأملاك|"
        r"دائرة الاراضي والاملاك|بلدية دبي|الحكومة|وزارة|هيئة|دائرة)\b",
        value,
        flags=re.I,
    ))

    authority_rule_terms = bool(re.search(
        r"\b(?:requires?|required|requirement|must|mandatory|"
        r"fee|fees|fine|fines|permit|licen[cs]e|eligible|eligibility|threshold)\b",
        low,
        flags=re.I,
    )) or bool(re.search(
        r"\b(?:يتطلب|مطلوب|متطلبات|يجب|إلزامي|الزامي|"
        r"رسوم|غرامة|غرامات|تصريح|ترخيص|مؤهل|أهلية|اهلية|حد أدنى|حد ادنى)\b",
        value,
        flags=re.I,
    ))

    return authority_context and authority_rule_terms



def split_source_claim_sentences(value):
    value = re.sub(r"\s+", " ", value or "").strip()
    if not value:
        return []
    parts = re.split(r"(?<=[.!?؟])\s+", value)
    return [part.strip() for part in parts if len(part.strip()) >= 25]


def source_quality_claim_examples(article_soup, base_url, limit=40):
    """
    Extract focused sentence-level Source Quality claims.

    Support is inherited from the containing editorial paragraph/list item.
    The claim itself is always shown as one sentence instead of a long paragraph.
    """
    claims = []

    for node in article_soup.find_all(["p", "li", "td"]):
        paragraph = re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()
        if len(paragraph) < 25:
            continue

        sources = []
        for anchor in node.find_all("a", href=True):
            resolved = urljoin(base_url, anchor.get("href", "").strip())
            if resolved.startswith(("http://", "https://")):
                sources.append(resolved)

        nearby_context = nearby_support_context(node)
        claim_links = unique_http_urls(sources)
        supported = bool(claim_links) or has_attribution(nearby_context)

        for sentence in split_source_claim_sentences(paragraph):
            if not is_source_sensitive_non_market_claim(sentence):
                continue

            claims.append({
                "claim": sentence[:420],
                "source_links": claim_links,
                "attributed": has_attribution(nearby_context),
                "supported": supported,
            })

            if len(claims) >= limit:
                return claims

    return claims



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


def response_access_state(response, min_article_words=40):
    """
    Decide whether a response is usable for crawler-vs-user content comparison.

    Access errors and short anti-bot/challenge pages are not valid inputs for
    cloaking or redirect-content comparison. This intentionally distinguishes
    bot handling from cloaking.
    """
    if response is None:
        return False, "request unavailable"

    try:
        status = int(getattr(response, "status_code", 0) or 0)
    except Exception:
        status = 0

    if status in {401, 403, 405, 406, 429}:
        return False, f"HTTP {status} access restriction"
    if status >= 500:
        return False, f"HTTP {status} server response"
    if status < 200 or status >= 300:
        return False, f"HTTP {status or 'unknown'} non-success response"

    page_text = clean_text(soup_of(getattr(response, "text", "")))
    article_text = main_content_text(soup_of(getattr(response, "text", "")))
    page_words = word_count(page_text)
    article_words = word_count(article_text)

    challenge_markers = (
        "captcha",
        "verify you are human",
        "are you a human",
        "attention required",
        "access denied",
        "request blocked",
        "security check",
        "bot challenge",
        "checking your browser",
        "enable javascript and cookies",
    )
    low = page_text.lower()[:8000]
    if page_words < 250 and any(marker in low for marker in challenge_markers):
        return False, "anti-bot, CAPTCHA or access-challenge page"

    if article_words < min_article_words:
        return False, f"HTTP {status} but only {article_words} article words were extractable"

    return True, f"HTTP {status} with usable article content"


def audit_spam(url, desktop_r, mobile_r, bot_r, soup, body_text, focus_keyword="", secondary_keywords=None):
    rows = []
    rules = dict(SPAM_RULES)
    secondary_keywords = secondary_keywords or []

    desktop_text = body_text
    bot_text = main_content_text(soup_of(bot_r.text))
    mobile_text = main_content_text(soup_of(mobile_r.text))

    desktop_usable, desktop_access_reason = response_access_state(desktop_r)
    bot_usable, bot_access_reason = response_access_state(bot_r)
    mobile_usable, mobile_access_reason = response_access_state(mobile_r)

    desktop_status = getattr(desktop_r, "status_code", None)
    bot_status = getattr(bot_r, "status_code", None)
    mobile_status = getattr(mobile_r, "status_code", None)

    desktop_dest = normalized_destination(desktop_r.url)
    bot_dest = normalized_destination(bot_r.url)
    desktop_chain = response_redirect_chain(desktop_r)
    bot_chain = response_redirect_chain(bot_r)

    # ---------------------------------------------------------
    # Crawler access is evaluated BEFORE cloaking.
    # A 403/401/429/CAPTCHA/challenge page is not cloaking proof.
    # ---------------------------------------------------------
    if desktop_usable and bot_usable:
        crawler_access_status = PASS
        crawler_access_note = (
            f"Normal user and Googlebot-like requests both returned usable content "
            f"(user HTTP {desktop_status}; crawler HTTP {bot_status})."
        )
    elif desktop_usable and not bot_usable:
        crawler_access_status = REVIEW
        crawler_access_note = (
            f"Crawler Access Issue: the normal user request is usable (HTTP {desktop_status}) "
            f"but the Googlebot-like request is not ({bot_access_reason}). "
            "This may come from CDN, WAF, firewall or bot-management behaviour and does not prove cloaking."
        )
    elif not desktop_usable and bot_usable:
        crawler_access_status = REVIEW
        crawler_access_note = (
            f"Crawler Access Issue: the Googlebot-like request is usable (HTTP {bot_status}) "
            f"but the normal user request is not ({desktop_access_reason}). "
            "The access difference requires investigation but is not enough to label cloaking."
        )
    else:
        crawler_access_status = REVIEW
        crawler_access_note = (
            f"Crawler Access Issue: neither response is suitable for a cloaking comparison. "
            f"Normal user: {desktop_access_reason}. Googlebot-like: {bot_access_reason}."
        )
    rows.append(result(
        "Crawler Access Issue",
        crawler_access_status,
        crawler_access_note,
        rules["Crawler Access Issue"],
    ))

    # ---------------------------------------------------------
    # Cloaking comparison only runs when BOTH responses are usable.
    # ---------------------------------------------------------
    if not (desktop_usable and bot_usable):
        rows.append(result(
            "Cloaking",
            REVIEW,
            "Cloaking could not be validly compared because both the normal user and Googlebot-like "
            f"responses did not return usable page content. User: {desktop_access_reason}. "
            f"Crawler: {bot_access_reason}. Access failure alone is not cloaking.",
            rules["Cloaking"],
        ))
    else:
        sim_bot = similarity(desktop_text, bot_text)
        if desktop_dest != bot_dest:
            rows.append(result(
                "Cloaking",
                FAIL,
                f"Confirmed accessible user and Googlebot-like requests reached different final destinations: "
                f"{desktop_r.url} vs {bot_r.url}.",
                rules["Cloaking"],
            ))
        elif sim_bot < 0.72 and min(word_count(desktop_text), word_count(bot_text)) > 150:
            rows.append(result(
                "Cloaking",
                FAIL,
                f"Confirmed material user versus Googlebot-like content difference detected "
                f"({sim_bot:.0%} similarity) after both responses returned usable content.",
                rules["Cloaking"],
            ))
        elif sim_bot < 0.88:
            rows.append(result(
                "Cloaking",
                REVIEW,
                f"Both responses are accessible, but user versus Googlebot-like content similarity is "
                f"{sim_bot:.0%}. Review dynamic, personalised, geo-specific or A/B-tested content before "
                "treating the difference as cloaking.",
                rules["Cloaking"],
            ))
        else:
            rows.append(result(
                "Cloaking",
                PASS,
                f"Both responses are accessible. User versus Googlebot-like content similarity is "
                f"{sim_bot:.0%} and the final destination matches.",
                rules["Cloaking"],
            ))

    # Sneaky Redirect also requires usable user and crawler responses.
    if not (desktop_usable and bot_usable):
        st_redirect = REVIEW
        note = (
            "Sneaky redirect comparison is inconclusive because one or both request variants are not "
            f"usable. User: {desktop_access_reason}. Crawler: {bot_access_reason}. "
            "An access-block or challenge redirect is not a confirmed sneaky redirect."
        )
    else:
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
                f"Different final destinations after successful access. User chain: {redirect_chain_summary(desktop_r)}. "
                f"Crawler chain: {redirect_chain_summary(bot_r)}."
            )
        elif chains_materially_different:
            st_redirect = REVIEW
            note = (
                "Final destination matches, but accessible user and crawler redirect chains differ. "
                f"User chain: {redirect_chain_summary(desktop_r)}. "
                f"Crawler chain: {redirect_chain_summary(bot_r)}."
            )
        else:
            st_redirect = PASS
            note = f"User and crawler reach the same destination with no material redirect-chain difference: {desktop_r.url}"
    rows.append(result("Sneaky Redirect", st_redirect, note, rules["Sneaky Redirect"]))

    # Device redirect/content comparison follows the same access-first principle.
    mobile_dest = normalized_destination(mobile_r.url)
    if not (desktop_usable and mobile_usable):
        rows.append(result(
            "Device Spam Redirect",
            REVIEW,
            "Desktop versus mobile comparison is inconclusive because one or both variants are not usable. "
            f"Desktop: {desktop_access_reason}. Mobile: {mobile_access_reason}. "
            "An access restriction is not a confirmed device spam redirect.",
            rules["Device Spam Redirect"],
        ))
    elif mobile_dest != desktop_dest:
        rows.append(result(
            "Device Spam Redirect",
            FAIL,
            f"Accessible mobile and desktop requests reached different final destinations. "
            f"Desktop: {desktop_r.url}. Mobile: {mobile_r.url}.",
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



def _qa_plain_text(value):
    if value is None:
        return ""
    if hasattr(value, "get_text"):
        value = value.get_text(" ", strip=True)
    return re.sub(r"\s+", " ", str(value)).strip()


def _qa_editorial_fields(article_soup):
    headings, image_alts, image_captions = [], [], []
    if article_soup is None:
        return {"headings": [], "image_alts": [], "image_captions": []}

    for h in article_soup.find_all(re.compile(r"^h[1-6]$")):
        value = _qa_plain_text(h)
        if value:
            headings.append(f"{h.name.upper()}: {value}")

    for img in article_soup.find_all("img"):
        alt = _qa_plain_text(img.get("alt", ""))
        if alt:
            image_alts.append(alt)

    for cap in article_soup.find_all("figcaption"):
        value = _qa_plain_text(cap)
        if value:
            image_captions.append(value)

    for node in article_soup.select(".wp-caption-text, .caption, .image-caption, [class*='caption']"):
        value = _qa_plain_text(node)
        if value and value not in image_captions:
            image_captions.append(value)

    return {
        "headings": list(dict.fromkeys(headings))[:120],
        "image_alts": list(dict.fromkeys(image_alts))[:200],
        "image_captions": list(dict.fromkeys(image_captions))[:200],
    }


def _qa_collect_http_urls(obj):
    urls = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key == "url" and isinstance(value, str) and value.startswith(("http://", "https://")):
                urls.append(value)
            else:
                urls.extend(_qa_collect_http_urls(value))
    elif isinstance(obj, list):
        for value in obj:
            urls.extend(_qa_collect_http_urls(value))
    return list(dict.fromkeys(urls))


def _qa_response_output_text(payload):
    for item in payload.get("output", []) or []:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for content in item.get("content", []) or []:
            if isinstance(content, dict) and content.get("type") == "output_text":
                return content.get("text", "") or ""
    return ""


def _qa_host(url):
    try:
        host = (urlparse(url).hostname or "").lower()
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""


def _qa_blocked_source(url):
    host = _qa_host(url)
    if not host:
        return True
    return any(host == d or host.endswith("." + d) for d in AI_BLOCKED_SOURCE_DOMAINS)


def _qa_normalized_url(url):
    try:
        p = urlparse(url)
        host = _qa_host(url)
        path = re.sub(r"/+", "/", p.path or "/").rstrip("/") or "/"
        return f"{p.scheme.lower()}://{host}{path}"
    except Exception:
        return str(url or "")


def _qa_reconcile_source(candidate_url, web_urls):
    candidate_url = _qa_plain_text(candidate_url)
    if not candidate_url or _qa_blocked_source(candidate_url):
        return ""

    wanted = _qa_normalized_url(candidate_url)
    for url in web_urls:
        if not _qa_blocked_source(url) and _qa_normalized_url(url) == wanted:
            return url

    candidate_host = _qa_host(candidate_url)
    for url in web_urls:
        if not _qa_blocked_source(url) and _qa_host(url) == candidate_host:
            return url
    return ""


def _qa_content_schema():
    return {
        "type": "object",
        "properties": {
            "findings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "status": {"type": "string", "enum": ["PASS", "REVIEW", "FAIL"]},
                        "check": {"type": "string", "enum": [
                            "Factual Accuracy", "Entity Accuracy", "Grammar & Wording",
                            "Search Intent", "Image Alt Text", "Image Caption"
                        ]},
                        "issue_name": {"type": "string"},
                        "result": {"type": "string"},
                        "article_excerpt": {"type": "string"},
                        "correction": {"type": "string"},
                        "verification_basis": {"type": "string", "enum": [
                            "official_source", "article_text", "insufficient_official_evidence"
                        ]},
                        "source_name": {"type": "string"},
                        "source_url": {"type": "string"},
                        "source_type": {"type": "string", "enum": [
                            "government", "official_developer", "official_project",
                            "official_organisation", "official_business", "article_itself", "none"
                        ]},
                    },
                    "required": [
                        "status", "check", "issue_name", "result", "article_excerpt", "correction",
                        "verification_basis", "source_name", "source_url", "source_type"
                    ],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["findings"],
        "additionalProperties": False,
    }


def _qa_content_prompt(url, title, h1, article_text, fields, focus_keyword="", secondary_keywords=None):
    secondary_keywords = secondary_keywords or []
    article_text = (article_text or "")[:AI_MAX_ARTICLE_CHARS]
    headings = "\n".join(fields.get("headings", [])[:120]) or "(none)"
    alts = "\n".join(f"- {x}" for x in fields.get("image_alts", [])[:200]) or "(none)"
    captions = "\n".join(f"- {x}" for x in fields.get("image_captions", [])[:200]) or "(none)"

    return f"""Audit CONTENT only for this MyBayut article.

ARTICLE URL (article evidence only; never use Bayut as factual verification evidence):
{url}
TITLE: {title}
H1: {h1}
FOCUS KEYWORD: {focus_keyword or '(not provided)'}
SECONDARY KEYWORDS: {', '.join(secondary_keywords) if secondary_keywords else '(none)'}

NON-NEGOTIABLE RULES:
1. Research factual claims, entity names, project/building/community details, awards, unit/floor counts,
   completion years, developers, amenities, certifications, distances and similar facts on the web.
2. Prefer official/primary sources: UAE government, Dubai Land Department, RERA or relevant authority;
   then official developer, project/community, school, hospital, attraction, golf club, business or company.
3. Do not use Bayut, Dubizzle, Property Finder, Wikipedia, Reddit, TripAdvisor, brokers, property portals,
   aggregators, blogs or SEO sites to confirm a factual claim.
4. FAIL factual/entity claims only when an authoritative official source directly contradicts the article.
5. REVIEW when official public evidence is insufficient. Lack of evidence is not evidence that a claim is false.
6. PASS when an official source directly confirms a claim. Include useful PASS findings where confirmation
   prevents a false positive.
7. Grammar, spelling, wording and search-intent errors can FAIL from the article itself without external proof.
8. Inspect image ALT text and image captions separately.
9. Never mix average with minimum/starting price. 'Average ... starts from' is incorrect wording.
10. If the article is rental-focused, a substantial buying/investment FAQ should be flagged for search intent.
11. Do not invent corrected facts, figures, dates, standards, awards or source URLs.
12. Return concise, specific findings. State what is wrong, what evidence shows, and the exact correction.
13. For REVIEW explicitly say Needs verification and do not call the claim false.
14. Precision matters more than quantity. Return at most 20 high-value findings.

STATUS:
PASS = officially confirmed/no issue.
REVIEW = needs verification/official evidence insufficient.
FAIL = proven factual, entity, grammar, wording, image or search-intent error.

HEADINGS:
{headings}

IMAGE ALT TEXT:
{alts}

IMAGE CAPTIONS:
{captions}

ARTICLE TEXT:
{article_text}
"""



# -----------------------------
# Free official-source verifier
# -----------------------------

_FREEQA_GENERIC_WORDS = {
    "the", "a", "an", "and", "or", "of", "in", "at", "on", "to", "for", "with", "from",
    "this", "that", "these", "those", "is", "are", "was", "were", "has", "have", "had",
    "offers", "offer", "features", "feature", "includes", "include", "provides", "provide",
    "dubai", "uae", "united", "arab", "emirates", "official", "website", "home",
}

_FREEQA_FACT_TERMS = {
    "tower", "towers", "unit", "units", "floor", "floors", "building", "buildings",
    "developed", "developer", "development", "project", "community", "located", "location",
    "consists", "comprises", "contains", "completed", "completion", "handover", "opened",
    "award", "awards", "awarded", "certified", "certification", "standard", "standards",
    "school", "schools", "hospital", "clinic", "golf", "club", "station", "metro", "route",
    "minutes", "minute", "km", "kilometres", "kilometers", "amenity", "amenities",
    "studio", "studios", "bedroom", "bedrooms", "apartment", "apartments", "villa", "villas",
}

_FREEQA_MARKET_TERMS = {
    "aed", "rent", "rents", "rental", "price", "prices", "roi", "yield", "yields",
    "average rent", "average price", "sale price", "asking price",
}

_FREEQA_NONOFFICIAL_HINTS = {
    "blog", "news", "guide", "broker", "real estate", "property portal", "listing", "listings",
    "wikipedia", "tripadvisor", "reddit", "facebook", "instagram", "linkedin", "youtube",
}

_FREEQA_NUMBER_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
    "eighteen": 18, "nineteen": 19, "twenty": 20,
}


def _freeqa_tokens(text):
    return [x.lower() for x in re.findall(r"[A-Za-z0-9]+", text or "") if len(x) > 1]


def _freeqa_content_tokens(text):
    return [x for x in _freeqa_tokens(text) if x not in _FREEQA_GENERIC_WORDS]


def _freeqa_entity_phrase(text):
    """Best-effort proper-name extraction for English editorial copy."""
    text = re.sub(r"\s+", " ", text or "").strip()
    candidates = []
    pattern = re.compile(
        r"\b(?:The\s+)?(?:[A-Z][A-Za-z0-9&'’.-]*|[A-Z]{2,}|[A-Z]\d+|\d+[A-Z])"
        r"(?:\s+(?:[A-Z][A-Za-z0-9&'’.-]*|[A-Z]{2,}|[A-Z]\d+|\d+[A-Z])){1,6}\b"
    )
    for m in pattern.finditer(text):
        c = m.group(0).strip(" ,.;:()[]{}")
        c = re.sub(r"^The\s+", "", c)
        if len(c) < 5:
            continue
        if c.lower().startswith(("AED ", "FAQ ")):
            continue
        candidates.append(c)
    if not candidates:
        return ""
    # Prefer names containing project/entity words, then longest meaningful phrase.
    def score(c):
        low = c.lower()
        entity_bonus = 5 if any(k in low for k in [
            "tower", "residence", "residences", "heights", "club", "school", "hospital",
            "city", "community", "village", "golf", "hotel", "mall", "park", "academy"
        ]) else 0
        return entity_bonus + min(len(c.split()), 6)
    return max(candidates, key=score)


def _freeqa_split_sentences(text):
    parts = re.split(r"(?<=[.!?])\s+|\n+", text or "")
    out = []
    for part in parts:
        part = re.sub(r"\s+", " ", part).strip()
        if 30 <= len(part) <= 360 and len(part.split()) >= 5:
            out.append(part)
    return out


def _freeqa_claim_candidates(article_soup, body_text, target_topic=""):
    fields = _qa_editorial_fields(article_soup)
    items = []

    # IMPORTANT: ordinary ALT text is descriptive metadata, not automatically a factual
    # claim. Do not send every ALT through official-source verification. That created
    # false REVIEW rows for perfectly normal descriptions such as "Exterior view of ...".
    # ALT entity mismatches are handled separately by _freeqa_alt_entity_findings().

    # Captions can contain real factual claims, but only research them when they contain
    # a concrete factual signal. Purely descriptive captions are left alone.
    for cap in fields.get("image_captions", [])[:80]:
        cap = re.sub(r"\s+", " ", cap).strip()
        if len(cap) < 5:
            continue
        low = cap.lower()
        has_fact_signal = bool(
            re.search(r"\b\d+(?:[.,]\d+)?\b", cap)
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
        # Market figures are handled by the data layer; avoid pretending free web research
        # can validate live Bayut market data.
        if any(term in low for term in _FREEQA_MARKET_TERMS):
            continue
        tokens = set(_freeqa_tokens(sentence))
        score = 0
        if re.search(r"\b\d+(?:[.,]\d+)?\b", sentence):
            score += 4
        if any(term in tokens or term in low for term in _FREEQA_FACT_TERMS):
            score += 3
        if _freeqa_entity_phrase(sentence):
            score += 3
        if any(x in low for x in ["consists of", "comprises", "developed by", "located in", "won", "award", "certified", "built to", "completed in"]):
            score += 3
        if score >= 6:
            items.append({"text": sentence, "kind": "Factual Accuracy", "priority": score})

    # Deduplicate while preserving priority.
    seen = set()
    unique = []
    for item in sorted(items, key=lambda x: x["priority"], reverse=True):
        key = re.sub(r"\W+", " ", item["text"].lower()).strip()
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
        if len(unique) >= FREE_MAX_CLAIMS:
            break
    return unique


def _freeqa_ddg_url(href):
    href = html_lib.unescape(href or "").strip()
    if not href:
        return ""
    if href.startswith("//"):
        href = "https:" + href
    try:
        p = urlparse(href)
        if "duckduckgo.com" in (p.hostname or "") and p.path.startswith("/l/"):
            qs = parse_qs(p.query)
            if qs.get("uddg"):
                return unquote(qs["uddg"][0])
    except Exception:
        pass
    return href


@lru_cache(maxsize=256)
def _freeqa_search(query):
    """
    No-key public web search with conservative fallbacks.

    This remains free: no search API key is required. Search engines can rate-limit
    automated requests, so failure returns [] and never becomes evidence by itself.
    """
    results = []
    seen = set()

    def add(url, title="", snippet=""):
        url = _freeqa_ddg_url(url)
        if not url.startswith(("http://", "https://")):
            return
        key = normalized_destination(url)
        if not key or key in seen:
            return
        seen.add(key)
        results.append({
            "url": url,
            "title": re.sub(r"\s+", " ", title or "").strip(),
            "snippet": re.sub(r"\s+", " ", snippet or "").strip(),
        })

    # 1. DuckDuckGo HTML.
    try:
        r = requests.post(
            FREE_SEARCH_URL,
            data={"q": query},
            headers={**UA_DESKTOP, "Accept-Language": "en-US,en;q=0.8"},
            timeout=FREE_SEARCH_TIMEOUT,
        )
        if r.status_code == 200 and r.text:
            soup = BeautifulSoup(r.text, "html.parser")
            for box in soup.select(".result, .web-result"):
                a = box.select_one("a.result__a") or box.find("a", href=True)
                if not a:
                    continue
                snippet_node = box.select_one(".result__snippet")
                add(
                    a.get("href", ""),
                    a.get_text(" ", strip=True),
                    snippet_node.get_text(" ", strip=True) if snippet_node else "",
                )
                if len(results) >= FREE_MAX_SEARCH_RESULTS:
                    return results
    except Exception:
        pass

    # 2. Bing public HTML fallback.
    if len(results) < FREE_MAX_SEARCH_RESULTS:
        try:
            r = requests.get(
                "https://www.bing.com/search",
                params={"q": query, "count": FREE_MAX_SEARCH_RESULTS},
                headers={**UA_DESKTOP, "Accept-Language": "en-US,en;q=0.8"},
                timeout=FREE_SEARCH_TIMEOUT,
            )
            if r.status_code == 200 and r.text:
                soup = BeautifulSoup(r.text, "html.parser")
                for box in soup.select("li.b_algo"):
                    a = box.select_one("h2 a[href]")
                    if not a:
                        continue
                    snippet_node = box.select_one(".b_caption p") or box.find("p")
                    add(
                        a.get("href", ""),
                        a.get_text(" ", strip=True),
                        snippet_node.get_text(" ", strip=True) if snippet_node else "",
                    )
                    if len(results) >= FREE_MAX_SEARCH_RESULTS:
                        return results
        except Exception:
            pass

    # 3. Google HTML fallback. Only used when the first two engines are inconclusive.
    if len(results) < FREE_MAX_SEARCH_RESULTS:
        try:
            r = requests.get(
                "https://www.google.com/search",
                params={"q": query, "num": FREE_MAX_SEARCH_RESULTS},
                headers={**UA_DESKTOP, "Accept-Language": "en-US,en;q=0.8"},
                timeout=FREE_SEARCH_TIMEOUT,
            )
            if r.status_code == 200 and r.text:
                soup = BeautifulSoup(r.text, "html.parser")
                for a in soup.select("div.yuRUbf > a[href], a[href]"):
                    h3 = a.find("h3")
                    if not h3:
                        continue
                    href = a.get("href", "")
                    if href.startswith("/url?"):
                        try:
                            qs = parse_qs(urlparse(href).query)
                            href = qs.get("q", [""])[0]
                        except Exception:
                            pass
                    add(href, h3.get_text(" ", strip=True), "")
                    if len(results) >= FREE_MAX_SEARCH_RESULTS:
                        return results
        except Exception:
            pass

    return results


def _freeqa_is_government(url):
    host = _qa_host(url)
    return bool(
        host.endswith(".gov.ae") or host == "gov.ae" or
        host.endswith(".gov") or host.endswith(".gov.uk") or
        host in {"u.ae", "dld.gov.ae", "rta.ae", "dm.gov.ae", "visitdubai.com"}
    )


def _freeqa_entity_match_score(entity, title, snippet, url):
    if not entity:
        return 0.0
    e = set(_freeqa_content_tokens(entity))
    if not e:
        return 0.0
    hay = set(_freeqa_content_tokens(f"{title} {snippet} {_qa_host(url).replace('.', ' ')}"))
    return len(e & hay) / max(len(e), 1)


def _freeqa_official_candidate(result_item, entity="", context=""):
    url = result_item.get("url", "")
    if not url or _qa_blocked_source(url):
        return False, "none", 0.0

    host = _qa_host(url)
    text = f"{result_item.get('title','')} {result_item.get('snippet','')}".lower()
    if any(h in text for h in _FREEQA_NONOFFICIAL_HINTS):
        return False, "none", 0.0
    if _freeqa_is_government(url):
        return True, "government", 1.0

    em = _freeqa_entity_match_score(
        entity,
        result_item.get("title", ""),
        result_item.get("snippet", ""),
        url,
    )
    title_low = result_item.get("title", "").lower()
    snippet_low = result_item.get("snippet", "").lower()
    official_word = "official" in title_low or "official" in snippet_low

    host_tokens = set(_freeqa_content_tokens(host.replace(".", " ").replace("-", " ")))
    entity_tokens = set(_freeqa_content_tokens(entity))
    context_tokens = set(_freeqa_content_tokens(context))

    host_overlap = (
        len(host_tokens & entity_tokens) / max(len(entity_tokens), 1)
        if entity_tokens else 0.0
    )
    context_host_overlap = (
        len(host_tokens & context_tokens) / max(min(len(context_tokens), 4), 1)
        if context_tokens else 0.0
    )

    # Direct first-party domain match (e.g. elsclubdubai.com for The Els Club).
    if em >= 0.75 and (official_word or host_overlap >= 0.40):
        return True, "official_organisation", max(em, host_overlap)

    # Community/project official site can be branded by the parent entity rather than
    # the exact sub-project. Example: Victory Heights on DubaiSportsCity.ae.
    if em >= 0.75 and context_host_overlap >= 0.35:
        return True, "official_project", max(em, context_host_overlap)

    if em >= 0.90 and host_overlap >= 0.25:
        return True, "official_project", max(em, host_overlap)

    return False, "none", max(em, host_overlap, context_host_overlap)


@lru_cache(maxsize=256)
def _freeqa_fetch_source(url):
    try:
        r = requests.get(
            url,
            headers={**UA_DESKTOP, "Accept-Language": "en-US,en;q=0.8"},
            timeout=FREE_SOURCE_TIMEOUT,
            allow_redirects=True,
        )
        ctype = (r.headers.get("content-type") or "").lower()
        if r.status_code >= 400 or "html" not in ctype:
            return {"ok": False, "url": r.url, "title": "", "text": ""}
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["script", "style", "noscript", "svg"]):
            tag.decompose()
        title = re.sub(r"\s+", " ", (soup.title.get_text(" ", strip=True) if soup.title else ""))
        text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))[:120000]
        return {"ok": True, "url": r.url, "title": title, "text": text}
    except Exception:
        return {"ok": False, "url": url, "title": "", "text": ""}


def _freeqa_numbers(text):
    nums = set()
    low = (text or "").lower()
    for n in re.findall(r"\b\d{1,5}(?:[.,]\d+)?\b", low):
        try:
            nums.add(float(n.replace(",", "")))
        except Exception:
            pass
    for word, value in _FREEQA_NUMBER_WORDS.items():
        if re.search(rf"\b{re.escape(word)}\b", low):
            nums.add(float(value))
    return nums


def _freeqa_number_noun_pairs(text):
    low = (text or "").lower()
    pairs = []
    num_pattern = r"(?:\d{1,4}|" + "|".join(_FREEQA_NUMBER_WORDS.keys()) + r")"
    noun_pattern = r"(?:tower|towers|unit|units|floor|floors|building|buildings|bedroom|bedrooms|award|awards)"
    for m in re.finditer(rf"\b({num_pattern})\s+({noun_pattern})\b", low):
        raw = m.group(1)
        n = _FREEQA_NUMBER_WORDS.get(raw)
        if n is None:
            try:
                n = int(raw)
            except Exception:
                continue
        noun = m.group(2).rstrip("s")
        pairs.append((n, noun))
    return pairs


def _freeqa_similarity(a, b):
    at = set(_freeqa_content_tokens(a))
    bt = set(_freeqa_content_tokens(b))
    if not at:
        return 0.0
    return len(at & bt) / len(at)


def _freeqa_source_excerpt(source_text, entity, claim, max_chars=420):
    low = source_text.lower()
    needles = []
    if entity:
        needles.append(entity.lower())
    claim_tokens = [t for t in _freeqa_content_tokens(claim) if len(t) >= 5]
    needles.extend(claim_tokens[:4])
    positions = [low.find(n) for n in needles if n and low.find(n) >= 0]
    if not positions:
        return ""
    pos = min(positions)
    start = max(0, pos - 120)
    end = min(len(source_text), pos + max_chars)
    return re.sub(r"\s+", " ", source_text[start:end]).strip()


def _freeqa_verify_claim(claim, kind, target_topic=""):
    entity = _freeqa_entity_phrase(claim)
    query_terms = entity or " ".join(_freeqa_content_tokens(claim)[:8])
    context = target_topic if target_topic and target_topic.lower() not in query_terms.lower() else ""
    query = f'"{query_terms}" {context} official'.strip()
    results = _freeqa_search(query)

    # If the exact entity was probably mistyped, a less quoted fallback can surface the real official entity.
    if not results and entity:
        results = _freeqa_search(f"{entity} {context} official")

    candidates = []
    for item in results:
        ok, source_type, confidence = _freeqa_official_candidate(item, entity=entity, context=target_topic)
        if ok:
            candidates.append((confidence, source_type, item))
    candidates.sort(key=lambda x: x[0], reverse=True)

    if not candidates:
        return {
            "status": REVIEW,
            "result": f"Needs verification. No sufficiently reliable official source was discovered automatically for: ‘{claim}’.",
            "action": "Verify this claim manually with an official or primary source before changing the article.",
            "source": "",
            "source_type": "none",
            "evidence": "",
        }

    # Test up to three plausible official pages.
    best_review = None
    for _, source_type, item in candidates[:3]:
        fetched = _freeqa_fetch_source(item["url"])
        if not fetched["ok"]:
            continue
        source_text = fetched["text"]
        source_url = fetched["url"]
        source_title = fetched["title"] or item.get("title", "") or _qa_host(source_url)
        entity_score = _freeqa_similarity(entity, f"{source_title} {source_text[:5000]}") if entity else 1.0
        claim_score = _freeqa_similarity(claim, source_text)
        claim_nums = _freeqa_numbers(claim)
        source_nums = _freeqa_numbers(source_text)
        pairs_claim = _freeqa_number_noun_pairs(claim)
        pairs_source = _freeqa_number_noun_pairs(source_text)
        excerpt = _freeqa_source_excerpt(source_text, entity, claim)

        # Direct numeric contradiction: same factual noun, different official number, and the claimed pair is absent.
        for claimed_n, noun in pairs_claim:
            official_for_noun = {n for n, n_noun in pairs_source if n_noun == noun}
            if official_for_noun and claimed_n not in official_for_noun and entity_score >= 0.55:
                shown = ", ".join(str(int(x)) for x in sorted(official_for_noun)[:6])
                return {
                    "status": FAIL,
                    "result": (
                        f"Official-source contradiction. The article states ‘{claim}’, while the official page "
                        f"uses {shown} for {noun}(s) in the matching entity context."
                    ),
                    "action": "Correct the article only after reviewing the cited official page and matching the exact entity/context.",
                    "source": f"{source_title} | {source_url}",
                    "source_type": source_type,
                    "evidence": excerpt,
                }

        # Direct confirmation: source contains the entity, the important terms, and all specific numbers.
        numbers_ok = not claim_nums or claim_nums.issubset(source_nums)
        if entity_score >= 0.65 and claim_score >= 0.52 and numbers_ok:
            return {
                "status": PASS,
                "result": f"No issue. The official source directly supports the article claim: ‘{claim}’.",
                "action": "No action required.",
                "source": f"{source_title} | {source_url}",
                "source_type": source_type,
                "evidence": excerpt,
            }

        review = {
            "status": REVIEW,
            "result": (
                f"Needs verification. An official-looking source was found for {entity or 'this topic'}, "
                "but the page text retrieved automatically does not confirm or directly contradict the full article claim."
            ),
            "action": "Review the cited official page manually before changing the article.",
            "source": f"{source_title} | {source_url}",
            "source_type": source_type,
            "evidence": excerpt,
        }
        if best_review is None or claim_score > best_review[0]:
            best_review = (claim_score, review)

    if best_review:
        return best_review[1]

    return {
        "status": REVIEW,
        "result": f"Needs verification. Official search results were found, but the source pages could not be fetched reliably for: ‘{claim}’.",
        "action": "Open an official source manually and verify the claim before changing the article.",
        "source": "",
        "source_type": "none",
        "evidence": "",
    }



_FREEQA_ALT_ENTITY_SUFFIXES = {
    "residence", "residences", "tower", "towers", "heights", "club", "city",
    "community", "village", "gardens", "estate", "estates", "park", "school",
    "academy", "hospital", "clinic", "mall", "hotel", "stadium", "centre", "center",
}


def _freeqa_alt_entity_phrases(alt_text):
    """Extract likely named entities from ALT text without treating the whole ALT as a claim."""
    text = re.sub(r"\s+", " ", alt_text or "").strip()
    if not text:
        return []
    suffix_pattern = "|".join(sorted(_FREEQA_ALT_ENTITY_SUFFIXES, key=len, reverse=True))
    pattern = re.compile(
        rf"\b((?:[A-Z][A-Za-z0-9&'’.-]*\s+){{0,5}}(?:{suffix_pattern}))\b",
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
    return {
        "residences": "residence",
        "towers": "tower",
        "estates": "estate",
    }.get(last, last)


def _freeqa_alt_entity_findings(article_soup, target_topic=""):
    """
    Flag ALT entity names only when there is a specific mismatch AND an official source
    confirms the competing article entity name. Normal descriptive ALTs are not findings.
    """
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
                # Exact entity spelling already exists in the article: no issue.
                continue

            alt_suffix = _freeqa_entity_suffix_key(alt_entity)
            same_suffix = [
                entity for entity in known_entities
                if _freeqa_entity_suffix_key(entity) == alt_suffix
            ]
            if not same_suffix:
                continue

            scored = []
            for entity in same_suffix:
                ratio = SequenceMatcher(
                    None, entity_similarity_key(alt_entity), entity_similarity_key(entity)
                ).ratio()
                scored.append((ratio, entity))
            scored.sort(reverse=True)
            best_ratio, expected_entity = scored[0]

            # Conservative candidate rule: a close spelling variant, or the only named
            # entity in the article using that distinctive project suffix.
            if best_ratio < 0.68 and len(same_suffix) != 1:
                continue

            pair_key = (alt_key, entity_similarity_key(expected_entity))
            if pair_key in seen:
                continue
            seen.add(pair_key)

            verification = _freeqa_verify_claim(
                expected_entity, "Entity Accuracy", target_topic=target_topic
            )
            if verification.get("status") != PASS or not verification.get("source"):
                # Do not create another noisy REVIEW just because free search could not
                # prove the entity name. Precision is more useful than volume here.
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
                    "The system first found a specific entity-name mismatch between the ALT text and "
                    "the article, then required an official-source confirmation before flagging it."
                ),
                "Official Source": verification.get("source", ""),
                "Finding Type": "Entity Accuracy",
                "_internal_status": FAIL,
                "_rule": dict(CONTENT_RULES).get("Official Source Verification", ""),
                "_system_uses": "ALT entity extraction + article entity consistency + official source confirmation",
                "_evidence_finding": True,
            })

    return rows

def _qa_title_case_heading(value):
    """Bayut-style English Title Case while keeping short connector words lowercase."""
    text = re.sub(r"\s+", " ", value or "").strip()
    if not text:
        return text

    terminal = ""
    if text[-1:] in "?!:":
        terminal = text[-1]
        text = text[:-1].rstrip()

    small = {"a", "an", "and", "as", "at", "but", "by", "for", "from", "in", "nor", "of", "on", "or", "per", "the", "to", "via", "vs", "with"}
    acronyms = {"UAE", "AED", "ROI", "FAQ", "FAQs", "JVC", "JLT", "JBR", "DIFC", "RTA", "DLD", "MBR"}
    parts = text.split()
    fixed = []

    for i, token in enumerate(parts):
        raw = token
        prefix = ""
        suffix = ""
        while raw and not raw[0].isalnum():
            prefix += raw[0]
            raw = raw[1:]
        while raw and not raw[-1].isalnum():
            suffix = raw[-1] + suffix
            raw = raw[:-1]

        if not raw:
            fixed.append(token)
            continue
        if raw.upper() in acronyms:
            core = raw.upper()
        elif i not in {0, len(parts) - 1} and raw.casefold() in small:
            core = raw.casefold()
        elif raw[:1].isdigit():
            # Keep 1-bedroom / 3BR style tokens stable.
            core = raw
        else:
            # Title-case hyphenated words without damaging apostrophes/numbers.
            core = "-".join(x[:1].upper() + x[1:].lower() if x else x for x in raw.split("-"))
        fixed.append(prefix + core + suffix)

    corrected = " ".join(fixed)
    first = parts[0].casefold() if parts else ""
    if not terminal and first in {"where", "what", "why", "which", "who", "when"}:
        terminal = "?"
    return corrected + terminal


def _freeqa_local_findings(article_soup, body_text, target_topic=""):
    """Free high-confidence editorial checks that do not need external evidence."""
    rows = []
    fields = _qa_editorial_fields(article_soup)
    texts = [("Article text", body_text)]
    texts += [("Image Alt Text", x) for x in fields.get("image_alts", [])]
    texts += [("Image Caption", x) for x in fields.get("image_captions", [])]

    seen = set()

    def add_local(finding_type, issue, result_text, action, location="Article text", source="Article itself"):
        key = (finding_type, re.sub(r"\s+", " ", issue).casefold())
        if key in seen:
            return
        seen.add(key)
        rows.append({
            "Check": issue,
            "Status": FAIL,
            "Result": result_text + (f" Location: {location}." if location != "Article text" else ""),
            "Action Needed": action,
            "Why": "High-confidence editorial rule based on the article itself; no external source is required.",
            "Official Source": source,
            "Finding Type": finding_type,
            "_internal_status": FAIL,
            "_rule": dict(CONTENT_RULES).get("Official Source Verification", ""),
            "_system_uses": "Free deterministic editorial QA checks",
            "_evidence_finding": True,
        })

    for location, text in texts:
        low = (text or "").lower()

        if re.search(r"\bthat[’']?s a wrap\s+our\b", low):
            add_local(
                "Grammar & Wording",
                "That’s a wrap our round-up → That’s a wrap on our round-up",
                "Grammar error. The preposition ‘on’ is missing.",
                "Change it to: “That’s a wrap on our round-up”.",
                location,
            )

        if re.search(r"\baverage\b[^.!?]{0,120}\bstarts? from\b", low):
            m = re.search(r"[^.!?]{0,80}\baverage\b[^.!?]{0,120}\bstarts? from\b[^.!?]{0,80}", text, flags=re.I)
            excerpt = re.sub(r"\s+", " ", m.group(0)).strip() if m else "average ... starts from"
            add_local(
                "Grammar & Wording",
                excerpt,
                "Incorrect data wording. An average does not ‘start from’ a value.",
                "Use ‘The average … is X’ for an average, or ‘… starts from X’ only for a minimum/starting value.",
                location,
            )

        if re.search(r"\bi\s+nto\b", text, flags=re.I):
            add_local(
                "Grammar & Wording",
                "i nto → into",
                "Typographical error. The word ‘into’ has been split incorrectly.",
                "Replace ‘i nto’ with ‘into’.",
                location,
            )

        # Subject-verb agreement for a singular named Residence/Club/Tower.
        m = re.search(r"\b([A-Z][A-Za-z0-9&'’.-]*(?:\s+[A-Z][A-Za-z0-9&'’.-]*){1,5}\s+(?:Residence|Club|Tower))\s+offer\b", text or "")
        if m:
            add_local(
                "Grammar & Wording",
                f"{m.group(1)} offer → {m.group(1)} offers",
                "Subject-verb agreement error. The named entity is singular.",
                f"Change ‘{m.group(1)} offer’ to ‘{m.group(1)} offers’.",
                location,
            )

        # Awkward duplicate determiner: 'the spectacular The Els Club'.
        m = re.search(
            r"\bthe\s+(?:spectacular|stunning|beautiful|iconic|impressive|famous)\s+(The\s+[A-Z][A-Za-z0-9&'’.-]*(?:\s+[A-Z][A-Za-z0-9&'’.-]*){1,5})",
            text or "",
            flags=re.I,
        )
        if m:
            entity = re.sub(r"\s+", " ", m.group(1)).strip()
            add_local(
                "Grammar & Wording",
                f"the spectacular {entity} → {entity}",
                "Awkward grammatical construction caused by a duplicated determiner and promotional adjective.",
                f"Use ‘{entity}’ without ‘the spectacular’.",
                location,
            )

        # Coordinated plural bedrooms/units incorrectly paired with singular rent/unit/is.
        m = re.search(
            r"\bthe\s+average\s+annual\s+rent\s+for\s+(?:a\s+)?(\d+)\s+and\s+(\d+)\s*[- ]\s*bed(?:room)?\s+unit\s+is\b",
            text or "",
            flags=re.I,
        )
        if m:
            a, b = m.group(1), m.group(2)
            add_local(
                "Grammar & Wording",
                f"The average annual rent for a {a} and {b}-bed unit is…",
                "Singular/plural agreement error. Two unit types are being discussed, so the noun and verb should be plural.",
                f"Use ‘The average annual rents for {a} and {b}-bedroom units are…’.",
                location,
            )

        # Space before punctuation, e.g. 'Dubai , Dubai Sports City'.
        m = re.search(r"\b([A-Za-z][A-Za-z'’.-]*)\s+([,;:.!?])", text or "")
        if m:
            bad = f"{m.group(1)} {m.group(2)}"
            good = f"{m.group(1)}{m.group(2)}"
            add_local(
                "Grammar & Wording",
                f"{bad} → {good}",
                "Incorrect spacing before punctuation.",
                f"Remove the space before ‘{m.group(2)}’.",
                location,
            )

    # English editorial heading case. Only flag headings with 4+ words to avoid
    # over-policing short proper names/project headings.
    for item in heading_sections(article_soup):
        heading = re.sub(r"\s+", " ", (item.get("heading") or "")).strip()
        if not heading or len(heading.split()) < 4 or re.search(r"[\u0600-\u06FF]", heading):
            continue
        corrected = _qa_title_case_heading(heading)
        if corrected != heading:
            # Ignore changes that only affect a terminal colon on non-question headings.
            add_local(
                "Heading / SEO",
                f"{heading} → {corrected}",
                "Editorial heading is not in the required English Title Case/question format.",
                f"Change the heading to ‘{corrected}’.",
                "Heading",
            )

    # Promotional/fluffy wording. Report a single editorial-style issue with all matches.
    promo_patterns = [
        (r"\bgreat option\b", "great option"),
        (r"\bperfect(?: choice| option)?\b", "perfect"),
        (r"\bspectacular\b", "spectacular"),
        (r"\bhighly sought[- ]after\b", "highly sought-after"),
    ]
    promo_hits = []
    low_body = (body_text or "").lower()
    for pattern, label in promo_patterns:
        if re.search(pattern, low_body, flags=re.I):
            promo_hits.append(label)
    if promo_hits:
        listed = ", ".join(f"‘{x}’" for x in promo_hits)
        add_local(
            "Editorial Style",
            "Promotional/fluffy wording",
            f"Promotional or subjective wording detected: {listed}. These phrases add little verifiable information.",
            "Reduce or replace these phrases with specific, factual descriptions where possible.",
        )

    # Search-intent mismatch for rental pages with investment FAQ/question wording.
    topic_low = (target_topic or "").lower()
    if any(k in topic_low for k in ["rent", "rental", "renting"]):
        for item in heading_sections(article_soup):
            h = (item.get("heading") or "").strip()
            section = (item.get("section") or "").strip()
            combined = f"{h} {section}".lower()
            if "invest" in combined and any(q in combined for q in ["popular", "area", "where", "best"]):
                issue = h or "Investment FAQ"
                add_local(
                    "Search Intent",
                    issue,
                    "Search-intent mismatch. This investment-focused FAQ/section does not closely match the page’s rental intent.",
                    "Replace it with a rental-focused FAQ or section.",
                )
                break

    return rows


def _summary_issue_row(check_name, items, no_issue_text, source_default="", why_text=""):
    """Create one compact Content table row containing numbered issues in Result."""
    if not items:
        row = {
            "Check": check_name,
            "Status": PASS,
            "Result": no_issue_text,
            "Action Needed": "No action required.",
            "Why": why_text,
            "Official Source": source_default,
            "Finding Type": check_name,
            "_internal_status": PASS,
            "_rule": dict(CONTENT_RULES).get("Official Source Verification", ""),
            "_system_uses": SYSTEM_USES.get("Official Source Verification", "Content issue aggregation"),
            "_evidence_finding": True,
        }
        return row

    result_lines = []
    action_lines = []
    source_lines = []
    seen_sources = set()
    for number, item in enumerate(items, start=1):
        title = re.sub(r"\s+", " ", str(item.get("Check", "Issue") or "Issue")).strip()
        detail = re.sub(r"\s+", " ", str(item.get("Result", "") or "")).strip()
        action = re.sub(r"\s+", " ", str(item.get("Action Needed", "") or "")).strip()
        source = re.sub(r"\s+", " ", str(item.get("Official Source", "") or "")).strip()

        result_lines.append(f"{number}. {title}: {detail}")
        if action:
            action_lines.append(f"{number}. {action}")
        if source and source not in seen_sources:
            seen_sources.add(source)
            source_lines.append(f"{number}. {source}")

    return {
        "Check": check_name,
        "Status": FAIL,
        "Result": "\n".join(result_lines),
        "Action Needed": "\n".join(action_lines) if action_lines else "Review and correct the listed issues.",
        "Why": why_text,
        "Official Source": "\n".join(source_lines) if source_lines else source_default,
        "Finding Type": check_name,
        "_internal_status": FAIL,
        "_rule": dict(CONTENT_RULES).get("Official Source Verification", ""),
        "_system_uses": SYSTEM_USES.get("Official Source Verification", "Content issue aggregation"),
        "_evidence_finding": True,
    }


def official_source_content_checks(url, soup, body_text, focus_keyword="", secondary_keywords=None):
    """
    Compact issue-summary rows for the Content table.

    Factual rule:
    - Facts Issues contains ONLY claims directly contradicted by a fetched official/primary source.
    - Unverified claims are omitted instead of being labelled incorrect.
    """
    try:
        article_soup = main_content_node(soup)
        title = title_text(soup)
        h1 = page_primary_h1(soup)
        target_topic = focus_keyword or title or h1

        local_rows = _freeqa_local_findings(article_soup, body_text, target_topic=target_topic)
        alt_rows = _freeqa_alt_entity_findings(article_soup, target_topic=target_topic)

        grammar_items = [r for r in local_rows if r.get("Finding Type") == "Grammar & Wording" and r.get("Status") == FAIL]
        heading_items = [r for r in local_rows if r.get("Finding Type") == "Heading / SEO" and r.get("Status") == FAIL]
        style_items = [r for r in local_rows if r.get("Finding Type") == "Editorial Style" and r.get("Status") == FAIL]
        intent_items = [r for r in local_rows if r.get("Finding Type") == "Search Intent" and r.get("Status") == FAIL]
        entity_items = [
            r for r in alt_rows
            if r.get("Finding Type") == "Entity Accuracy"
            and r.get("Status") == FAIL
            and r.get("Official Source")
        ]

        # Internal-link destination title-tag mismatches.
        link_items = []
        inventory = content_internal_link_inventory(article_soup, url)
        for issue in internal_link_title_mismatches(inventory):
            link_items.append({
                "Check": f"{issue.get('anchor_text', 'Internal link')} internal link",
                "Status": FAIL,
                "Result": (
                    f"Destination page has an unrelated title tag: ‘{issue.get('target_title', '')}’. "
                    f"The linked anchor is ‘{issue.get('anchor_text', '')}’."
                ),
                "Action Needed": "Correct the destination page title tag or update the link if it points to the wrong page.",
                "Why": "The named internal-link anchor has essentially no semantic overlap with the destination title tag.",
                "Official Source": issue.get("final_url") or issue.get("url", ""),
                "Finding Type": "Internal Link",
            })

        # Research factual candidates, but keep ONLY officially proven contradictions.
        fact_items = []
        candidates = _freeqa_claim_candidates(article_soup, body_text, target_topic=target_topic)
        for item in candidates:
            claim = item["text"]
            kind = item["kind"]
            verification = _freeqa_verify_claim(claim, kind, target_topic=target_topic)
            if verification.get("status") != FAIL:
                continue
            source = re.sub(r"\s+", " ", str(verification.get("source", "") or "")).strip()
            if not source:
                continue
            fact_items.append({
                "Check": _freeqa_entity_phrase(claim) or claim[:90],
                "Status": FAIL,
                "Result": verification.get("result", "Official-source contradiction found."),
                "Action Needed": verification.get("action", "Correct the factual statement using the cited official source."),
                "Why": "A direct contradiction was found on an official or primary source.",
                "Official Source": source,
                "Finding Type": "Factual Accuracy",
            })

        return [
            _summary_issue_row(
                "Grammar Issues", grammar_items,
                "No high-confidence grammar, typo, punctuation or data-wording mistakes were found.",
                source_default="Article itself",
                why_text="Lists high-confidence grammar, typo, punctuation and wording mistakes detected directly in article text, captions or ALT text.",
            ),
            _summary_issue_row(
                "Facts Issues", fact_items,
                "No factual error was proven from an official source in this audit.",
                source_default="",
                why_text="Only factual statements directly contradicted by a fetched official or primary source are listed. Unverified claims are omitted.",
            ),
            _summary_issue_row(
                "Entity / Image Issues", entity_items,
                "No officially confirmed entity-name mistake was found in image ALT text.",
                source_default="",
                why_text="Normal descriptive ALT text is not treated as a factual claim. Only specific entity-name mismatches confirmed by an official source are listed.",
            ),
            _summary_issue_row(
                "Heading / SEO Issues", heading_items,
                "No clear heading-case or heading-format issue was found.",
                source_default="Article itself",
                why_text="Checks English editorial headings for the required Title Case/question format.",
            ),
            _summary_issue_row(
                "Internal Link Issues", link_items,
                "No named internal link was found pointing to a page with an unrelated title tag.",
                source_default="",
                why_text="Fetches destination title tags for named internal editorial links and flags strong entity/title mismatches.",
            ),
            _summary_issue_row(
                "Search Intent Issues", intent_items,
                "No clear search-intent mismatch was found by the focused article checks.",
                source_default="Article itself",
                why_text="Lists clear sections or FAQs that conflict with the article's primary intent.",
            ),
            _summary_issue_row(
                "Editorial Style Issues", style_items,
                "No configured promotional/fluffy wording was found.",
                source_default="Article itself",
                why_text="Flags subjective promotional wording that should be replaced with specific factual language where possible.",
            ),
        ]

    except Exception as exc:
        # Never fabricate an issue because a free network/search check failed.
        return [
            _summary_issue_row("Grammar Issues", [], "Grammar summary could not be completed in this run.", source_default="Article itself", why_text=f"Content summary encountered {type(exc).__name__}."),
            _summary_issue_row("Facts Issues", [], "No factual error was proven from an official source in this audit.", why_text="Search/network failure is not evidence that a fact is wrong."),
            _summary_issue_row("Entity / Image Issues", [], "No officially confirmed entity-name mistake was produced in this run.", why_text="ALT descriptions are not flagged just because a source could not be found."),
            _summary_issue_row("Heading / SEO Issues", [], "No confirmed heading-format issue was produced in this run.", source_default="Article itself", why_text="No speculative issue was added."),
            _summary_issue_row("Internal Link Issues", [], "No confirmed destination-title mismatch was produced in this run.", why_text="Network failure is not treated as a link-title mismatch."),
            _summary_issue_row("Search Intent Issues", [], "No confirmed search-intent issue was produced in this run.", source_default="Article itself", why_text="No speculative issue was added."),
            _summary_issue_row("Editorial Style Issues", [], "No configured promotional/fluffy wording was produced in this run.", source_default="Article itself", why_text="No speculative issue was added."),
        ]


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

    keyword_use_text = keyword_stuffing_editorial_text(soup)

    kw_assessment = keyword_repetition_assessment(
        keyword_use_text,
        focus_keyword,
        secondary_keywords,
        title=title,
        h1=h1,
        url=url,
    )

    if kw_assessment["status"] == PASS:
        keyword_use_finding = (
            "Keywords are used naturally in the editorial content."
        )
    else:
        keyword_use_parts = []

        # Show only target phrases that are actually repeated enough to matter.
        material_targets = [
            (kw, exact, per_1000)
            for kw, exact, per_1000 in kw_assessment["targets"]
            if exact > 0 and per_1000 >= 10
        ]

        if material_targets:
            keyword_use_parts.append(
                "Repeated target phrase(s): "
                + "; ".join(
                    f"{kw}: {exact} use(s), {per_1000:.1f} per 1,000 words"
                    for kw, exact, per_1000 in material_targets[:5]
                )
            )

        # If the issue comes from a non-target repeated phrase, show it only
        # after widgets and interface content have already been excluded.
        if (
            not material_targets
            and kw_assessment["gram"]
            and not kw_assessment["primary_topic"]
        ):
            keyword_use_parts.append(
                f"Repeated phrase: '{kw_assessment['gram']}' "
                f"({kw_assessment['count']} uses; "
                f"{kw_assessment['density']:.1%} of two word phrases)"
            )

        if not keyword_use_parts:
            keyword_use_parts.append(kw_assessment["reason"])

        keyword_use_finding = ". ".join(keyword_use_parts) + "."

    rows.append(result(
        "Keyword Use",
        kw_assessment["status"],
        keyword_use_finding,
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

        if hstatus == PASS and relevant == len(section_items):
            hfind = f"All {len(section_items)} article sections are relevant to the main topic."
        elif hstatus == PASS:
            hfind = f"{relevant} of {len(section_items)} article sections are relevant to the main topic."
        else:
            hfind = (
                f"{len(section_items) - relevant} of {len(section_items)} article sections may be weakly related to the main topic."
            )
            if weak_examples:
                hfind += " Examples: " + "; ".join(weak_examples) + "."
    else:
        hstatus = REVIEW
        hfind = "No H2 to H4 headings were available for contextual heading relevance assessment."
    rows.append(result("Heading Relevance", hstatus, hfind, rules["Heading Relevance"]))

    raw_source_claims = source_quality_claim_examples(article_soup, url, limit=60)
    source_claims = raw_source_claims

    unsupported_source_claims = [
        item for item in source_claims
        if not item.get("supported")
    ]

    if unsupported_source_claims:
        sq = REVIEW
        source_targets = unsupported_source_claims[:8]

        numbered_claims = [
            f"{index}: {item['claim']}"
            for index, item in enumerate(source_targets, start=1)
        ]
        sf = (
            f"{len(unsupported_source_claims)} official source claim(s) need attribution.\n"
            + "\n".join(numbered_claims)
        )

        numbered_actions = [
            f"{index}: Add an official or authoritative source beside this claim."
            for index, _item in enumerate(source_targets, start=1)
        ]
        source_action = "\n".join(numbered_actions)
    else:
        sq = PASS
        source_targets = []
        sf = "No official source quality issues found."
        source_action = ""

    rows.append(result(
        "Source Quality",
        sq,
        sf,
        rules["Source Quality"],
        source_action,
    ))

    conflicts = numeric_statement_conflicts(article_soup)

    if conflicts:
        data_status = REVIEW
        data_targets = conflicts[:8]

        numbered_conflicts = [
            (
                f"{index}: Section: {item['section']} | "
                f"Previous: {item['previous_statement']} | "
                f"Current: {item['statement']}"
            )
            for index, item in enumerate(data_targets, start=1)
        ]

        data_finding = (
            f"{len(conflicts)} internal numeric contradiction(s) found within the same article section.\n"
            + "\n".join(numbered_conflicts)
        )

        data_action = "\n".join(
            f"{index}: Verify which value is correct within this section."
            for index, _item in enumerate(data_targets, start=1)
        )
    else:
        data_status = PASS
        data_finding = "No internal numeric contradictions found within the same article context."
        data_action = ""

    rows.append(result(
        "Data Accuracy",
        data_status,
        data_finding,
        rules["Data Accuracy"],
        data_action,
    ))

    spelling_text = keyword_stuffing_editorial_text(soup)
    spelling_issues = likely_misspellings(spelling_text, limit=12)

    if spelling_issues:
        spelling_status = REVIEW
        spelling_targets = spelling_issues[:12]
        spelling_finding = (
            f"{len(spelling_targets)} likely misspelling(s) found.\n"
            + "\n".join(
                f"{index}: {item['word']} → {item['suggestion']}"
                + (f" ({item['count']} uses)" if item['count'] > 1 else "")
                for index, item in enumerate(spelling_targets, start=1)
            )
        )
        spelling_action = "\n".join(
            f"{index}: Check and correct '{item['word']}' if '{item['suggestion']}' is the intended word."
            for index, item in enumerate(spelling_targets, start=1)
        )
    else:
        spelling_status = PASS
        spelling_finding = "No likely misspellings found in the editorial content."
        spelling_action = ""

    rows.append(result(
        "Misspelling",
        spelling_status,
        spelling_finding,
        rules["Misspelling"],
        spelling_action,
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

        audit_status.write(f"{APP_VERSION}  1 of 5  Fetching Desktop, Mobile and Googlebot versions in parallel")
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
            "2 of 5  Running Spam, Content, Sitemap, Robots, Internal Link, External Link and Resource checks in parallel"
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

        audit_status.write("3 of 5  Running free official-source Content verification")
        evidence_content_rows = official_source_content_checks(
            desktop_r.url,
            soup_of(desktop_r.text),
            body_text,
            focus_keyword,
            secondary_keywords,
        )
        content_rows.extend(evidence_content_rows)

        sitemap_result = parallel_results["Sitemap"]
        internal_validation = parallel_results["Internal Links"]
        external_validation = parallel_results["External Links"]
        resource_validation = parallel_results["Resources"]
        robots_txt_result = parallel_results["Robots"]

        audit_status.write("4 of 5  Finalising SEO checks")
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
        audit_status.write("5 of 5  Preparing results")
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

        for tab_index, (tab, rows) in enumerate(zip(tabs, [spam_rows, seo_rows, content_rows])):
            with tab:
                def status_style(value):
                    if value == "PASS":
                        return "color: #28B16D; font-weight: 800;"
                    if value == "REVIEW":
                        return "color: #B7791F; font-weight: 800;"
                    if value == "FAIL":
                        return "color: #C53030; font-weight: 800;"
                    return ""

                # Spam, SEO and Content all keep the same table-first layout.
                # Content-specific issue categories are represented as rows inside this table.
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

        report_generated_at = datetime.now(timezone.utc).isoformat()

        excel_report = build_audit_excel_report(
            url_requested=url,
            url_final=desktop_r.url,
            focus_keyword=focus_keyword,
            secondary_keywords=secondary_keywords,
            spam_rows=spam_rows,
            seo_rows=seo_rows,
            content_rows=content_rows,
            spam_status=spam_status,
            spam_counts=spam_counts,
            seo_status=seo_status,
            seo_counts=seo_counts,
            content_status=content_status,
            content_counts=content_counts,
            generated_at_utc=report_generated_at,
            total_audit_time=total_audit_time,
            desktop_status_code=desktop_r.status_code,
            extracted_words=word_count(body_text),
        )

        st.download_button(
            "Download audit report Excel",
            data=excel_report,
            file_name="url_audit_report_v18_26.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        with st.expander("Important interpretation notes"):
            st.markdown(
                """
                This Excel report was generated by the engine version displayed at the top of the app. Version details are stored in the Summary sheet.

                Every rule receives one of three statuses: PASS, REVIEW or FAIL.

                Result shows exactly what the system found.

                Why explains the data and rule used to reach that status and result.

                When a rule cannot be fully verified from one URL, it can receive REVIEW and the Result explains what additional verification is required.

                The Googlebot check uses a Googlebot-like User Agent comparison. It does not reproduce Google's full rendering and indexing infrastructure.
                Access errors, HTTP 401/403/405/406/429 responses, CAPTCHA and short bot-challenge pages are classified as Crawler Access Issue and are never treated as cloaking proof by themselves.

                External plagiarism may require external verification.

                Content word count and repetition thresholds are internal QA heuristics and are not Google thresholds.

                Hidden content inspection uses a rendered Chromium browser when Playwright and Chromium are available. If Chromium is unavailable, the system falls back to static HTML inspection.

                Network heavy checks are parallelised and cached. Sitemap inspection has a strict time and file budget so it cannot hold the interface indefinitely.

                Content QA uses an isolated editorial article body and excludes comments, related posts, popular widgets, sidebars, navigation and other page chrome before calculating content results.
                Official-source Content verification is free and requires no API key. It uses public search result retrieval plus direct official-page fetching. If search is rate-limited or evidence is insufficient, the system returns REVIEW instead of guessing.

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
        (c, ICON_DOC, f'<span>Content</span> {len(CONTENT_RULES)} rules', 'Intent, relevance, thinness, originality, freshness, repetition, sourcing, accuracy, spelling and readability.'),
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
