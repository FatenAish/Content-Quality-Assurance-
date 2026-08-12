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

Version 14 Final Context Cleanup
FAQ Hierarchy
Heading section extraction now respects heading levels.
An H2 section includes child H3 and H4 content until the next H2.
An H3 section includes child H4 content until the next H2 or H3.
This fixes FAQ structures such as:
H2 FAQS
H3 Question 1
Answer 1
H3 Question 2
Answer 2
The FAQ parent section is now evaluated using the complete questions and answers rather than appearing empty.
Entity Aware Heading Relevance
A heading that looks like a named project, building or place does not need to repeat the Focus Keyword.
The system evaluates the section below that entity heading.
A named entity heading can be accepted when its section has enough relationship to the page topic.
This addresses cases such as Victory Heights.
Entity Cleaning
Generic property wording is removed from entity candidates.
Example:
studio in Elite Sports Residents
becomes:
Elite Sports Residents
Near Duplicate Entity Detection
Entity spellings are compared with each other.
Suspiciously similar names are reported as a consistency signal.
Example:
Elite Sports Residence
Elite Sports Residents
The system reports the similarity and asks for verification rather than silently treating both spellings as separate correct entities.
Legitimate numbered variants such as Global Golf Residence and Global Golf Residence II are not automatically treated as spelling errors.

Version 15 Final Cleanup
Entity Prefix Normalisation
Leading wrapper words are removed before entity comparison.
Examples:
in Global Golf Residence
becomes:
Global Golf Residence
near Victory Heights
becomes:
Victory Heights
studio in Elite Sports Residents
becomes:
Elite Sports Residents
Common English and Arabic location prepositions are normalised.
Exact Entity De Duplication
Entities that become identical after normalisation are merged before near duplicate analysis.
This prevents false findings such as:
Global Golf Residence
versus
in Global Golf Residence
True Near Duplicate Detection
Real spelling differences remain visible.
Example:
Elite Sports Residence
versus
Elite Sports Residents
This remains a REVIEW signal because it may represent a typo or a legitimate naming variation.
Legitimate numbered variants such as Residence and Residence II are excluded from typo warnings.
Sitemap Stability
Editorial sitemap families are now prioritised ahead of generic page, category, tag, author and media sitemaps.
For MyBayut article URLs, MyBayut post sitemaps receive additional priority.
The maximum inspected sitemap file budget increased modestly from 28 to 36 while the existing wall clock time budget remains in place.
This reduces cases where the same article alternates between PASS and REVIEW only because the correct post sitemap was reached too late.

Version 16 Runtime Verification
Version 16 makes it impossible to confuse an old running app with the latest code.
The current engine version appears:
in the browser page title
inside the dashboard hero
inside the left sidebar
inside the progress status
inside every downloaded audit JSON as app_version
inside every downloaded audit JSON as engine_build
The exported file name is now:
url_audit_v16.json
If a downloaded audit does not contain:
"app_version": "V16"
then it was not generated by Version 16.
Clear Audit Cache
The sidebar includes a Clear audit cache button.
It clears:
robots sitemap cache
sitemap document cache
sitemap lookup cache
rendered hidden content cache
HTTP link and resource probe cache
Windows Launcher
RUN_V16.bat is included.
Double click it to start Streamlit from the correct Version 16 directory instead of accidentally launching an older app.py elsewhere.
RUN_V16.ps1 is also included for PowerShell.

Version 17 FINAL Comprehensive Audit
This release is a full review of all 56 fixed checks.
Major final changes:
Robots now checks robots.txt and page level robots directives.
Internal Links now requests all unique internal HTTP links rather than counting them only.
Canonical now compares the complete preferred destination and checks the canonical target response.
Meta Description no longer requires exact Focus Keyword wording or a fixed character count.
Heading Structure now uses the editorial article hierarchy rather than unrelated navigation headings.
Images now separates meaningful article images from decorative images and checks meaningful alt treatment.
Structured Data now requires an identifiable editorial Article, BlogPosting or NewsArticle object where expected and compares schema identity signals with the visible page.
HTTPS now checks discovered render resources for mixed HTTP content.
Outdated Information now considers the age of the editorial modification or publication date when the article contains current prices, rents, ROI, fees, law, route or project status information.
FAQ Quality now checks actual question and answer pairs, answer length, duplication and topic relevance.
Unsupported Superlatives now evaluates the claim where the wording appears and recognises nearby visible attribution or source links.
Source Quality now scores concrete claims by nearby attribution and local source links rather than counting all external links.
Data Accuracy now looks for substantially repeated statements with conflicting numeric values.
Spam redirect checks now compare redirect chains in addition to final URLs.
Link Spam now focuses on editorial non social links and repeated keyword rich anchor patterns.
User Generated Spam now evaluates repeated domain and anchor patterns instead of link count alone.
The fixed PASS, REVIEW and FAIL framework remains unchanged.
Checks that fundamentally require outside evidence remain REVIEW when the single URL cannot prove the answer. This includes external copying, factual truth, site reputation abuse context and external entity truth.

Version 17.1 FINAL Runtime Fix
Fixed a Python name shadowing error in factual_claim_examples.
The local boolean variable previously named has_attribution shadowed the global has_attribution() function. When the audit later called has_attribution(nearby_context), Python attempted to call a boolean value and raised:
TypeError: 'bool' object is not callable
The local boolean is now named:
has_claim_attribution_signal
The global has_attribution() function remains callable for claim level source and attribution checks.
The exported audit filename is now:
url_audit_v17_1_final.json

Version 17.2 FINAL Runtime Fix
Fixed the runtime error:
NameError: name 'SOCIAL_DOMAINS' is not defined
SOCIAL_DOMAINS is explicitly defined before is_social_domain() and includes the social platforms handled by the automated-link validator.
The domain matcher now normalizes:
www prefixes
ports
subdomains
A Python symbol-table validation is also run before packaging to catch unresolved global names used by functions.
Export filename:
url_audit_v17_2_final.json

Version 17.3 ACTIONABLE
Audit results now include an Action Needed column.
PASS:
No action required.
REVIEW and FAIL:
The system tells the user what needs to be changed or verified.
Factual Accuracy:
Lists unsupported sampled statements and recommends the type of source needed.
Source Quality:
Lists the actual unsupported statements instead of showing only a claim count.
Unsupported Superlatives:
Lists each unsupported hard ranking claim and tells the user to support or rewrite it.
Data Accuracy:
Shows the conflicting statement and the previous and current numeric values.
Entity Accuracy:
Shows the exact entity names or near duplicate pair that must be verified and standardized.
Outdated Information:
Tells the user which type of current data must be refreshed and warns not to update dateModified without a real editorial content update.
dateModified:
Provides a backend action focused on the source of the HTTP Last Modified header.
Scraped Content:
Explains the external comparison needed and what to do only if copying is confirmed.
Site Reputation Abuse:
Explains the internal editorial ownership evidence required to clear the review.
Export filename:
url_audit_v17_3_actionable.json

Version 17.4 INTERNAL CONTENT
Removed completely:
Scraped Content
Site Reputation Abuse
The audit now contains:
14 Spam checks
20 SEO checks
20 Content checks
54 total checks
Internal Links
Internal Links now checks only hyperlinks inside the isolated article content.
Excluded:
header links
footer links
sidebar links
navigation links
social links
external links
The Internal Links check evaluates:
whether the URL is on the same domain
whether the destination responds successfully
whether the anchor text exists
whether the anchor is generic or spammy
whether the anchor is heavily over optimised
whether the anchor text reasonably describes the linked destination slug
For REVIEW results, Action Needed lists the exact anchor text, URL and required correction.
Export filename:
url_audit_v17_4_internal_content.json

Version 17.5 SIMPLE RESULTS
Internal Links and Images now use issue-only output.
Internal Links PASS:
No internal linking issues found inside the article content.
Internal Links REVIEW:
Only the exact URL and reason are shown.
Examples:
https://example.com/page | Issue: Broken internal link HTTP 404
https://external.com/page | Issue: External link inside article content
https://example.com/page | Issue: Empty anchor text
HTTP 401, 403 and 429 are not treated as broken links by themselves.
Images PASS:
No image issues found inside the article content.
Images REVIEW:
Only the exact image URL and issue are shown.
Examples:
https://example.com/image.png | Issue: Empty alt text
https://example.com/image.png | Issue: Missing alt attribute
Export filename:
url_audit_v17_5_simple_results.json

Version 17.6 IGNORE TRUBROKER
Images remains issue-only.
PASS:
No image issues found inside the article content.
REVIEW:
Only the exact image URL and issue are shown.
The image audit now completely excludes known Bayut TruBroker assets.
Any image URL or file name containing:
TruBroker
Tru-Broker
Tru_Broker
is skipped.
This covers English and Arabic TruBroker variants as well as mobile and desktop assets.
Example excluded asset:
EN_Trubroker-GIF-Mobile@2x.png
Export filename:
url_audit_v17_6_ignore_trubroker.json

Version 17.7 BODY LINKS ONLY
Internal Links now means editorial body links only.
Included:
text hyperlinks inside article paragraphs
text hyperlinks inside article list items
text hyperlinks inside article table cells
Excluded:
Find An Agent CTA
property listing cards
property detail cards
broker banners
image links
social share buttons
Google source links
header
footer
sidebar
navigation
related content
widgets
buttons and forms
self links to the current article
The output shows only the real body link with an issue and the reason.
PASS:
No internal linking issues found inside the article body.
Export filename:
url_audit_v17_7_body_links_only.json

Version 17.8 STRICT HIDDEN LINKS
Hidden Links is now strict.
PASS: No hidden links found.
FAIL: Any hidden hyperlink detected.
Result shows only:
URL | Anchor | HTML Location | Issue
Example:
https://www.bayut.com/example/#respond | Anchor: "Cancel Reply" | Location: a, id cancel-comment-reply-link | Issue: Hidden link (display none)
Export:
url_audit_v17_8_strict_hidden_links.json

Version 17.9 HTML HIDDEN LINKS
Hidden Links now uses fetched HTML source only.
The rule does not use Playwright or rendered browser state.
A hidden link exists only when:
an actual <a href> is present in the fetched HTML
and the anchor itself or an HTML ancestor contains a supported hiding signal
Supported source-level signals include:
hidden attribute
inert attribute
display none
visibility hidden
visibility collapse
opacity zero
font size zero
zero height or width
offscreen positioning
large negative text indent
clipping
content visibility hidden
scale zero
Result format:
URL | Anchor | Location | Issue | HTML
PASS:
No hidden links found in the fetched HTML.
Export:
url_audit_v17_9_html_hidden_links.json

V18 EMPTY ANCHOR HIDDEN LINKS
Hidden Links now detects two HTML-source cases.
Case 1:
HTML/CSS hidden link.
Case 2:
Empty anchor with a real HTTP(S) href and no visible content.
Example:
<a href="https://example.com/source"></a>
This is now FAIL.
Visible content includes:
anchor text
image
SVG
picture
video
audio
canvas
object
embed
iframe
Result is intentionally simple:
URL | Issue | Near
Example:
https://example.com/source | Issue: Empty anchor | Near: Azizi Abraham ...
This makes it possible to locate exactly where the bad link appears in the article.
Export:
url_audit_v18_empty_anchor_hidden_links.json

V18.1 HIDDEN LINKS FIX
Fixed runtime error:
NameError: hidden_ancestor_info is not defined
The missing helper is now included.
Hidden Links still checks fetched HTML source only.
The helper walks:
the anchor itself
its HTML parents
and returns the first source-level hiding reason found.
Supported source signals include:
hidden
inert
display none
visibility hidden
opacity zero
font size zero
zero dimensions
offscreen positioning
clipping
content visibility hidden
scale zero
Empty HTTP(S) anchors with no visible content are still detected separately.
Export:
url_audit_v18_1_hidden_links_fix.json

V18.2 SIMPLE HIDDEN URLS
Hidden Links output is now simplified.
FAIL result example:
https://example.com/source-one | Empty anchor
https://example.com/source-two | Hidden HTML link
https://example.com/source-three | Empty anchor, Hidden HTML link
Duplicate URLs are grouped into one numbered item.
The Near context and raw HTML are no longer shown in the main Result.
Why is now only:
Checked the fetched HTML for empty <a href> links and links hidden by HTML/CSS.
Export:
url_audit_v18_2_simple_hidden_urls.json
