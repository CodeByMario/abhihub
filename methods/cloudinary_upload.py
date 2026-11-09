"""
Cloudinary Upload Helper
Provides functions to upload files to Cloudinary with compression and optimization.
"""

import os
import io
import time
import cloudinary
import cloudinary.uploader
from PIL import Image
try:
    from pypdf import PdfReader, PdfWriter
except ImportError:
    PdfReader = PdfWriter = None
from typing import Dict, Optional, BinaryIO
from dotenv import load_dotenv
import logging

# Load environment variables
load_dotenv()

# Configure Cloudinary
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True
)

# File type to resource type mapping
def get_cloudinary_resource_type(filename: str) -> str:
    """
    Determine Cloudinary resource type based on file extension.

    Args:
        filename: Original filename

    Returns:
        'image', 'video', or 'raw'
    """
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''

    image_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'bmp', 'tiff'}
    video_extensions = {'mp4', 'mov', 'avi', 'wmv', 'flv', 'webm'}

    if ext in image_extensions:
        return 'image'
    elif ext in video_extensions:
        return 'video'
    else:
        return 'raw'  # For PDFs, docs, archives, etc.

def compress_pdf(file_data: bytes) -> bytes:
    """
    Strip PDF metadata cleanly using pypdf writer and compress streams.
    Returns valid cleaned PDF bytes, or original on any failure.
    """
    try:
        reader = PdfReader(io.BytesIO(file_data))
        writer = PdfWriter()
        for page in reader.pages:
            try:
                page.compress_content_streams()
            except Exception:
                pass
            writer.add_page(page)
        writer.add_metadata({})
        out = io.BytesIO()
        writer.write(out)
        cleaned = out.getvalue()
        if len(cleaned) < len(file_data):
            logging.info(f"✓ PDF metadata stripped & streams compressed → {len(cleaned)} bytes (was {len(file_data)}")
            return cleaned
        else:
            logging.info(f"✓ PDF compression produced no size reduction; keeping original ({len(file_data)} bytes)")
            return file_data
    except Exception as e:
        logging.warning("PDF metadata strip failed, keeping original (error_type=%s)", type(e).__name__)
        return file_data

def compress_image(file_data: bytes, format: str = 'JPEG', quality: int = 75) -> bytes:
    """
    Compress image, convert document photos to high-contrast grayscale,
    strip EXIF metadata, and maximize legibility of text documents.
    """
    try:
        img = Image.open(io.BytesIO(file_data))

        # Auto-rotate based on EXIF orientation before stripping
        try:
            from PIL import ImageOps
            img = ImageOps.exif_transpose(img)
        except Exception:
            pass

        # Convert to Grayscale & enhance contrast for scanned document text
        from PIL import ImageEnhance, ImageOps
        img = img.convert('L')
        img = ImageOps.autocontrast(img, cutoff=1)
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(1.15)

        # Ensure RGB mode for watermarking and consistent saving
        if img.mode != 'RGB':
            img = img.convert('RGB')

        # Add brand logo image watermark to bottom right corner
        try:
            wm_img_path = os.path.join(os.getcwd(), 'static', 'images', 'logo.png')
            if not os.path.isfile(wm_img_path):
                wm_img_path = os.path.join(os.getcwd(), 'static', 'premium', 'images', 'logo.png')
            if os.path.isfile(wm_img_path):
                wm = Image.open(wm_img_path).convert('RGBA')
                w, h = img.size
                target_wm_w = max(28, int(w * 0.12))
                target_wm_h = int(wm.height * (target_wm_w / wm.width))
                wm = wm.resize((target_wm_w, target_wm_h), Image.Resampling.LANCZOS)
                alpha = wm.split()[3].point(lambda p: int(p * 0.45))
                wm.putalpha(alpha)
                pad = max(12, int(min(w, h) * 0.02))
                img.paste(wm, (w - target_wm_w - pad, h - target_wm_h - pad), wm)
            else:
                from PIL import ImageDraw, ImageFont
                draw = ImageDraw.Draw(img)
                w, h = img.size
                font_size = max(16, int(w * 0.025))
                try: font = ImageFont.truetype("arial.ttf", font_size)
                except Exception: font = ImageFont.load_default()
                text = "AbhiHub"
                padding = max(12, int(w * 0.015))
                bbox = draw.textbbox((0, 0), text, font=font) if hasattr(draw, 'textbbox') else (0,0,font_size*4,font_size)
                tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
                draw.text((w - tw - padding + 1, h - th - padding + 1), text, fill=(0, 0, 0), font=font)
                draw.text((w - tw - padding, h - th - padding), text, fill=(255, 255, 255), font=font)
        except Exception as wm_err:
            logging.warning("Watermark operation failed (error_type=%s)", type(wm_err).__name__)

        output = io.BytesIO()
        save_kwargs = {'format': format, 'optimize': True}
        if format.upper() in ('JPEG', 'WEBP'):
            save_kwargs['quality'] = quality

        img.save(output, **save_kwargs)
        compressed = output.getvalue()
        logging.info(f"✓ Document image converted to grayscale & compressed to {len(compressed)} bytes")
        return compressed
    except Exception as e:
        logging.error("Image compression failed (error_type=%s)", type(e).__name__)
        return file_data

def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename for safe cloud storage.

    Args:
        filename: Original filename

    Returns:
        Sanitized filename
    """
    # Remove path components and dangerous characters
    import re
    filename = os.path.basename(filename)
    filename = re.sub(r'[^\w\s.-]', '_', filename)
    filename = re.sub(r'\s+', '_', filename)
    filename = filename.lower()
    return filename

def upload_file_to_cloudinary(
    file_data: BinaryIO,
    filename: str,
    user_id: str,
    folder: str = "uploads",
    compress: bool = True
) -> Dict:
    """
    Upload file to Cloudinary with compression and user ID tracking.

    Args:
        file_data: File data (file object or bytes)
        filename: Original filename
        user_id: User ID for tracking and naming
        folder: Cloudinary folder path
        compress: Whether to compress images (default: True)

    Returns:
        dict: {
            'success': bool,
            'url': str,
            'secure_url': str,
            'public_id': str,
            'resource_type': str,
            'format': str,
            'bytes': int,
            'original_filename': str,
            'error': str (if failed),
            'supabase_url': str (optional, fallback URL)
        }
    """
    try:
        # Read file data if it's a file object
        if hasattr(file_data, 'read'):
            file_bytes = file_data.read()
            file_data.seek(0)  # Reset for potential reuse
        else:
            file_bytes = file_data

        # Determine resource type
        resource_type = get_cloudinary_resource_type(filename)
        ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''

        original_bytes = len(file_bytes)
        compression_applied = False

        # Compress / clean files if enabled
        if compress:
            if resource_type == 'image':
                format_map = {
                    'jpg': 'JPEG', 'jpeg': 'JPEG',
                    'png': 'PNG', 'webp': 'WEBP'
                }
                image_format = format_map.get(ext, 'JPEG')
                file_bytes = compress_image(file_bytes, format=image_format, quality=85)
                logging.info(f"✓ Image compressed: {len(file_bytes)} bytes")
                compression_applied = len(file_bytes) < original_bytes
            elif ext == 'pdf':
                compressed_bytes = compress_pdf(file_bytes)
                compression_applied = len(compressed_bytes) < original_bytes
                file_bytes = compressed_bytes
                logging.info(f"✓ PDF metadata stripped: {len(file_bytes)} bytes")

        # Create unique filename with user ID and timestamp
        timestamp = int(time.time())
        sanitized_name = sanitize_filename(filename)
        name_without_ext = sanitized_name.rsplit('.', 1)[0] if '.' in sanitized_name else sanitized_name
        ext = sanitized_name.rsplit('.', 1)[-1] if '.' in sanitized_name else ''

        public_id = f"{user_id}_{timestamp}_{name_without_ext}"
        # Cloudinary Free tier blocks PDF sharing/delivery.
        # Keep the file bytes intact, but upload with a non-PDF extension
        # so Cloudinary does not apply PDF-specific delivery restrictions.
        # The app still serves it with Content-Type: application/pdf.
        is_pdf = (ext and ext.lower() == 'pdf') or (resource_type == 'raw' and filename.lower().endswith('.pdf'))
        if is_pdf:
            public_id = f"{public_id}.txt"
            resource_type = 'raw'
        elif resource_type == 'raw' and ext:
            public_id = f"{public_id}.{ext}"

        # Upload to Cloudinary
        upload_params = {
            'public_id': public_id,
            'resource_type': resource_type,
            'type': 'authenticated',
            'folder': folder,
            'overwrite': False,
            'use_filename': False,
            'unique_filename': False,
        }

        # Add optimization for different resource types
        if resource_type == 'image':
            upload_params['quality'] = 'auto:good'
            upload_params['fetch_format'] = 'auto'
        elif resource_type == 'raw':
            # For PDFs and documents
            upload_params['resource_type'] = 'raw'
        logging.info(f"📤 Uploading to Cloudinary: {public_id}")
        if is_pdf and not public_id.lower().endswith('.txt'):
            raise ValueError("PDF Cloudinary public ID must use a .txt suffix")
        result = cloudinary.uploader.upload(file_bytes, **upload_params)

        def _bg_register_storage_asset(res_data, orig_filename):
            try:
                from methods.supabase_helper import init_supabase
                client = init_supabase()
                if client:
                    client.table('storage_assets').upsert({
                        'provider': 'cloudinary',
                        'provider_public_id': res_data.get('public_id'),
                        'filename': orig_filename or res_data.get('original_filename') or res_data.get('public_id'),
                        'public_url': res_data.get('secure_url') or res_data.get('url'),
                        'mime': res_data.get('format', 'unknown'),
                        'status': 'PENDING'
                    }, on_conflict='provider,provider_public_id', ignore_duplicates=True).execute()
            except Exception as _e:
                logging.debug(f"[cloudinary] Storage asset registration skipped: {_e}")

        import threading
        threading.Thread(
            target=_bg_register_storage_asset,
            args=(result, filename),
            daemon=True
        ).start()

        logging.info("✅ Upload successful")

        return {
            'success': True,
            'url': result.get('url'),
            'secure_url': result.get('secure_url'),
            'public_id': result.get('public_id'),
            'resource_type': result.get('resource_type'),
            'format': result.get('format'),
            'bytes': result.get('bytes'),
            'original_filename': filename,
            'cloudinary_filename': f"{public_id.rsplit('/', 1)[-1]}",
            'source_extension': ext,
            'uploaded_extension': 'txt' if is_pdf else ext,
            'pdf_uploaded_as_txt': is_pdf,
            'original_bytes': original_bytes,
            'processed_bytes': len(file_bytes),
            'compression_requested': bool(compress),
            'compression_applied': compression_applied,
            'width': result.get('width'),
            'height': result.get('height'),
            # Optional fallback fields
            'supabase_url': result.get('supabase_url'),
            'supabase_public_id': result.get('supabase_public_id')
        }
    except Exception as e:
        logging.error("Cloudinary upload failed (error_type=%s)", type(e).__name__)
        return {
            'success': False,
            'error': str(e),
            'original_filename': filename
        }

def delete_file_from_cloudinary(public_id: str, resource_type: str = 'raw') -> Dict:
    """
    Delete a file from Cloudinary.

    Args:
        public_id: Cloudinary public ID
        resource_type: Resource type ('image', 'video', or 'raw')

    Returns:
        dict: {'success': bool, 'result': str}
    """
    try:
        result = cloudinary.uploader.destroy(
            public_id, resource_type=resource_type, type='authenticated'
        )
        if result.get('result') != 'ok':
            # Older assets were uploaded with Cloudinary's default public type.
            result = cloudinary.uploader.destroy(
                public_id, resource_type=resource_type, type='upload'
            )
        return {
            'success': result.get('result') == 'ok',
            'result': result.get('result')
        }
    except Exception as e:
        logging.error("Cloudinary delete failed (error_type=%s)", type(e).__name__)
        return {
            'success': False,
            'error': str(e)
        }
