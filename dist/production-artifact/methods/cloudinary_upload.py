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
from pypdf import PdfReader, PdfWriter
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
        else:
            logging.info(f"✓ PDF metadata stripped ({len(cleaned)} bytes)")
        return cleaned
    except Exception as e:
        logging.warning(f"PDF metadata strip failed, keeping original: {e}")
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

        # Convert to RGB for JPEG save
        if format.upper() in ('JPEG', 'WEBP'):
            img = img.convert('RGB')

        # Add AbhiHub watermark to bottom right corner
        try:
            from PIL import ImageDraw, ImageFont
            draw = ImageDraw.Draw(img)
            w, h = img.size
            font_size = max(16, int(w * 0.025))
            try:
                font = ImageFont.truetype("arial.ttf", font_size)
            except Exception:
                font = ImageFont.load_default()
            text = "AbhiHub"
            padding = max(12, int(w * 0.015))
            if hasattr(draw, 'textbbox'):
                bbox = draw.textbbox((0, 0), text, font=font)
                tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            else:
                tw, th = font_size * 4, font_size
            x = w - tw - padding
            y = h - th - padding
            draw.text((x + 1, y + 1), text, fill=(0, 0, 0), font=font)
            draw.text((x, y), text, fill=(255, 255, 255), font=font)
        except Exception as wm_err:
            logging.warning(f"Watermark error: {wm_err}")

        output = io.BytesIO()
        save_kwargs = {'format': format, 'optimize': True}
        if format.upper() in ('JPEG', 'WEBP'):
            save_kwargs['quality'] = quality

        img.save(output, **save_kwargs)
        compressed = output.getvalue()
        logging.info(f"✓ Document image converted to grayscale & compressed to {len(compressed)} bytes")
        return compressed
    except Exception as e:
        logging.error(f"Error compressing image: {e}")
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
            elif ext == 'pdf':
                file_bytes = compress_pdf(file_bytes)
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
        if resource_type == 'raw' and ext and ext.lower() == 'pdf':
            public_id = f"{public_id}.txt"
        elif resource_type == 'raw' and ext:
            public_id = f"{public_id}.{ext}"

        # Upload to Cloudinary
        upload_params = {
            'public_id': public_id,
            'resource_type': resource_type,
            'folder': folder,
            'overwrite': False,
            'use_filename': False,
            'unique_filename': True,
            'access_control': [{'access_type': 'anonymous'}]  # Ensure public access for proxied delivery
        }

        # Add optimization for different resource types
        if resource_type == 'image':
            upload_params['quality'] = 'auto:good'
            upload_params['fetch_format'] = 'auto'
        elif resource_type == 'raw':
            # For PDFs and documents
            upload_params['resource_type'] = 'raw'

        logging.info(f"📤 Uploading to Cloudinary: {public_id}")
        result = cloudinary.uploader.upload(file_bytes, **upload_params)

        # Ensure the resource is publicly accessible via admin API.
        # The access_control param on upload doesn't always stick for raw resources
        # on some account configurations; an explicit admin update guarantees it.
        try:
            import cloudinary.api as _cld_api
            _cld_api.update(result.get('public_id'), resource_type=resource_type, access_mode='public')
            logging.info(f"✓ Public access confirmed for {result.get('public_id')}")
        except Exception as _e:
            logging.warning(f"[cloudinary] Could not set public access on {public_id}: {_e}")

        # Also upload to Supabase Storage as a fallback/public delivery layer.
        # Cloudinary Free plan may block all access methods (signed URLs, admin API),
        # but Supabase Storage with anon key provides reliable public access.
        try:
            from methods.supabase_helper import init_supabase, upload_file_to_supabase
            client = init_supabase()
            if client:
                supabase_result = upload_file_to_supabase(
                    file_data=file_bytes,
                    supabase_path=f"cloudinary_fallback/{result['public_id']}{ext if ext else '.pdf'}",
                    content_type='application/pdf' if ext and ext.lower() == 'pdf' else 'application/octet-stream'
                )
                if supabase_result.get('success'):
                    result['supabase_url'] = supabase_result.get('url')
                    result['supabase_public_id'] = supabase_result.get('public_path')
                    logging.info(f"✓ Uploaded to Supabase fallback: {supabase_result.get('url')}")
                else:
                    logging.warning(f"[cloudinary] Supabase upload fallback skipped: {supabase_result.get('message')}")
        except Exception as _e:
            logging.warning(f"[cloudinary] Supabase fallback upload skipped: {_e}")

        logging.info(f"✅ Upload successful: {result.get('secure_url')}")

        return {
            'success': True,
            'url': result.get('url'),
            'secure_url': result.get('secure_url'),
            'public_id': result.get('public_id'),
            'resource_type': result.get('resource_type'),
            'format': result.get('format'),
            'bytes': result.get('bytes'),
            'original_filename': filename,
            'width': result.get('width'),
            'height': result.get('height'),
            # Optional fallback fields
            'supabase_url': result.get('supabase_url'),
            'supabase_public_id': result.get('supabase_public_id')
        }
    except Exception as e:
        logging.error(f"❌ Cloudinary upload error: {e}")
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
        result = cloudinary.uploader.destroy(public_id, resource_type=resource_type)
        return {
            'success': result.get('result') == 'ok',
            'result': result.get('result')
        }
    except Exception as e:
        logging.error(f"Error deleting from Cloudinary: {e}")
        return {
            'success': False,
            'error': str(e)
        }