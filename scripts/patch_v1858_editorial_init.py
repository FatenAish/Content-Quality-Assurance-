from pathlib import Path
import py_compile
import re

path = Path('app.py')
text = path.read_text(encoding='utf-8')

text = re.sub(
    r'APP_VERSION = "[^"]+"',
    'APP_VERSION = "V18.58 EDITORIAL INIT FIX"',
    text,
    count=1,
)
text = re.sub(
    r'ENGINE_BUILD = "[^"]+"',
    'ENGINE_BUILD = "2026.08.17.58"',
    text,
    count=1,
)

fn_start = text.find('def audit_content(url, soup, body_text, focus_keyword="", secondary_keywords=None):')
if fn_start < 0:
    raise RuntimeError('audit_content() not found')
fn_end = text.find('\ndef ', fn_start + 10)
if fn_end < 0:
    fn_end = len(text)
block = text[fn_start:fn_end]

init_code = '''    editorial_quality_issues = deterministic_editorial_quality_issues(\n        article_soup,\n        limit=30,\n    )\n\n'''

if 'editorial_quality_issues = deterministic_editorial_quality_issues(' not in block:
    anchor = '    article_soup = main_content_node(soup)\n    body_text = clean_text(article_soup)\n\n'
    if anchor not in block:
        raise RuntimeError('audit_content article_soup/body_text anchor not found')
    block = block.replace(anchor, anchor + init_code, 1)

old_status = '    gr = REVIEW if avg > 32 or malformed >= 4 else PASS\n'
new_status = '    gr = REVIEW if editorial_quality_issues or avg > 32 or malformed >= 4 else PASS\n'
if old_status in block:
    block = block.replace(old_status, new_status, 1)
elif new_status not in block:
    raise RuntimeError('Grammar status line not found')

# Ensure initialization occurs before first use.
init_pos = block.find('editorial_quality_issues = deterministic_editorial_quality_issues(')
use_pos = block.find('if editorial_quality_issues:')
if init_pos < 0 or use_pos < 0 or init_pos > use_pos:
    raise RuntimeError('editorial_quality_issues is not initialized before use')

text = text[:fn_start] + block + text[fn_end:]
path.write_text(text, encoding='utf-8')
py_compile.compile(str(path), doraise=True)

print('Patched app.py to V18.58')
print('editorial_quality_issues initialized before use: PASS')
print('Grammar status considers editorial issues: PASS')
print('py_compile: PASS')
