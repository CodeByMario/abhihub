# PDF.js CORS Fix

## Problem

PDF.js viewer embedded in iframes (via `/resource/<slug>` or `/p_pdf_reader.html`) was throwing CORS errors when loading PDFs. The root cause was that the `/api/view-doc/<doc_id>` proxy endpoint's CORS headers were not properly configured for the app's own domain.

## Root Cause

The `_ALLOWED_PROXY_HOSTS` set in `app.py` (line 2230-2234) only included cloud storage domains but **missed the app domain**:

```python
_ALLOWED_PROXY_HOSTS = {
    'storage.googleapis.com',
    'firebasestorage.googleapis.com',
    'res.cloudinary.com',
}
```

When PDF.js viewer (running from `app.abhihub.run.place` or a custom domain) made cross-origin requests through the proxy, the CORS header logic defaulted to `https://app.abhihub.run.place`, which didn't match the actual deployment domain, causing browsers to block the response.

## Fix

### 1. Add App Domain to Allowed Hosts

Update `_ALLOWED_PROXY_HOSTS` in `app.py` to include the deployment domain:

```python
_ALLOWED_PROXY_HOSTS = {
    'storage.googleapis.com',
    'firebasestorage.googleapis.com', 
    'res.cloudinary.com',
    'app.abhihub.run.place',  # ADD: enables CORS for app domain
}
```

### 2. Verify CORS Header Logic

The proxy's CORS header at lines 2266, 2361, 2386:

```python
'Access-Control-Allow-Origin': request.host if request.host in _ALLOWED_PROXY_HOSTS else 'https://app.abhihub.run.place'
```

With `app.abhihub.run.place` now in the set, requests originating from the app domain will correctly return `request.host` (the app's own host), properly satisfying the browser's CORS check.

### 3. Optional: Update Viewer.html CSP

If issues persist, the PDF.js viewer's Content-Security-Policy in `viewer.html` (line 32) can be made more permissive:

```html
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'self' 'wasm-unsafe-eval'; worker-src 'self' blob:; style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; media-src blob:; font-src 'self' data:; connect-src 'self' https://app.abhihub.run.place blob: data:; base-uri 'none'; form-action 'none';" />
```

Adding `https://app.abhihub.run.place` to `connect-src` explicitly ensures PDF.js worker connections are allowed.

## Verification

After applying the fix:

1. Restart the Flask application
2. Access a PDF through the viewer (e.g., `/resource/<slug>` or `p_pdf_reader.html`)
3. Open browser DevTools → Network tab
4. Verify the `/api/view-doc/<doc_id>` response has:
   - `Access-Control-Allow-Origin: https://<your-domain>.com` (or `*` if appropriately configured)
   - No CORS-related console errors
5. Test both production domain and localhost development

## Related Pitfalls (from flask-security-audit skill)

- **Pitfall #9**: Missing `@auth_required` distinction — `/api/view-doc/<doc_id>` used as a public viewer proxy must NOT have `@auth_required`, only Firebase signed URL + Referer protection
- **Pitfall #22**: Referer check string-contains fails for `localhost:5000` — use host parsing instead
- **Service Worker interference**: SW may cache PDF streams and lose Range headers; exclude `/api/view-doc/` from SW caching