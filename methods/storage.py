help = '''\
    This module provides upload, download, list, and delete features for Firebase Storage.
    '''

from firebase_admin import storage, get_app
from google.api_core.retry import Retry
from datetime import timedelta
import json
import os
from datetime import datetime

# Get the default app initialized in app.py
default_app = get_app()

# DEFERRED: storage.bucket() crashes if Firebase credentials are missing or invalid.
# Use a lazy proxy so the bucket is only accessed when a storage operation is actually performed.
_bucket = None  # Lazily initialized

def _get_bucket():
    """Return Firebase storage bucket, initializing on first access."""
    global _bucket
    if _bucket is None:
        _bucket = storage.bucket(app=default_app)
    return _bucket

def upload_file(file_path, destination_blob_name, chunk_size=15 * 1024 * 1024, timeout=600):
    blob = _get_bucket().blob(destination_blob_name)
    blob.chunk_size = chunk_size  # Set the chunk size to 15 MB
    retry = Retry(deadline=timeout)  # Set the retry deadline to handle timeouts
    blob.upload_from_filename(file_path, timeout=timeout, retry=retry)
    print(f'File {file_path} uploaded to {destination_blob_name}.')

    # Add file details to data/data.json
    info_temp = destination_blob_name.split('/')
    info = {
        'file-name': info_temp[-1].split('.')[0],
        'file-type': info_temp[-1].split('.')[1],
        'file-path': destination_blob_name,
        'author': info_temp[1] if len(info_temp) > 1 else '',
        'type': info_temp[2] if len(info_temp) > 2 else '',
        'date': info_temp[3] if len(info_temp) > 3 else '',
        'subject': info_temp[4] if len(info_temp) > 4 else '',
        'url': blob.generate_signed_url(version="v4", expiration=timedelta(hours=1))
    }

    # Load existing data if available
    existing_data = []
    if os.path.exists('data/data.json'):
        with open('data/data.json', 'r') as f:
            existing_data = json.load(f)

    # Add new file info and remove duplicates
    combined_data = {item['file-path']: item for item in existing_data}
    combined_data[destination_blob_name] = info
    unique_library = list(combined_data.values())

    # Save the unique data to data/data.json file
    os.makedirs('data', exist_ok=True)
    with open('data/data.json', 'w') as f:
        json.dump(unique_library, f, indent=4)

file_cache = {}

def list_files(folder):
    # Check if the folder is already cached
    if folder in file_cache:
        return file_cache[folder]

    # Fetch blobs from the bucket with the specified prefix
    blobs = _get_bucket().list_blobs(prefix=folder)
    file_list = [blob.name for blob in blobs if not blob.name.endswith('/')]

    # Load existing data from the JSON file if available
    existing_data = []
    existing_data_dict = {}
    data_file_path = 'data/data.json'
    if os.path.exists(data_file_path):
        with open(data_file_path, 'r') as f:
            try:
                existing_data = json.load(f)
                # Create a dictionary with file-path as key for quick lookup
                existing_data_dict = {item['file-path']: item for item in existing_data}
            except json.JSONDecodeError:
                print(f"Error decoding JSON from {data_file_path}. Using an empty list.")

    # Generate file metadata
    library = []
    for file_p in file_list:
        blob = _get_bucket().blob(file_p)
        info_temp = file_p.split('/')

        # Check if this file already exists in our data
        existing_file = existing_data_dict.get(file_p)

        # Extract metadata based on new style
        if "AbhiHub" in info_temp:
            file_name_parts = info_temp[-1].split('_')
            # Handle the file extension properly
            if '.' in file_name_parts[-1]:
                last_part = file_name_parts[-1].split('.')
                file_name_parts[-1] = last_part[0]
                file_extension = last_part[1]
            else:
                file_extension = ''
                
            info = {
                'file-name': '_'.join(file_name_parts),
                'file-type': file_extension,
                'file-path': file_p,
                'author': 'AbhiHub',
                'type': info_temp[2] if len(info_temp) > 2 else '',
                'subject': file_name_parts[0] if len(file_name_parts) > 0 else '',
                'exam': file_name_parts[1] if len(file_name_parts) > 1 else '',
                'year': file_name_parts[2] if len(file_name_parts) > 2 else '',
                'status': True,
            }
        else:
            info = {
                'file-name': info_temp[-1].split('.')[0],
                'file-type': info_temp[-1].split('.')[1] if '.' in info_temp[-1] else '',
                'file-path': file_p,
                'author': info_temp[1] if len(info_temp) > 1 else '',
                'type': info_temp[2] if len(info_temp) > 2 else '',
                'year': info_temp[3] if len(info_temp) > 3 else '',
                'subject': info_temp[4] if len(info_temp) > 4 else '',
                'status': False,
            }
        
        # Preserve existing metadata if file already exists
        if existing_file:
            # Keep the original date_added timestamp
            info['date_added'] = existing_file.get('date_added', existing_file.get('last_updated', datetime.now().isoformat()))
            # Preserve verified status if it exists
            info['verified'] = existing_file.get('verified', False)
            # Keep last_updated if it exists (for backward compatibility)
            if 'last_updated' in existing_file:
                info['last_updated'] = existing_file['last_updated']
        else:
            # New file - set the date_added timestamp
            info['date_added'] = datetime.now().isoformat()
            info['verified'] = False
        
        library.append(info)

    # Create unique library using file-path as key
    combined_data = {item['file-path']: item for item in library}

    unique_library = list(combined_data.values())

    # Save the unique data back to the JSON file
    os.makedirs(os.path.dirname(data_file_path), exist_ok=True)
    with open(data_file_path, 'w') as f:
        json.dump(unique_library, f, indent=4)

    # Cache the result for future calls
    file_cache[folder] = unique_library
    return unique_library

def download_file(destination_blob_name, file_path='static/test/', timeout=600):
    blob = _get_bucket().blob(destination_blob_name)
    retry = Retry(deadline=timeout)  # Set the retry deadline to handle timeouts
    blob.download_to_filename(file_path, timeout=timeout, retry=retry)
    print(f'File {destination_blob_name} downloaded to {file_path}.')

def delete_file(destination_blob_name, timeout=600):
    blob = _get_bucket().blob(destination_blob_name)
    retry = Retry(deadline=timeout)  # Set the retry deadline to handle timeouts
    blob.delete(timeout=timeout, retry=retry)
    print(f'File {destination_blob_name} deleted.')

