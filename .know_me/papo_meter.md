# Papo Meter

## Overview
The Papo Meter is a profile feature that displays two metrics:
- **पाप (Pap)** — Count of unique files the user has accessed/viewed
- **पुण्य (Punya)** — Total views received by all files uploaded by the user

## Location
Displayed on the profile page (`/profile`) between the hero banner and the two-column grid.

## UI Design
Two side-by-side gradient cards:
- **Pap Card**: Orange-red gradient (`#f97316` → `#ef4444`), 📖 icon
- **Punya Card**: Green gradient (`#10b981` → `#059669`), 🌟 icon

Each card shows the count in large bold text with Hindi label and English description.

## Data Source

### Backend Function: `get_papo_meter_data(user_id)` — `methods/supabase_helper.py`

```python
def get_papo_meter_data(user_id: str) -> Dict:
    # Returns {'pap_count': int, 'punya_count': int}
```

**Pap Count Query:**
```sql
SELECT DISTINCT document_id FROM abhihub.document_views WHERE user_id = ?
```

**Punya Count Query:**
```sql
SELECT view_count FROM abhihub.documents WHERE uploader_id = ?
-- Then sum all view_count values
```

### Profile Route: `app.py` → `profile()`
```python
from methods.supabase_helper import get_papo_meter_data
papo_meter = get_papo_meter_data(user_id)
# Passed to template as data['papo_meter']
```

### Template: `templates/p_profile.html`
```html
{{ data.get('papo_meter', {}).get('pap_count', 0) }}
{{ data.get('papo_meter', {}).get('punya_count', 0) }}
```

## Files
- `methods/supabase_helper.py` — `get_papo_meter_data()`
- `app.py` — Profile route (line ~1382)
- `templates/p_profile.html` — Papo Meter HTML section (after hero, before grid)
