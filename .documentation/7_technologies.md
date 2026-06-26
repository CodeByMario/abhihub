# Technologies Documentation — AbhiHub

## Core Stack

### Backend
| Technology | Version | Purpose | Payment/Plan |
|---|---|---|---|
| Python | 3.x | Core language | Free (open source) |
| Flask | 2.0.1 | Web framework | Free (open source) |
| Gunicorn | 20.1.0 | WSGI production server | Free (open source) |
| Werkzeug | 2.0.3 | WSGI utilities | Free (open source) |
| Flask-WTF | latest | CSRF protection + forms | Free (open source) |
| Flask-Compress | 1.23 | Response compression | Free (open source) |
| Flask-SocketIO | latest | WebSocket support | Free (open source) |
| PyJWT | latest | JWT token handling | Free (open source) |
| python-dotenv | latest | Environment variable loading | Free (open source) |
| python-multipart | latest | Multipart form parsing | Free (open source) |

### Database & Auth
| Technology | Purpose | Plan/Pricing |
|---|---|---|
| Supabase | PostgreSQL database + Auth + RLS | Free tier (up to 500MB, 50K monthly active users). Paid from $25/mo |
| Contact | supabase.com | Email: support@supabase.io |

### File Storage
| Technology | Purpose | Plan/Pricing |
|---|---|---|
| Cloudinary | Document/file storage (PDFs, notes) | Free tier (25GB storage, 25GB bandwidth). Paid plans from $89/mo |
| Firebase Storage | Signature images (MemoryWall) | Free Spark plan (5GB storage, 1GB/day download). Paid Blaze plan (pay-as-you-go) |
| Contact | cloudinary.com | support@cloudinary.com |
| Contact | firebase.google.com | cloud-support@google.com |

### Image Processing
| Technology | Version | Purpose | Payment |
|---|---|---|---|
| Pillow | >=10.0.0 | Image manipulation, word cloud generation, signature composite | Free (open source) |
| wordcloud | latest | Word cloud image generation from text | Free (open source) |

### Push Notifications
| Technology | Purpose | Payment |
|---|---|---|
| pywebpush | Web Push Protocol (VAPID) | Free (open source) |
| VAPID Keys | Generated via `generate_vapid.py` | Free |

### Analytics
| Technology | Purpose | Plan |
|---|---|---|
| Google Analytics 4 (GA4) | User behavior tracking | Free |
| GA4 ID | `G-EH5BGS9BEG` | Free tier |
| Contact | analytics.google.com | analytics-help@google.com |

### Frontend
| Technology | Purpose | Payment |
|---|---|---|
| Vanilla JavaScript | Client-side logic (no framework) | Free |
| HTML5 + CSS3 | UI markup and styling | Free |
| Tailwind CSS | Utility CSS classes | Free (open source) |
| Bootstrap | Grid system + components | Free (open source) |
| Google Fonts (Kanit) | Typography | Free |

### Encryption
| Technology | Purpose | Payment |
|---|---|---|
| AES Encryption | File encryption before storage | Free (open source via `methods/encryption.py`) |
| PyJWT | Token signing | Free (open source) |

---

## Infrastructure & Deployment

| Technology | Purpose | Plan/Pricing |
|---|---|---|
| Heroku / Render | App hosting (Procfile present) | Heroku free tier discontinued; Eco dynos $5/mo. Render free tier available |
| Firebase Admin SDK | 5.2.0 — Server-side Firebase ops (storage bucket: `abhi-hub.appspot.com`) | Free Spark plan |

---

## Development Tools

| Tool | Purpose |
|---|---|
| Node.js + npm | Tailwind CSS build (`package.json` present) |
| Tailwind CLI | CSS compilation (`tailwind.config.js`) |
| Jupyter Notebooks | Data analysis (`rank.ipynb`, `test.ipynb`) |
| Python migration scripts | Data migration utilities |

---

## Payment / UPI Integration

| Method | Details |
|---|---|
| Samsung Pay UPI | QR image stored at `static/payment/Samsungpay Upi.jpeg` |
| UPI ID | (configured separately, not hardcoded) |
| Payment gateway | No automated payment gateway currently integrated — UPI QR used for manual Study Pass payments |

---

## Environment Variables Required

```
# Supabase
SUPABASE_URL=
SUPABASE_KEY=

# Firebase
FIREBASE_CREDENTIALS=  (path to firebase-auth.json)
FIREBASE_STORAGE_BUCKET=abhi-hub.appspot.com

# Cloudinary
CLOUDINARY_CLOUD_NAME=
CLOUDINARY_API_KEY=
CLOUDINARY_API_SECRET=

# Flask
SECRET_KEY=
WTF_CSRF_SECRET_KEY=

# VAPID (Push Notifications)
VAPID_PUBLIC_KEY=
VAPID_PRIVATE_KEY=
VAPID_CLAIM_EMAIL=

# Google Analytics
GA4_MEASUREMENT_ID=G-EH5BGS9BEG
```

---

## Deprecated Technologies

| Technology | Status | Replacement |
|---|---|---|
| Firebase Auth | ❌ Deprecated | Supabase Auth |
| `firebase-config.js` | ❌ Deprecated | `supabase-config.js` |
| Firebase Auth client SDK | ❌ Removed | Supabase client SDK |
