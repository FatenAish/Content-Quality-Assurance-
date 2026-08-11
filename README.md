Bayut URL Quality Auditor — V2
This version keeps the full URL audit logic and updates the interface to closely match the supplied Bayut-style dashboard reference.
Audit sections
Spam Check — 16 fixed rules
SEO Check — 20 fixed rules
Content Check — 20 fixed rules
Design changes in V2
Bayut-style left navigation
Bayut green / mint palette
Large branded hero card
URL audit input panel with green CTA
Three rule summary cards
Four-step "How it works" section
Refined result cards, tabs, data table, and sidebar rule library
Desktop/mobile responsive CSS
Run
```bash
pip install -r requirements.txt
streamlit run app.py
```
Notes
The Googlebot comparison uses a Googlebot User-Agent request, not Google's real crawler infrastructure. Checks that cannot be conclusively proven from one URL remain REVIEW rather than being treated as automatic PASS/FAIL.

Keyword targeting inputs
Focus Keyword: used by the SEO and Content checks to review Title, Meta Description, H1, search intent, headings, introduction and keyword usage.
Secondary Keywords: comma/semicolon/newline-separated phrases used for coverage reporting and keyword-usage context.
The app keeps the same 56 core rules; keyword inputs enrich existing rules rather than adding duplicate rules.

Version 4
The result table now includes a permanent column called `What the System Uses`.
Every Spam, SEO and Content rule shows the data, parser, comparison or detection method used to reach the result.
The visible interface wording avoids dash characters where possible.

Version 5
The public audit results no longer display PASS, REVIEW or FAIL.
Each result table now contains only:
Check
Result
Why
The Rule Library remains available and continues to show the fixed rule and what the system uses for that rule.
Internal rule outcomes may still be calculated only to support rule engine logic, but they are not shown in the interface and are not included in exported JSON.

Version 6
PASS, REVIEW and FAIL are displayed again.
Each audit result contains:
Check
Status
Result
Why
The Rule Library remains unchanged and still shows the fixed rule and What the System Uses.
The JSON export also includes Status for every rule.

Version 7
Hidden Links now reports the exact evidence for every detected hidden link.
The Result includes:
Actual URL
Anchor Text
Hidden Element
Hidden Because
The scanner checks the anchor itself and its parent elements for the same hidden rules already used by the system.
Rule Library remains unchanged in structure.

Version 8
Hidden content logic now checks the reason for hiding before deciding PASS, REVIEW or FAIL.
The system recognises common legitimate hiding patterns including:
WordPress comment reply controls
Accordions and collapsible panels
Tabs
Dialogs, modals, popups, drawers and off canvas panels
Responsive desktop and mobile navigation
Dropdowns and submenus
Sliders and carousels
Tooltips and popovers
Screen reader and accessibility only content
Cookie and consent interfaces
Search and filter panels
Form validation messages
Loading and deferred interface states
Native closed details elements
Hidden until found
Inert inactive interface regions
The system also detects suspicious hiding methods including:
Opacity zero
Font size zero
Content moved far outside the visible screen
Large negative text indent
Scale zero
Unexplained invisible links
When Playwright and Chromium are available, the scanner uses rendered computed styles and compares desktop and mobile visibility.
Install dependencies:
```bash
pip install -r requirements.txt
playwright install chromium
streamlit run app.py
```
If Chromium is not installed, the app continues using static HTML fallback checks.

Version 9
Title Tag logic was revised.
Google does not have a fixed character limit in this system.
The new logic uses:
Title existence
Character count as an advisory signal
Title to article topic overlap
Focus Keyword exact match or semantic term overlap
Repeated title terms
Internal length treatment:
30 to 70 characters: concise internal range
71 to 80 characters: length alone does not trigger REVIEW
More than 80 characters: REVIEW for possible verbosity
Less than 30 characters: REVIEW only when the title is also too vague or weakly related to the page
The Rule Library has been updated with the same fixed logic.

Version 10
Four major false positive sources were revised.
Keyword Stuffing and Keyword Use
The system no longer gives REVIEW because a primary location or entity phrase is repeated frequently by itself.
A repeated phrase is treated as a primary topic phrase when it appears across at least two strong page identity signals such as:
Title
H1
Focus Keyword
URL
Exact Focus Keyword and Secondary Keyword repetition is also measured per 1,000 words.
Natural topic repetition can PASS.
Unusually repetitive target phrases can REVIEW.
Clearly excessive manipulative repetition can FAIL.
H1
Exact Focus Keyword matching is no longer required.
The system uses semantic concept normalisation and compares the H1 with:
Focus Keyword meaning
Article topic
One clear semantically relevant H1 can PASS even if synonyms are used.
For example:
Focus Keyword: Rent apartments and villas in Dubai Sports City
H1: Where can you rent properties in Dubai Sports City
Both map to the same rent, property and location concepts.
Heading Relevance
Headings are no longer judged only by direct word overlap.
The system now checks each H2 to H4 together with the section text that follows it.
A building or project name can PASS when its section clearly establishes its relationship to the main topic.
Sitemap
The system now:
Reads Sitemap declarations from robots.txt
Checks common sitemap endpoints
Parses XML sitemap indexes
Follows child sitemaps recursively
Searches for the preferred canonical URL
Returns the sitemap where the URL was found
Returns sitemap lastmod when available
The recursive crawl is bounded to protect audit performance.

Version 11 Performance Upgrade
No audit rules were removed.
Performance changes:
Desktop, Mobile and Googlebot requests run in parallel.
Spam, Content and Sitemap stages run in parallel.
Sitemap files are fetched in concurrent batches.
robots.txt sitemap declarations are cached.
Parsed sitemap documents are cached across repeated audits in the same app process.
Sitemap traversal has a 12 second wall clock budget.
Sitemap traversal checks at most 28 files per audit.
Likely child sitemaps are prioritised first.
If the sitemap time or file budget is reached, the system returns REVIEW with an explicit incomplete inspection reason instead of freezing the application.
Playwright rendered hidden content results are cached by URL.
Playwright navigation timeout was reduced and the browser settle delay was shortened.
A visible audit progress panel is displayed above the Rule Library.
The result screen displays total audit time.
Default performance controls can be adjusted at the top of app.py:
PAGE_FETCH_TIMEOUT
SITEMAP_REQUEST_TIMEOUT
SITEMAP_MAX_FILES
SITEMAP_MAX_DEPTH
SITEMAP_WORKERS
SITEMAP_TIME_BUDGET
PLAYWRIGHT_NAV_TIMEOUT
PLAYWRIGHT_SETTLE_MS

Cache freshness
Performance caches are time limited.
robots.txt and sitemap documents refresh every 10 minutes.
Completed sitemap lookup results refresh every 10 minutes.
Rendered browser visibility results refresh every 5 minutes.
This keeps repeated audits fast while preventing permanent stale results.

Version 12 Accuracy Upgrade
Article Content Isolation
Content QA now selects and cleans the editorial article body before analysis.
It prefers article specific containers such as:
itemprop articleBody
entry content
post content
article content
post body
article
It removes:
Comments
Reply forms
Related posts
Popular posts
Recommended content
Sidebars
Navigation
Footer
Newsletter and subscription blocks
Social share blocks
Author boxes
Breadcrumbs
Post navigation
This isolated article fragment is used for:
Content Relevance
Thin Content
Original Value
Factual Accuracy
Outdated Information
Keyword Use
Repetition
Generic or Filler Content
Title vs Content
H1 vs Content
Heading Relevance
Introduction Quality
FAQ Quality
Unsupported Superlatives
Source Quality
Data Accuracy
Entity Accuracy
Grammar and Readability
Broken Content
External Links
Every discovered unique external HTTP link is requested.
The result shows:
HTTP status
Final destination when redirected
Broken URLs
Restricted URLs
Server errors
Unreachable URLs
A link is no longer marked PASS simply because it exists.
Broken Resources
Discovered image, stylesheet and JavaScript resources are requested directly.
The result reports any resource that is broken, restricted, unreachable or returns a server error.
Structured Data
JSON LD parsing is now combined with visible page comparison.
Schema headline is compared with the visible Title and H1.
Date Consistency
datePublished can be compared with visible or metadata publication signals.
dateModified can be compared with:
Visible modified metadata
Sitemap lastmod
HTTP Last Modified
A material HTTP Last Modified mismatch is reported as a technical freshness inconsistency and not a spam violation.
Outdated Information
Old years are evaluated sentence by sentence inside the isolated article body.
Historical and contextual dates do not automatically trigger REVIEW.
Older years trigger REVIEW when they occur inside time sensitive claims such as current rent, prices, ROI, fees, laws, transport routes or project status.
The Result shows the year and sentence that caused the finding.
Factual Accuracy
The scanner now extracts concrete factual and numeric claim examples from the isolated article body.
It reports visible source links found in the same content blocks.
External or first party verification is still required to confirm truth.
Entity Accuracy
The scanner extracts entity candidates from article headings and editorial text and shows the exact names that require verification instead of returning a generic REVIEW message.
Performance
External link validation and resource validation run in parallel with Spam, Content and Sitemap checks.
Network probe results are cached for 10 minutes.

Version 13 False Positive Cleanup
H1
H1 is now collected from the full page and article header, not only the isolated article body.
This fixes pages where the H1 is outside entry content.
External Social Links
Known social platforms can return login pages, HTTP 400, 401, 403 or 429 to automated requests.
These are now treated as expected platform or anti bot behaviour when the URL belongs to a recognised social platform.
They do not automatically make External Links REVIEW.
Confirmed broken destinations such as 404 and 410 still trigger REVIEW.
Broken Resources
Resource extraction now includes only render relevant resources:
script src
img src
source src
stylesheet links
preload links for style, script, font and image
The scanner excludes:
WordPress wp json discovery
oEmbed links
xmlrpc
canonical links
alternate links
shortlinks and other metadata discovery links
Factual Accuracy
Claim extraction is now more conservative.
It prioritises claims containing:
AED values
percentages
years and dates
distances and travel times
average prices or rents
ROI and yields
completion or launch facts
developer attribution
ranking and data claims
specific location statements
Generic promotional statements such as comfortable lifestyle or great option are not treated as factual claims unless they also contain concrete verifiable information.
FAQ Relevance
FAQ is now treated as a structural section.
The system checks the questions and answers beneath FAQ rather than judging the word FAQ against the Focus Keyword.
Entity Accuracy
Entity extraction now prioritises:
proper noun headings
article anchor text
conservative proper noun phrases
It filters:
CTA text
FAQ labels
Find an Agent
Rent Apartments or Rent Villas keyword phrases
question fragments
sentence fragments
generic SEO wording
