# Multi-Source Web Scraping & Data Consolidation Pipeline

A Python pipeline that scrapes two public practice websites, cleans and
validates the data, removes duplicates, and writes one consolidated UTF-8
dataset with a measurable summary report and an execution log.

```
scrape (follow next links) → clean → validate → deduplicate → consolidate → save → summarise → log
```

## 1. Objective

Build a reproducible, robust scraping pipeline that:

- collects records from **more than one source** with **dynamic pagination**
- maps them onto a **common data model**
- **cleans** and **validates** them, and keeps rejected records with reasons
  instead of dropping them silently
- detects **duplicates** with normalisation rather than exact string matching
- writes a final CSV, a JSON summary with metrics that add up, and a log file
- survives failures of single records, single pages, or a whole source
- is covered by automated tests and can be explained in an interview

## 2. Sources

| Source | Start URL | What is collected |
|--------|-----------|-------------------|
| Books to Scrape | https://books.toscrape.com/ | title, price, star rating, detail URL; category and description from each book's detail page |
| Quotes to Scrape | https://quotes.toscrape.com/ | quote text, author, author "about" URL, tags |

Both sites are sandboxes built for scraping practice. Neither has a
`robots.txt` (both return 404), and neither uses logins or CAPTCHAs. The
scraper does not bypass any protection; it identifies itself with a
descriptive User-Agent and waits ≥ 0.5 s between requests.

## 3. Project structure

```
scraping_assignment/
├── main.py                  # CLI entry point (argparse) → builds Settings, runs pipeline
├── pipeline.py              # orchestration + summary metrics
├── config.py                # Settings dataclass, URLs, retryable status codes
├── schema.py                # common data model (FIELDNAMES), source names
├── logging_setup.py         # file + console logging
├── scrapers/
│   ├── http_client.py       # requests.Session, retries/backoff, timeout, rate limit
│   ├── base_scraper.py      # pagination loop, per-item/page isolation, stats
│   ├── books_scraper.py     # Books to Scrape parser (+ detail pages)
│   └── quotes_scraper.py    # Quotes to Scrape parser
├── processing/
│   ├── cleaning.py          # field-level cleaning functions
│   ├── validation.py        # validation rules + rejection reasons
│   ├── deduplication.py     # normalised fingerprints
│   └── output.py            # CSV / JSON writers
├── tests/                   # pytest suite (offline) + HTML fixtures
├── output/                  # final_dataset.csv, summary_report.json, rejected_records.csv, duplicates.csv
├── logs/scraper.log
├── requirements.txt
├── pytest.ini
├── README.md
└── AI_USAGE.md
```

## 4. Requirements

- **Python 3.10 or newer.** Verified on **3.13.15** and on **3.12.10** in a
  fresh virtual environment.
- Internet access to the two sites (only `main.py` needs it; the tests run
  offline).
- No API keys, accounts or paid services.

| Dependency | Why |
|------------|-----|
| `requests` | HTTP session, timeouts, retry adapter (via its bundled `urllib3`) |
| `beautifulsoup4` | HTML parsing with CSS selectors |
| `lxml` | fast, tolerant parser backend for BeautifulSoup |
| `pytest` | test runner |

Everything else (`csv`, `json`, `logging`, `argparse`, `hashlib`,
`unicodedata`, `pathlib`) is from the standard library.

## 5. Installation

```bash
cd scraping_assignment
python -m venv .venv

# Windows (PowerShell)
.venv\Scripts\Activate.ps1
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

## 6. How to run

```bash
python main.py                         # full run: every page of both sites (~10 min, see below)
python main.py --skip-book-details     # fast full run (~35 s): no category/description for books
python main.py --max-pages 2           # quick demo: 2 listing pages per source
python main.py --sources quotes        # one source only
python main.py --help                  # all options
```

| Option | Default | Meaning |
|--------|---------|---------|
| `--sources books quotes` | both | which sources to scrape |
| `--max-pages N` | unlimited | stop each source after N listing pages |
| `--skip-book-details` | off | do not open the 1,000 book detail pages |
| `--delay S` | 0.5 | minimum seconds between requests |
| `--timeout S` | 10 | per-request timeout |
| `--retries N` | 3 | retries for connection errors / timeouts / HTTP 429, 500, 502, 503, 504 |
| `--books-url`, `--quotes-url` | real sites | start URLs (useful for testing failure handling) |
| `--output-dir`, `--log-file` | `output/`, `logs/scraper.log` | where results go |
| `--verbose` | off | include DEBUG messages (e.g. each detail page) |

**Why the full run takes about 10 minutes.** Category and description exist
only on each book's detail page. That means 1,000 detail requests + 50 Books
listing pages + 10 Quotes pages, with ≥ 0.5 s between requests. This is a
deliberate politeness choice, not a slowdown in the code.

Exit code: `0` when at least one source succeeded (status `success` or
`partial`), `1` when every source failed.

## 7. How pagination works

`BaseScraper.scrape()` in `scrapers/base_scraper.py` runs the same loop for
both sites:

1. Fetch the current URL and parse it.
2. Extract every item on the page.
3. Look for `li.next > a`. If it exists, resolve its `href` against the
   **current page URL** with `urljoin` and continue. If it does not, stop
   (`stop_reason = "no_next_link"`).

No page count is hard-coded. `urljoin` matters because the two sites link
differently: Books page 1 links to `catalogue/page-2.html`, later pages link
to `page-3.html` (relative to `/catalogue/`), and Quotes uses absolute paths
such as `/page/2/`. A `visited` set stops infinite loops, and `--max-pages`
can cap the crawl. The summary records `pages_scraped`,
`next_links_followed`, `first_page_url`, `last_page_url` and `stop_reason`
for each source as evidence.

### Selectors (checked against the live HTML)

| Purpose | Books | Quotes |
|---------|-------|--------|
| item | `article.product_pod` | `div.quote` |
| title / text | `h3 > a` **`title` attribute** (link text is truncated, e.g. "A Light in the ...") | `span.text` |
| price | `p.price_color` | — |
| rating | 2nd class of `p.star-rating` (e.g. `Three`) | — |
| author | — | `small.author` |
| author URL | — | `a[href^="/author/"]` |
| tags | — | `a.tag` |
| category | detail page: 3rd link of `ul.breadcrumb` | — |
| description | detail page: `#product_description + p` | — |
| next page | `li.next > a` | `li.next > a` |

**Encoding.** Books to Scrape sends `Content-Type: text/html` with no
charset, so `requests` would decode it as ISO-8859-1 and `£` would become
`Â£`. The scraper passes the raw **bytes** to BeautifulSoup, which reads the
page's `<meta charset=UTF-8>` and decodes correctly.

## 8. Common data model

Defined in `schema.py`. Every output row has these columns, in this order:

| Field | Type | Books | Quotes |
|-------|------|-------|--------|
| `source` | str | `books_toscrape` | `quotes_toscrape` |
| `source_url` | str (absolute URL) | book detail page | listing page the quote appeared on |
| `name_or_title` | str | book title | quote text (decorative “ ” removed) |
| `category` | str / empty | genre from breadcrumb | empty (not provided) |
| `price` | float / empty | price in GBP (£) | empty |
| `rating` | int 1–5 / empty | star rating | empty |
| `author` | str / empty | empty (site lists no author) | author name |
| `author_url` | str / empty | empty | absolute author page URL |
| `tags` | list → `a|b|c` in CSV | empty | lower-cased tags |
| `description` | str / empty | product description (empty if the book has none) | empty |
| `scraped_at` | ISO-8601 UTC | time of extraction | time of extraction |

Rule: **a field that a source does not provide stays empty. It is never
guessed, defaulted or copied from somewhere else.** For example, quote tags
are *not* used as a category, and price is never set to 0 when it is
missing.

`author_url` is the only addition to the suggested field list. It keeps the
"author URL" that the Quotes requirements ask for.

## 9. Cleaning (`processing/cleaning.py`)

| Function | What it does |
|----------|--------------|
| `normalize_whitespace` | Unicode NFC, removes zero-width/BOM chars, collapses spaces/newlines/NBSP, trims; blank → `None` |
| `strip_wrapping_quotes` | removes one pair of surrounding “ ” / " " from quote text; inner quotes kept |
| `clean_price` | `"£51.77"` → `51.77` (2 dp); handles thousands separators and the `Â£` mojibake; blank → `None`; **anything else returned unchanged** |
| `clean_rating` | `"Three"`/`"3"`/`3.0` → `3`; blank → `None`; unknown words / out-of-range numbers returned unchanged (not clamped) |
| `clean_tags` | trim, lower-case, de-duplicate (order kept); accepts a list or `,;|`-separated string; missing → `[]` |
| `clean_url` | trim, resolve relative URLs, lower-case scheme and host, drop `#fragment` |
| `clean_description` | whitespace normalisation + removes the site's trailing `...more` UI marker |
| `clean_record` | applies all of the above and emits exactly the schema fields in order |

Design choice: **cleaning normalises but never invents.** A price like
`"free"` or `"abc5"` is *not* turned into a number. It is passed through so
that validation rejects it as `invalid_price` and the problem stays visible.
Cleaning never drops records, so `cleaned_records == raw_records`.

## 10. Validation (`processing/validation.py`)

`validate_record` returns **all** reasons a record fails. Records with at
least one reason go to `output/rejected_records.csv` (with a
`rejection_reasons` column) and are counted in the summary.

| Reason | Rule |
|--------|------|
| `malformed_record` | scraper could not parse the item, or a schema field is missing |
| `unknown_source` | `source` not in {`books_toscrape`, `quotes_toscrape`} |
| `missing_title` | empty `name_or_title` |
| `invalid_url` | `source_url` not an absolute `http(s)` URL |
| `invalid_author_url` | `author_url` present but not an absolute `http(s)` URL |
| `missing_price` / `invalid_price` | books need a price; any price must be a finite number ≥ 0 |
| `missing_rating` / `invalid_rating` | books need a rating; any rating must be an int 1–5 |
| `missing_author` | quotes need an author |
| `invalid_tags` | tags not a list of strings |
| `invalid_scraped_at` | not an ISO-8601 timestamp |

Because one record can have several reasons, the sum of
`rejection_reasons` counts can exceed `rejected_records`.

## 11. Duplicate detection (`processing/deduplication.py`)

Exact string comparison is not enough: `"A Light in the Attic"`,
`"a  light in the attic"` and `"A Light in the Attic!"` are the same item
but different strings. Curly versus straight quotes and accents cause the
same problem.

1. **Normalise:** Unicode NFKD → drop accent marks → punctuation and symbols
   become spaces → `casefold()` → collapse whitespace.
   `"  Héllo,  WORLD!! "` → `"hello world"`.
2. **Build a key:**
   - books: `source | normalised title`
   - quotes: `source | normalised author | first 80 chars of normalised quote`
3. **Fingerprint:** `sha256(key)`, which is deterministic and fixed-length.
4. Keep the **first** record per fingerprint. Later ones go to
   `output/duplicates.csv` with `fingerprint` and `duplicate_of` (the kept
   record's URL).

Including `source` in the key means a book and a quote are never merged.
The author is part of the quote key, so the same words by different people
stay distinct.

**What the real data shows.** The run found one duplicate: *The
Star-Touched Queen* has two catalogue listings (`..._764` and `..._642`) with
the same title, category (Fantasy) and five-star rating, and a blurb that is
92 % identical. The differences are typography (`...` vs `…`, `--` vs `—`,
`'` vs `’`, letter case) and one extra closing sentence. The listings have
**different UPCs and prices** (£46.02 vs £32.30), so they are best described
as two listings/editions of the same book. Exact string comparison would not
match them on any field except the title. Under the reference's title key
they are duplicates: the first (£46.02) is kept and the second is reported
in `duplicates.csv`. If separate editions should be kept, the key should be
the UPC instead. The same title key would also merge two *unrelated* books
that share a title. That does not occur on this site (checked: 999 distinct
normalised titles = 999 kept books).

Duplicate detection is tested with **deliberately duplicated fixtures** in
`tests/test_deduplication.py` and `tests/test_pipeline.py`. Real scraped
data is never modified to create duplicates.

## 12. Consolidation

Valid, non-duplicate records from both sources are combined into
`output/final_dataset.csv`:

- columns are exactly `schema.FIELDNAMES`, in a fixed order
- UTF-8, standard CSV quoting (descriptions contain commas and quotes)
- rows in crawl order: all books, then all quotes, each in page order
- `source` and `source_url` keep each row traceable to its origin

## 13. Error handling

| Level | Failure | Behaviour |
|-------|---------|-----------|
| request | connection error, timeout, HTTP 429/500/502/503/504 | retried up to `--retries` times with exponential backoff (honours `Retry-After`) |
| request | final failure or other HTTP error (e.g. 404) | `FetchError` raised and logged at ERROR |
| item | missing element (e.g. no price) | field stays empty, WARNING logged, validation later rejects it if required |
| item | unexpected markup raising `AttributeError/KeyError/IndexError/TypeError/ValueError` | placeholder record with `_parse_error` → rejected as `malformed_record`; crawl continues |
| detail page | fetch/parse fails | listing data kept, category/description left empty, WARNING, counted in `detail_pages_failed` |
| listing page | fetch fails after retries | that source stops (the next link cannot be discovered); earlier records kept; status `partial`/`failed` |
| source | unexpected exception | caught at the source boundary in `pipeline.run_scraper`, logged **with traceback**, other sources still run |

Only these narrow boundaries catch exceptions. The single broad `except
Exception` is at the source boundary, where it logs the full traceback and
records the error in the summary, so a bug is reported rather than hidden.

*Verified live:* running with `--books-url http://127.0.0.1:9/` makes Books
fail with a connection error while Quotes completes normally (run status
`partial`, exit code 0).

## 14. Logging

`logs/scraper.log` (overwritten each run so it matches the latest summary),
also echoed to the console. Format:
`timestamp | LEVEL | logger | message`.

- **INFO:** pipeline start, source start/end, every page scraped with its
  record count, stop reason, cleaning / validation / dedup stage counts, each
  duplicate removed, output files written, final totals
- **WARNING:** missing expected element, malformed item, failed detail page,
  each rejected record with its reasons, pagination loop
- **ERROR:** failed request (after retries), page that stops a source, source
  failure (with traceback)

No secrets exist, so none can be logged.

## 15. Output files

| File | Content |
|------|---------|
| `output/final_dataset.csv` | consolidated, valid, de-duplicated records |
| `output/summary_report.json` | metrics (below) |
| `output/rejected_records.csv` | every rejected record + `rejection_reasons` (+ `_parse_error`) |
| `output/duplicates.csv` | every removed duplicate + `fingerprint` + `duplicate_of` |
| `logs/scraper.log` | execution log |

## 16. Summary metrics (`output/summary_report.json`)

Every number is computed from the record lists of the actual run:

- `run`: `started_at`, `finished_at` (UTC), `duration_seconds`, `status`
  (`success`/`partial`/`failed`), effective `settings`
- `totals`: `raw_records`, `cleaned_records`, `valid_records`,
  `rejected_records`, `duplicate_records`, `final_records`
- `sources.<name>`: status, error, `pages_scraped`, `pages_failed`,
  `next_links_followed`, `first_page_url`, `last_page_url`, `stop_reason`,
  `items_found`, `malformed_items`, detail page counts (books), and
  raw/rejected/duplicate/final counts
- `rejection_reasons`: count per reason
- `duplicates`: total, per source, and the strategy used
- `reconciliation`: checks `raw = rejected + duplicates + final`, overall
  and per source
- `data_quality.empty_fields_in_final_dataset`: per source, how many final
  rows have each field empty (shows which gaps are expected, e.g. quotes have
  no price)
- `http`: requests made and failed

## 17. Testing

```bash
pytest            # or: python -m pytest -v
```

All tests run **offline** and do not touch the live sites:

| File | Covers |
|------|--------|
| `test_cleaning.py` | whitespace, Unicode, quote marks, price conversion, rating normalisation, tags, URLs, missing values, invalid values left for validation |
| `test_validation.py` | valid records, missing title/fields, invalid price/rating/URL, unknown source, per-source required fields, multiple reasons |
| `test_deduplication.py` | identical, case, whitespace, punctuation differences, distinct records, cross-source, order, quote prefix |
| `test_scrapers.py` | parsing saved HTML, following next links to the end, `urljoin` behaviour, `max_pages`, missing elements, malformed items, detail pages and their failures, page failure, loop detection |
| `test_http_client.py` | real `HttpClient` against a local server: retry on 429/500/502/503/504, give up after N retries, no retry on 404, error mapping, rate limiting, User-Agent |
| `test_pipeline.py` | end-to-end with fake sources: counts add up, CSV schema and order, rejected/duplicate reports, **one source failing while the other completes** |

## 18. Assumptions

- **Source documents.** The original assignment and reference PDFs were not
  in the working directory when this was built. The requirements were taken
  from the detailed task brief that restates them (schema fields, selectors,
  fingerprint strategy, rejection reasons, outputs).
- Quotes have no individual page, so `source_url` for a quote is the listing
  page it appeared on.
- Books prices are in GBP, as shown on the site. No currency conversion is
  done.
- Books require price and rating; quotes require author. Fields a source
  does not provide are not required for that source.
- Book category and description are worth one extra request per book, so
  detail pages are fetched by default (`--skip-book-details` turns this off).
- Duplicates keep the first occurrence in crawl order.

## 19. Limitations

- Sequential and polite by design, so a full run takes about 10 minutes.
  Parallel fetching would be faster but harsher on the server.
- If a *listing* page fails after all retries, the rest of that source cannot
  be discovered, because pagination depends on the next link of the failed
  page.
- The Books title-only duplicate key would merge two *different* books that
  share a title. That does not happen on this site, but a UPC from the detail
  page would be a stronger key elsewhere.
- The quote key compares only the first 80 normalised characters. Two
  different quotes by the same author that start with the same 80 characters
  would be merged; none exist on the site.
- No checkpoint/resume or incremental scraping. Each run re-scrapes
  everything.
- Selectors are tied to the current markup of the two sites.

## 20. AI usage

AI (Claude Code) was used to build this project. See [AI_USAGE.md](AI_USAGE.md)
for which parts were AI-generated, how they were verified, and which AI
suggestions were wrong and corrected.

## 21. Reproducibility

```bash
python -m venv .venv && .venv\Scripts\activate      # or: source .venv/bin/activate
pip install -r requirements.txt                      # pinned versions
pytest                                               # 126 tests, offline
python main.py                                       # regenerates output/ and logs/
```

Exact counts and timestamps depend on the live sites at run time. The two
sites are static sandboxes, so the record counts should match the results
below.

## 22. Results of the verified run

Full run `python main.py` on 2026-10-06 (all values copied from
`output/summary_report.json` and `logs/scraper.log`):

| Metric | Books | Quotes | Total |
|--------|------:|-------:|------:|
| listing pages scraped (via next links) | 50 (49 next links, stop: `no_next_link`) | 10 (9 next links, stop: `no_next_link`) | 60 |
| detail pages fetched / failed | 1000 / 0 | — | — |
| raw records | 1000 | 100 | **1100** |
| cleaned records | 1000 | 100 | 1100 |
| rejected records | 0 | 0 | **0** |
| duplicates removed | 1 | 0 | **1** |
| final records | 999 | 100 | **1099** |

- Reconciliation: 1100 = 0 + 1 + 1099 ✔ (also per source)
- HTTP: 1060 requests, 0 failed; duration 549.4 s
- Status: `success`, exit code 0; `pytest`: **126 passed**
- Fields that are empty in the final data and were confirmed empty on the
  live site: 2 books without a description (`..._840`, `..._5`), 3 quotes
  without tags (pages 3, 5 and 8). Quotes have no price/rating/category/
  description, and books have no author/tags, as the data model specifies.
- Spot check: randomly sampled books re-fetched from the live site matched
  title, price, rating and category exactly.

No rejections is the expected result for these clean sandbox sites. The
rejection paths are tested in `tests/test_validation.py`, `test_scrapers.py`
and `test_pipeline.py`.
