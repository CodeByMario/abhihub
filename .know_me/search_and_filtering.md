# Search & Filtering

## Overview
The platform provides a robust search mechanism that allows users to find documents based on keywords, university/college, branch, semester/year, and document type. It includes custom scoring algorithms to rank relevant results higher.

## Relevant Code
- **`app.py`**:
    - `search()` route (`/search`): Renders the search page UI and processes frontend requests.
    - `_score_item()`: Core logic for ranking documents against a search query.
    - `_apply_filters()`: Filters the document list based on college, branch, year, and type.
    - `_parse_query()` & `_tokenize()`: Helpers for cleaning and analyzing the search string.
    - `suggest()` route (`/suggest`): Provides autocomplete/typeahead suggestions as the user types.
- **`templates/search.html`**: The UI containing the search bar, filter dropdowns, and results container.
- **`static/js/`**: Client-side scripts that handle debouncing search input and fetching results dynamically.

## Search Ranking Logic
When a search is performed, `_score_item` calculates a relevance score based on:
1. **Title Match**: Exact or partial matches in the document title carry the highest weight.
2. **Tag/Keyword Match**: Matches in associated tags or subjects.
3. **Recent Year Boost**: Newer documents or documents belonging to more recent academic years might receive a slight ranking boost (`_recent_year_boost`).

## Filtering
Filters can be applied alongside or independently of a keyword search:
- **College/University**: Narrows down to specific institutions.
- **Branch/Course**: Narrows down to specific study programs (e.g., CSE, ECE).
- **Year/Semester**: Filters by academic level.
- **Type**: Differentiates between Notes, Previous Year Questions (PYQs), Assignments, etc.
