# Linking / Routing Documentation — AbhiHub

## Backend: Flask (`app.py`)

All routes are defined in `app.py` (2978 lines). Route naming pattern:

```python
@app.route('/route')
def route_name():
    return render_template('p_template.html', **context)
```

---

## Public Routes (No Auth Required)

| URL | Template | Description |
|---|---|---|
| `/` | `p_landing.html` | Landing/home page |
| `/login` | `p_login.html` | Login page |
| `/signup` | `p_signup.html` | Signup page |
| `/forgot-password` | `forgot_password.html` | Forgot password |
| `/reset-password` | `reset_password_form.html` | Reset password form |
| `/about` | `p_about.html` | About page |
| `/team` | `team.html` | Team page |
| `/contact` | `contact.html` | Contact form |
| `/features` | `features.html` | Features page |
| `/privacy` | `privacy.html` | Privacy policy |
| `/terms` | `terms.html` | Terms of service |
| `/ranking` | `p_ranking.html` | Public leaderboard |
| `/m/<slug>` | `know_me/public_wall.html` | MemoryWall public page |

---

## Authenticated Routes (`@auth_required`)

| URL | Template | Description |
|---|---|---|
| `/dashboard` | `p_index.html` | Main dashboard |
| `/profile` | `p_profile.html` | User profile |
| `/account` | `p_account.html` | Account settings |
| `/update-account` (POST) | — | Update profile data |
| `/upload` | `p_upload.html` | Upload gate/page |
| `/upload-gate` | `p_upload_gate.html` | Upload access gate |
| `/view` | `p_view.html` | Document viewer |
| `/search` | `p_search.html` | Search page |
| `/store-room` | `p_store_room.html` | Store room |
| `/file-receiver` | `p_file_receiver.html` | Received files |
| `/share-receiver` | `p_share_receiver.html` | Shared file receiver |
| `/pdf-reader` | `p_pdf_reader.html` | PDF reader |
| `/exam` | `exam_page.html` | Exam page |
| `/support` | `p_support.html` | Support page |
| `/settings` | `settings.html` | Settings |
| `/memorywall` | `know_me/dashboard.html` | MemoryWall dashboard |
| `/memorywall/create` | `know_me/create.html` | Create wall |
| `/memorywall/reveal/<wall_id>` | `know_me/reveal.html` | Reveal wall results |
| `/memorywall/closed` | `know_me/closed.html` | Closed wall page |

---

## Admin Routes (`@admin_required`)

| URL | Template | Description |
|---|---|---|
| `/admin` | `admin_dashboard.html` | Admin dashboard |
| `/admin/notifications` | `admin_notification_panel.html` | Push notification panel |

---

## API Routes (JSON)

### Auth
| Method | URL | Auth | Description |
|---|---|---|---|
| `GET/POST` | `/auth/callback` | — | Supabase auth callback |
| `POST` | `/logout` | session | Logout |

### Documents / Files
| Method | URL | Auth | Description |
|---|---|---|---|
| `POST` | `/api/interactions/like` | required | Like a document |
| `POST` | `/api/interactions/bookmark` | required | Bookmark a document |
| `GET` | `/api/quota` | required | Get paper quota |
| `POST` | `/store-room/api/label` | required | Label store room file |

### MemoryWall / Know Me
| Method | URL | Auth | Description |
|---|---|---|---|
| `POST` | `/api/memorywall/submit` | none (rate-limited) | Submit friend response |
| `POST` | `/api/memorywall/upload-signature` | none | Upload signature PNG |
| `GET` | `/api/memorywall/stats/<wall_id>` | required (owner only) | Get wall stats |

### Push Notifications
| Method | URL | Auth | Description |
|---|---|---|---|
| `POST` | `/api/push/subscribe` | required | Subscribe to push |
| `POST` | `/api/push/unsubscribe` | required | Unsubscribe |
| `POST` | `/api/push/send` | admin | Send push notification |

---

## Auth Decorators

```python
@auth_required   # checks session['user'], redirects to /login or returns 401
@admin_required  # checks email against admin list
```

---

## Template Includes

```jinja2
{% include 'p_nav.html' %}           {# Bottom nav — all auth pages #}
{% include 'footer.html' %}          {# Footer — public pages #}
{% include 'navbar_public.html' %}   {# Top nav — public pages #}
{% include 'google_tag.html' %}      {# GA4 — in p_struct.html #}
{% include 'includes/promo_card.html' %}
```

---

## Static File URLs

```
/static/css/<file>          → static/css/
/static/js/<file>           → static/js/
/static/images/<file>       → static/images/
/static/premium/css/<file>  → static/premium/css/
/static/premium/js/<file>   → static/premium/js/
```
