"""
Patch upload categorization:
- Images categorized as 'image'
- PDFs categorized as 'pdf' (uploaded as raw .txt)
"""
import os

# 1. Patch routes/api.py
api_path = os.path.join('routes', 'api.py')
with open(api_path, 'r', encoding='utf-8') as f:
    api_content = f.read()

target_api = """        # Cloudinary result fields
        public_id = data.get('public_id', '')
        secure_url = data.get('secure_url', '')
        file_size = data.get('bytes', 0)
        file_type = data.get('format', 'pdf')
        original_filename = os.path.basename(
            str(data.get('original_filename') or data.get('file_name') or '')
        )
        is_pdf_upload = (
            original_filename.lower().endswith('.pdf')
            or str(data.get('file_type') or '').lower() == 'pdf'
            or str(public_id).lower().endswith('.txt')
        )
        if is_pdf_upload:
            # Cloudinary must store PDFs as raw assets with a .txt public ID.
            # Do not persist a provider response URL that still contains .pdf.
            public_id = str(public_id)
            if public_id.lower().endswith('.txt.pdf'):
                public_id = public_id[:-4]
            elif not public_id.lower().endswith('.txt'):
                public_id = f"{public_id.rsplit('.', 1)[0] if '.' in public_id else public_id}.txt"
            cloud_name = os.getenv('CLOUDINARY_CLOUD_NAME', '')
            if cloud_name:
                secure_url = (
                    f"https://res.cloudinary.com/{cloud_name}/raw/upload/{public_id}"
                )
            file_type = 'pdf'"""

replacement_api = """        # Cloudinary result fields
        public_id = data.get('public_id', '')
        secure_url = data.get('secure_url', '')
        file_size = data.get('bytes', 0)
        original_filename = os.path.basename(
            str(data.get('original_filename') or data.get('file_name') or '')
        )
        orig_lower = original_filename.lower()
        pub_lower = str(public_id).lower()
        raw_format = str(data.get('format') or '').lower()
        raw_type = str(data.get('file_type') or '').lower()
        secure_url_lower = str(secure_url).lower()

        # Categorize images vs PDFs accurately
        image_extensions = ('.png', '.jpg', '.jpeg', '.webp', '.gif', '.svg', '.bmp', '.tiff')
        is_image_upload = (
            any(orig_lower.endswith(ext) for ext in image_extensions)
            or raw_format in ('png', 'jpg', 'jpeg', 'webp', 'gif', 'bmp', 'svg')
            or raw_type in ('image', 'img')
            or '/image/upload/' in secure_url_lower
        )

        is_pdf_upload = (
            not is_image_upload and (
                orig_lower.endswith('.pdf')
                or raw_type == 'pdf'
                or pub_lower.endswith('.txt')
                or '/raw/upload/' in secure_url_lower
            )
        )

        if is_image_upload:
            file_type = 'image'
        elif is_pdf_upload:
            # Cloudinary stores PDFs as raw assets with a .txt public ID.
            public_id = str(public_id)
            if public_id.lower().endswith('.txt.pdf'):
                public_id = public_id[:-4]
            elif not public_id.lower().endswith('.txt'):
                public_id = f"{public_id.rsplit('.', 1)[0] if '.' in public_id else public_id}.txt"
            cloud_name = os.getenv('CLOUDINARY_CLOUD_NAME', '')
            if cloud_name:
                secure_url = (
                    f"https://res.cloudinary.com/{cloud_name}/raw/upload/{public_id}"
                )
            file_type = 'pdf'
        else:
            file_type = raw_type if raw_type in ('pdf', 'image', 'document', 'archive') else 'document'"""

if target_api in api_content:
    api_content = api_content.replace(target_api, replacement_api, 1)

target_save_call = """            file_type=file_type if file_type in ('pdf', 'image', 'document') else 'pdf',"""
replacement_save_call = """            file_type=file_type,"""
if target_save_call in api_content:
    api_content = api_content.replace(target_save_call, replacement_save_call, 1)

with open(api_path, 'w', encoding='utf-8') as f:
    f.write(api_content)
print("Patched routes/api.py upload categorization")

# 2. Patch methods/supabase_helper.py
sb_path = os.path.join('methods', 'supabase_helper.py')
with open(sb_path, 'r', encoding='utf-8') as f:
    sb_content = f.read()

target_sb = """            'provider_public_id': cloudinary_public_id,
            'file_type': file_type,
            'file_size_bytes': file_size,"""

replacement_sb = """            'provider_public_id': cloudinary_public_id,
            'file_type': 'image' if (
                any((final_file_name or file_name or '').lower().endswith(ext) for ext in ('.png', '.jpg', '.jpeg', '.webp', '.gif', '.svg', '.bmp'))
                or file_type == 'image'
                or '/image/upload/' in str(file_url or '').lower()
            ) else ('pdf' if (
                (final_file_name or file_name or '').lower().endswith('.pdf')
                or str(cloudinary_public_id or '').lower().endswith('.txt')
                or file_type == 'pdf'
                or '/raw/upload/' in str(file_url or '').lower()
            ) else (file_type or 'pdf')),
            'file_size_bytes': file_size,"""

if target_sb in sb_content:
    sb_content = sb_content.replace(target_sb, replacement_sb, 1)
    with open(sb_path, 'w', encoding='utf-8') as f:
        f.write(sb_content)
    print("Patched methods/supabase_helper.py canonical file_type determination")
else:
    print("Target not found in supabase_helper.py")

# 3. Patch static/js/bulk_upload.js
bulk_path = os.path.join('static', 'js', 'bulk_upload.js')
with open(bulk_path, 'r', encoding='utf-8') as f:
    b_content = f.read()

target_bulk = """                          program: preparedValue('program', 'b.tech'),
                          file_hash: item.fileHash || ''"""

replacement_bulk = """                          program: preparedValue('program', 'b.tech'),
                          file_hash: item.fileHash || '',
                          file_type: (item.file?.type?.startsWith('image/') || /\\.(png|jpe?g|webp|gif|bmp|svg)$/i.test(item.name || '')) ? 'image' : (/\\.pdf$/i.test(item.name || '') ? 'pdf' : (uploadResult.format || 'pdf'))"""

if target_bulk in b_content:
    b_content = b_content.replace(target_bulk, replacement_bulk, 1)
    with open(bulk_path, 'w', encoding='utf-8') as f:
        f.write(b_content)
    print("Patched static/js/bulk_upload.js client-side file_type metadata")
else:
    print("Target not found in bulk_upload.js")
