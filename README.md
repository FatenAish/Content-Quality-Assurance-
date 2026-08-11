Bayut URL Quality Auditor
A single-URL audit app with three separate result groups:
Spam Check — 16 rules
SEO Check — 20 rules
Content Check — 20 rules
Run
```bash
pip install -r requirements.txt
streamlit run app.py
```
Then paste one article URL and click Run URL Audit.
Design
The UI uses a Bayut-inspired green palette. The main green in this prototype is `#28B16D`, derived from a widely circulated Bayut logo asset. The app does not bundle or redistribute any Bayut font or proprietary brand asset.
Result meanings
PASS: no issue found under the current rule
REVIEW: suspicious/inconclusive; human or external-source verification needed
FAIL: strong rule violation / serious issue detected
Important limitations
This is a first working rule-engine version. It can automatically inspect fetched HTML, metadata, links, redirects, basic crawler/mobile differences, scripts and content patterns.
Some checks cannot be proven from one URL alone without another data source or a browser/search API. Those checks intentionally return REVIEW when evidence is insufficient rather than pretending the URL is safe.
Examples:
external copied/scraped-content verification
factual accuracy
entity accuracy
site reputation abuse context
true Google rendering/indexing behavior
Core Web Vitals field data
