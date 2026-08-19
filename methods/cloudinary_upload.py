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


def compress_image(file_data: bytes, format: str = 'JPEG', quality: int = 90) -> bytes:
    """
    Compress image, auto-rotate from EXIF, and strip all metadata.
    Quality 90 keeps text in scanned papers sharp.
    """
    try:
        img = Image.open(io.BytesIO(file_data))

        # Auto-rotate based on EXIF orientation before stripping
        try:
            from PIL import ImageOps
            img = ImageOps.exif_transpose(img)
        except Exception:
            pass  # Non-critical; continue without rotation fix

        # Convert to RGB for JPEG/WEBP (drop alpha, palette)
        if format.upper() in ('JPEG', 'WEBP') and img.mode not in ('RGB',):
            bg = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode in ('RGBA', 'LA'):
                bg.paste(img, mask=img.split()[-1])
            else:
                bg.paste(img.convert('RGB'))
            img = bg

        # Strip EXIF by saving clean to buffer (no putdata needed after convert)
        output = io.BytesIO()
        save_kwargs = {'format': format, 'optimize': True}
        if format.upper() in ('JPEG', 'WEBP'):
            save_kwargs['quality'] = quality

        img.save(output, **save_kwargs)
        compressed = output.getvalue()
        logging.info(f"✓ EXIF stripped+rotated, compressed to {len(compressed)} bytes")
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
            'error': str (if failed)
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
        
        # Compress images if enabled
        if compress and resource_type == 'image':
            ext = filename.rsplit('.', 1)[-1].lower()
            format_map = {
                'jpg': 'JPEG', 'jpeg': 'JPEG',
                'png': 'PNG', 'webp': 'WEBP'
            }
            image_format = format_map.get(ext, 'JPEG')
            file_bytes = compress_image(file_bytes, format=image_format, quality=85)
            logging.info(f"✓ Image compressed: {len(file_bytes)} bytes")
        
        # Create unique filename with user ID and timestamp
        timestamp = int(time.time())
        sanitized_name = sanitize_filename(filename)
        name_without_ext = sanitized_name.rsplit('.', 1)[0] if '.' in sanitized_name else sanitized_name
        ext = sanitized_name.rsplit('.', 1)[-1] if '.' in sanitized_name else ''
        
        public_id = f"{folder}/{user_id}_{timestamp}_{name_without_ext}"
        
        # Upload to Cloudinary
        upload_params = {
            'public_id': public_id,
            'resource_type': resource_type,
            'folder': folder,
            'overwrite': False,
            'use_filename': False,
            'unique_filename': True
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
            'height': result.get('height')
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
