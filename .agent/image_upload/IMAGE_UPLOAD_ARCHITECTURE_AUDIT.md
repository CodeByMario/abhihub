# AbhiHub Image Upload & Processing Architecture Audit
## Phase 1: Read-Only Audit & Evidence Report

**Module:** Image Upload Improvements  
**Initiative:** Image Capture, Editing, and Direct Upload Optimization  
**Mode:** `READ_ONLY_AUDIT` (Zero source code altered)  
**Status:** Audit Completed — Awaiting Implementation Approval

---

## 1. Upload Entry Points & File Contracts

### 1.1 Entry Routes & Templates
- **Primary Endpoint:** `POST /upload` and `GET /upload` in [`routes/app_pages.py:1120-1410`](file:///e:/Users/abhihub/New%20folder/abhihub/routes/app_pages.py#L1120-L1410).
- **Template Mapping:** `app.py:315` maps `'app/upload.html'` -> [`templates/p_upload.html`](file:///e:/Users/abhihub/New%20folder/abhihub/templates/p_upload.html) (2,095 lines).
- **Client Script:** Embedded `<script>` block in [`templates/p_upload.html:731-2094`](file:///e:/Users/abhihub/New%20folder/abhihub/templates/p_upload.html#L731-L2094). (`static/js/pages/p_upload.js` is an unreferenced 5-line stub).

### 1.2 Input Controls & Capture Attributes
- **Front Side File Input:** [`templates/p_upload.html:73`](file:///e:/Users/abhihub/New%20folder/abhihub/templates/p_upload.html#L73):
  ```html
  <input type="file" id="fileInput" name="upload_document" hidden accept="application/pdf,image/*">
  ```
- **Front Side Camera Input:** [`templates/p_upload.html:74`](file:///e:/Users/abhihub/New%20folder/abhihub/templates/p_upload.html#L74):
  ```html
  <input type="file" id="cameraInput" accept="image/*" capture="environment" hidden>
  ```
- **Back Side File Input:** [`templates/p_upload.html:121`](file:///e:/Users/abhihub/New%20folder/abhihub/templates/p_upload.html#L121):
  ```html
  <input type="file" id="backSideInput" accept="image/*" style="display: none;" onchange="handleBackSideFileSelected(this)">
  ```
  *(Defect: Lacks `capture="environment"`, so tapping on mobile defaults to file gallery rather than camera prompt).*

### 1.3 Validation & Constraints
- **MIME & Magic Bytes:** Validated in [`app.py:596-620`](file:///e:/Users/abhihub/New%20folder/abhihub/app.py#L596-L620) (`validate_file_content`):
  - PDF (`%PDF-`), PNG (`\x89PNG\r\n\x1a\n`), JPEG (`\xff\xd8\xff`), WEBP (`RIFF....WEBP`), GIF (`GIF87a` / `GIF89a`).
- **File Size Ceiling:** `MAX_FILE_SIZE = 50 * 1024 * 1024` (50 MB) in [`app.py`](file:///e:/Users/abhihub/New%20folder/abhihub/app.py) & [`routes/app_pages.py:1157`](file:///e:/Users/abhihub/New%20folder/abhihub/routes/app_pages.py#L1157).

---

## 2. Image Processing & Generation Architecture

### 2.1 Existing Client-Side Processing
- **Implementation:** [`templates/p_upload.html:1279-1323`](file:///e:/Users/abhihub/New%20folder/abhihub/templates/p_upload.html#L1279-L1323) (`compressImageFile`):
  - Canvas-based downscaling: Caps max dimension to `1920px` maintaining aspect ratio.
  - JPEG compression: Re-encodes using `canvas.toBlob(..., 'image/jpeg', 0.82)`.
  - Replaces staged file with compressed `File` object only if output size < input size.
- **Missing On-Device Features:**
  - **No cropping or framing** tool.
  - **No rotation / orientation fix** (0°, 90°, 180°, 270°).
  - **No client-side side-by-side or combined preview** for front and back sides before upload.

### 2.2 Existing Server-Side Processing
- **Implementation:** [`services/doc_scanner.py`](file:///e:/Users/abhihub/New%20folder/abhihub/services/doc_scanner.py) (OpenCV 4.x + NumPy + PIL):
  - `estimate_skew_angle()`: Projection profile variance text tilt detector.
  - `remove_shadows()`: Background division via morphological dilation + median blur.
  - `merge_pages_side_by_side()`: Stitches front and back pages side-by-side with a 16px gutter on a single landscape sheet.
  - `add_watermark()`: Blends AbhiHub watermark in bottom-right corner.
  - `compress_image()`: Downscales to 2400px JPEG at 82 quality.

---

## 3. Storage & Upload Path Architecture

### 3.1 Current Upload Flow
```
User Selection / Camera 
  ↓ (Canvas downscale 1920px, JPEG 0.82)
XHR Multipart POST /upload (File + Back File + Academic Form Metadata)
  ↓
Flask Server (Gunicorn / gevent)
  ↓ (services/doc_scanner.py: deskew, shadow removal, book merge)
Cloudinary Storage (cloudinary.uploader.upload via methods/cloudinary_upload.py)
  ↓
Supabase Database (documents table record creation)
```

### 3.2 Application Server Transit Analysis
- **Current Reality:** File bytes currently transit through the Flask application server (`POST /upload`).
- **Server Platform:** VPS / Gunicorn WSGI. (Bytes do **not** transit through Vercel serverless).
- **On-Device Target:** Moving the crop, rotate, and front+back combination entirely to the client's browser `<canvas>` allows the user to inspect, review, and confirm a single combined, legible image **before** uploading.

---

## 4. Camera & Device Compatibility

- **Mechanism:** HTML5 File Input with `capture="environment"`.
- **Supported Platforms:**
  - iOS Safari: Fully supported; triggers native iOS camera sheet.
  - Android Chrome / Brave / Edge: Fully supported; launches default camera app.
  - Desktop Browsers: Gracefully falls back to standard file picker (webcam is not forcibly opened).
- **Identified Gap:** The back-side input (`#backSideInput`) does not include `capture="environment"`, requiring users to manually navigate file pickers rather than directly taking a photo of the reverse page.

---

## 5. Security & Privacy Controls

- **Authentication:** All upload attempts require session user via `@auth_required`.
- **Input Sanitization:** Filenames are strictly canonicalized using university abbreviations (`_resolve_abbreviations()`).
- **Metadata Privacy:** Client canvas redraw strips GPS and device EXIF metadata before transmission.
- **Cleanliness:** No image byte data or user documents are logged in application traces or telemetry.

---

## 6. Proposed Implementation Plan (Phase 2)

### Step 1: Lightweight On-Device Image Editor Modal (Vanilla Canvas, Zero New Dependencies)
- Add a modal dialog in `templates/p_upload.html`:
  - **Crop Box:** Drag handles for document border adjustment.
  - **Rotate Controls:** 90° clockwise and counter-clockwise rotation buttons.
  - **Preview & Legibility:** Zoom / fit-to-screen preview.
  - **Reversibility:** Retake / Replace, Reset, or Cancel without losing previously selected files.

### Step 2: Front & Back Capture Sequencing
- Enhance `#twoSidedPaperCard`:
  - Offer separate "Camera" and "Gallery" buttons for **both** Front and Back sides.
  - Add `capture="environment"` to back-side camera input.
  - Clear visual tags: `[PAGE 1: FRONT]` and `[PAGE 2: BACK]`.
  - Independent retake / replace for either side.

### Step 3: On-Device Side-by-Side Combiner
- In `templates/p_upload.html`, when two sides are provided:
  - Normalize both images to equal height on an offscreen `<canvas>`.
  - Place Front on Left, 16px white gutter, Back on Right (Book Mode).
  - Render an interactive **Combined Output Preview** for final user confirmation before proceeding to Step 2.
  - Output is exported as a single optimized JPEG `File` object.

### Step 4: Upload Reliability & Cleanup
- Revoke all `URL.createObjectURL` references on replacement or modal exit to prevent memory leaks on mobile devices.
- Retain existing backend fallback (`services/doc_scanner.py` and `routes/app_pages.py`) so existing non-image uploads and legacy flows remain 100% intact.

---

## 7. Approval Request

Phase 1 Read-Only Audit is complete. Zero source code changes were made.
**Do you approve proceeding with the proposed implementation plan?**
