# AbhiHub — High-Efficiency Search & Discovery Engine Architecture (v2)

**Document ID:** `SEARCH_ENHANCEMENT_PLAN`  
**Target:** Sub-50ms Subject & Academic Resource Discovery Engine  
**Status:** Approved Architecture with In-Memory Resolution & Tiered Lexicographical Matching

---

## 1. Executive Summary & Core Architectural Shift

### The Latency Problem
A purely database-side search over Supabase HTTP incurs a 30–100ms network round-trip overhead per call, even before SQL execution. Furthermore, complex SQL joins and multi-step `ilike` queries compound this latency to 300–800ms.

### The Solution: Hybrid In-Memory Understanding + Single DB Document Fetch
1. **In-Memory Query Understanding (<1ms):**
   Academic taxonomies (Colleges, Departments, Subjects, Subject Codes, and Aliases) are compact (<5,000 rows). We load them into an in-process Python memory index at server boot (refreshed every 5–10 minutes via background thread).
2. **Deterministic Token Resolution:**
   Tokens like `"iter"`, `"sem 4"`, `"cse2001"`, and `"os"` are resolved in Python memory without any database call.
3. **Single Indexed Document Query:**
   The database is only called once with resolved IDs: `WHERE subject_id = ANY(...)` or a single indexed lookup.
4. **Separate Sub-10ms Autocomplete (`/api/v2/suggest`):**
   Autocomplete serves instant keystroke suggestions directly from memory, while `/api/v2/search` executes full document retrieval on Enter or pause.

---

## 2. In-Memory Taxonomy & Entity Resolution Engine

```
[ User Input: "iter sem 4 os 2023 pyq" ]
                 │
                 ▼
 ┌─────────────────────────────────────────────────────────┐
 │               In-Process Python Resolver                │
 │ 1. College Alias Match:   "iter"   -> College ID (ITER) │
 │ 2. Semester Parser:       "sem 4"  -> Semester: 4       │
 │ 3. Resource Type/Exam:    "pyq"    -> Category: Papers  │
 │ 4. Year Extractor:        "2023"   -> Year: 2023        │
 │ 5. Acronym / Code Lookup: "os"     -> Subject: Operating│
 │                                       Systems (CSE2001) │
 └─────────────────────────────────────────────────────────┘
                 │
                 ▼ (Resolved Criteria: Subject IDs, College ID, Sem 4, etc.)
 ┌─────────────────────────────────────────────────────────┐
 │              Single Database Query (Indexed)            │
 │ SELECT * FROM search_documents                          │
 │ WHERE subject_id = ANY('{uuid1, uuid2}')                │
 │   AND college_id = 'iter-uuid'                          │
 │   AND status = 'approved'                               │
 └─────────────────────────────────────────────────────────┘
```

### 2.1 Resolution Vectors & Rules
- **College Groups & Aliases:**
  `soa` expands to SOA University colleges (including ITER). `iter` resolves directly to ITER. `kiit`, `vssut`, `outr`, `cet` resolve instantly.
- **Normalized Subject Codes (`subject_code_norm`):**
  Strip hyphens, spaces, and punctuation: `CSE-2001`, `cse 2001`, `CSE2001` all normalize to `cse2001`. Indexed via B-Tree for exact and prefix matches (`cse20*`).
- **Acronym & Shortform Dictionary:**
  Pre-loaded hash maps:
  - `os` ↔ Operating Systems (`CSE2001`)
  - `dbms` ↔ Database Management Systems (`CSE2002`)
  - `daa` / `algo` ↔ Design and Analysis of Algorithms (`CSE2003`)
  - `toc` / `flat` ↔ Theory of Computation / Formal Languages & Automata
  - `coa` / `cao` ↔ Computer Organization & Architecture
  - `cn` / `nw` ↔ Computer Networks
  - `wt` / `webtech` ↔ Web Technologies
  - `dld` / `de` ↔ Digital Logic Design
  - `m1` / `m2` / `m3` ↔ Engineering Mathematics I / II / III
- **Greedy Multi-Word N-Gram Matching:**
  `data structures and algorithms` matches as a single atomic unit before splitting into single words.
- **Stopword Filtration:**
  Removes generic filler words (`of`, `the`, `for`, `in`, `paper`, `notes` when used as filters).

---

## 3. Tiered Lexicographical Ranking (Not Arbitrary Summed Points)

To eliminate false-positive anomalies where a popular but irrelevant document outranks an exact match, results are sorted **lexicographically by Tier**, with popularity used only as a secondary tie-breaker.

| Tier | Priority Match Type | Example |
| :---: | :--- | :--- |
| **Tier 1** | **Exact Normalized Code** | Query `cse2001` matches document with code `CSE2001` |
| **Tier 2** | **Exact Alias or Acronym** | Query `os` matches subject `Operating Systems` |
| **Tier 3** | **Exact / Prefix Subject Name** | Query `Operating System` matches `Operating Systems` |
| **Tier 4** | **Full-Text Word Match (`tsvector`)** | Prefix match `operat:*` inside document title / description |
| **Tier 5** | **Trigram Fuzzy Match (`<%`)** | Handles typos (e.g. `algorithem` -> `algorithms`) for tokens > 3 chars |
| **Tier 6** | **Graceful Relaxation Fallback** | Related subjects or matching papers across other semesters |

### Popularity Tie-Breaker (Log-Scaled & Capped)
Within any tier, documents are ranked by:
$$\text{Score} = \text{Tier Score} + \min\left(10, \, \ln(1 + \text{views}) + 2 \cdot \ln(1 + \text{likes})\right)$$
*Guarantees a popular irrelevant paper can never leap over a relevant paper in a higher tier.*

---

## 4. Graceful Filter Relaxation (Zero Dead Ends)

If a strict query yields 0 results:
1. **Step 1 (Relax Semester):** Remove semester filter while keeping Subject & College.
   *User prompt:* *"No papers found for Sem 4. Showing Operating Systems papers from other semesters."*
2. **Step 2 (Relax College):** Remove College filter while keeping Subject.
   *User prompt:* *"No papers found for ITER. Showing Operating Systems papers from other universities."*
3. **Step 3 (Zero-Result Logging):**
   Log unmatched queries to `abhihub.search_analytics` with `results_count = 0` to continuously expand the alias dictionary.

---

## 5. Modernized Filtering Section (UI & UX)

### 5.1 Interactive Matrix
```
┌────────────────────────────────────────────────────────────────────────┐
│  🔍 [ ITER × ] [ Sem 4 × ] os cse2001...                         [ ✕ ] │
├────────────────────────────────────────────────────────────────────────┤
│  Filters:                                                              │
│  [ College: ITER ▾ ]  [ Branch: CSE ▾ ]  [ Semester: Sem 4 ▾ ]         │
│  [ Type: All ▾ ]      [ Year: All ▾ ]    [ Sort: Relevance ▾ ]         │
├────────────────────────────────────────────────────────────────────────┤
│  Active Tags: [ ✕ ITER ]  [ ✕ CSE ]  [ ✕ Sem 4 ]          (Clear all)  │
└────────────────────────────────────────────────────────────────────────┘
```

### 5.2 Frontend UX Enhancements
- **Interactive Removable Search Pills:** Parsed filters (`ITER`, `Sem 4`) display as inline badges in the search bar.
- **Backend `match_reason` Badges:** The API sends the match reason (e.g., `Matched Code: CSE2001`, `Matched Alias: OS → Operating Systems`), so the UI renders clear verification badges without client calculation.
- **Zero Layout Shifts:** Skeleton loader rows while results fetch; previous results remain visible during background refinement.
- **Client Debounce & Request Cancellation:** Debounced at 150ms with `AbortController` canceling in-flight stale requests.

---

## 6. Endpoints Architecture

1. **`GET /api/v2/suggest?q=...`**
   - Served 100% from in-memory cache (<5ms response).
   - Returns instant autocomplete suggestions: Subject names, Aliases, Codes, Colleges.
2. **`GET /api/v2/search?q=...&college=...&branch=...&sem=...`**
   - Resolves intent in-memory.
   - Executes single indexed query to PostgreSQL.
   - Returns tiered, ranked document cards with match reasons.
3. **`POST /api/v2/search/analytics`**
   - Logs search performance, clicks, and zero-result queries for dictionary expansion.

---

## 7. Answers to System & Environment Inquiries

1. **Data Model:**
   - `subjects`: Has `id`, `name`, `subject_code`, `semester` (1–8), and `department_id`.
   - Colleges link to departments via `college_departments(college_id, department_id)`.
   - Documents store `college_id`, `department_id`, `subject_id`, and `document_category`.
   - `subject_aliases`: `id`, `subject_id`, `alias`, `priority`.
2. **Scale & Caching:**
   - Scale: Several hundred to a few thousand documents; < 1,000 active subjects.
   - Supabase: Hosted PostgreSQL cloud.
   - Cache: Python process memory with automated TTL refresh (`_cache`). No Redis needed for this scale.
3. **Alias Seed Data:**
   - Seed dictionary will cover comprehensive B.Tech/BCA curricula (SOA/ITER, KIIT, OUTR, BPUT) for CSE, CSIT, ECE, EE, Mech, Civil, plus all standard first-year engineering subjects.
4. **Implementation Sequence:**
   - **Step 1:** SQL migration (normalized code column, indexes, alias table seeding).
   - **Step 2:** Python In-Memory Resolver & updated `methods/search_api.py` (`/suggest` + `/search`).
   - **Step 3:** Frontend `_search_partial.html` & `script.js` with cascading filters, pills, and match badges.
   - **Step 4:** Golden query testing & benchmark verification.
