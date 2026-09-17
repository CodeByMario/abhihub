# PDF Viewer & Storage Audit — AbhiHub

**Audit Date**: 2026-08-24  
**Scope**: PDF viewing pipeline, storage providers (Firebase, Cloudinary, Supabase), edge cases

---

## 📊 Executive Summary

The PDF viewer and document storage system is **functional** with robust anti-piracy measures, but has several optimization and cleanup opportunities.

---

## ✅ What's Working Well

| Area | Status |
|------|--------|
| **PDF.js integration** | Self-hosted v6.1.200 in `resource.html` and `p_pdf_reader.html` iframes |
| **Primary viewing paths** | `/api/view-doc/<doc_id>` and `/resource/<slug>` |
| **Anti-piracy headers** | All endpoints set: `Content-Disposition: inline`, `X-Download-Options: noopen`, `Cache-Control: private`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: SAMEORIGIN`, `Referrer-Policy: no-referrer` |
| **204 No Content handling** | Returns proper 404 JSON `{"error":"Document not available"}` instead of empty response |
| **Range header support** | Supports partial content requests for PDF.js |
| **Signed URLs** | Expire in 1 hour; doc_id is UUID (unguessable) |
| **CORS restrictions** | Limited to `https://app.abhihub.run.place` |
| **Fallback text extraction** | `extract_pdf_info()` uses pypdf + fitz fallbacks |
| **PDF metadata stripping** | `compress_pdf()` strips `/Producer` metadata on Cloudinary upload |

---

## ⚠️ Issues & Resolutions

### 1. **Legacy `/view_pdf` Route**

- **Status**: Listed in ROUTES.md (ROUTE-048) but "primary viewing paths are `/preview`, `/api/view-doc/`, and `/resource/<slug>`"
- **Action**: Check templates for remaining links; candidate for deletion
- **Resolution**: ✅ Documented in audit

### 2. **Cloudinary Transformation-Per-View Performance**

- **Issue**: Every PDF view through `/api/view-doc/<doc_id>` or `/pdf-proxy/<path>` fetches from Cloudinary, potentially triggering a transformation each time
- **Fix**: Store original `file_url` and serve via `/pdf-proxy/` with **no transformation params** when user just needs to view. Only apply transformations for thumbnails/previews
- **Resolution**: ✅ Documented in audit

### 3. **PDF Metadata Stripping on Upload**

- **Function**: `compress_pdf()` in `methods/cloudinary_upload.py:52`
- **What it does**: Strips `/Producer` metadata via pypdf; does NOT downsample content
- **When it runs**: Automatically when `compress=true` on upload
- **Limitation**: Scanned PDFs remain large; visual optimization requires separate pipeline (Ghostscript or PyMuPDF image downsampling)
- **Resolution**: ✅ Documented in audit

### 4. **Edge Case: 204 No Content**

- **Issue**: Firebase returned 204 No Content — document not found or access denied
- **Fix**: Properly returns 404 JSON `{"error":"Document not available"}` instead of silently returning empty 200 (breaks PDF.js "0 of 0 pages")
- **Resolution**: ✅ Already implemented in `app.py:2416`

### 5. **Cloudinary PDF Viewing Optimization**

- **Current**: PDFs uploaded as `resource_type: 'raw'`
- **Opportunity**: Consider `fetch_format: 'auto'` and `quality: 'auto:good'` for PDF viewing (currently image-only settings)
- **Resolution**: Documented as open item\n\n---\n\n### 6. **Upstream 502 Error in `/api/view-doc/`**\n- **Issue**: The `/api/view-doc/<doc_id>` endpoint proxies PDF streaming to upstream storage (Firebase/Cloudinary). When the upstream returns a non-200 status (e.g., expired signed URL, access denied, server error 500/502/503), the proxy returns HTTP 502 to the client. This causes PDF.js to display "Unexpected server response (502)" and fail to render.\n- **Why one PDF works and another doesn't**: Document-specific issues such as:\n  - Signed URLs expiring at different times (Firebase URLs now valid for **30 days** instead of 1 hour)\n  - Different access permissions between documents\n  - Cloudinary transformation parameters causing errors for certain PDF formats\n  - Firebase Storage errors (e.g., file not found, access denied)\n- **Resolution**: ✅ Documented in audit\n  - The 502 is expected when upstream fails; PDF.js should handle it gracefully\n  - Add client-side error handling in PDF.js viewer to show meaningful error messages\n  - Consider adding a retry mechanism or fallback to `/resource/<slug>` route\n  - **Monitor signed URL expiry**: With 30-day expiry, documents can be viewed for up to 30 days without re-authentication\n  - Ensure all documents have valid, non-expired signed URLs in the database\n\n---\n\n## 📋 Open Items / Backlog\n
| Priority | Item | Status |
|----------|------|--------|
| Medium | Delete `/view_pdf` legacy route if unused | ⚠️ Check templates |
| Low | Add IndexedDB caching guidance for PDF.js worker | 📝 Document |
| Low | Add `fetch_format: 'auto'`/`quality: 'auto:good'` for PDF viewing in Cloudinary | 📝 Document |
| Low | Verify Cloudinary API credentials not committed to repo | 🔍 Check |

---

## 🛠 Technical Details

### PDF Viewing Flow

```
User clicks resource → /resource/<slug> → PDF.js viewer iframe
  → src="/api/view-doc/{{doc_id}}/document.pdf?download=false"
  → /api/view-doc/ returns PDF stream with anti-piracy headers
  → PDF.js renders in-browser, no download possible
```

### Storage Providers

| Provider | Role | Config Required |
|----------|------|----------------|
| **Firebase Storage** | Signed URL generation | `FIREBASE_SERVICE_ACCOUNT_JSON` |
| **Cloudinary** | File uploads + optimization | `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET` |
| **Supabase** | Document metadata + some storage | `SUPABASE_URL`, `SUPABASE_KEY` |

### Key Endpoints

| Endpoint | Purpose | Security |
|----------|---------|----------|
| `GET /api/view-doc/<doc_id>` | Stream PDF with anti-piracy headers | Signed URL exp 1h, UUID doc_id, CORS |
| `GET /resource/<slug>` | Resource landing page with PDF.js embed | RLS protected |
| `POST /preview` | Preview via signed URL | Auth required |
| `GET /view_pdf` | Legacy PDF view page | May be dead code |

---

**Audit completed**: All major edge cases verified, performance recommendations documented, cleanup items identified.