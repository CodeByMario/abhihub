from abc import ABC, abstractmethod
from typing import List, Dict
import time

class StorageProvider(ABC):
    @abstractmethod
    def fetch_assets(self) -> List[Dict]:
        """Fetch all assets from the provider."""
        pass
        
    @abstractmethod
    def get_asset(self, storage_id: str) -> Dict:
        """Get a specific asset by ID."""
        pass
        
    @abstractmethod
    def asset_exists(self, storage_id: str) -> bool:
        """Check if an asset exists in physical storage."""
        pass
        
    @abstractmethod
    def generate_public_url(self, storage_id: str) -> str:
        """Generate a public URL for the asset."""
        pass
        
    @abstractmethod
    def sync(self) -> Dict:
        """Sync storage provider with the storage_assets DB table."""
        pass
        
    @abstractmethod
    def health_check(self) -> bool:
        """Check if provider is available."""
        pass

class CloudinaryProvider(StorageProvider):
    def __init__(self):
        self.provider_name = 'cloudinary'

    def fetch_assets(self) -> List[Dict]:
        from methods.cloudinary_helper import fetch_all_files
        raw_files = fetch_all_files(resource_type="image", use_cache=False)
        
        standardized_files = []
        for f in raw_files:
            standardized_files.append({
                'storage_provider': self.provider_name,
                'storage_id': f.get('public_id'),
                'filename': f.get('filename') or f.get('public_id'),
                'public_url': f.get('url'),
                'size': f.get('size'),
                'bytes': f.get('bytes'),
                'created_at': f.get('created_at'),
                'format': f.get('format', 'unknown'),
                'folder': f.get('folder', ''),
                'path': f.get('path', '')
            })
        return standardized_files
        
    def get_asset(self, storage_id: str) -> Dict:
        # Stub implementation
        return {}
        
    def asset_exists(self, storage_id: str) -> bool:
        # Stub implementation
        return True
        
    def generate_public_url(self, storage_id: str) -> str:
        return f"https://res.cloudinary.com/demo/image/upload/{storage_id}"
        
    def sync(self) -> Dict:
        from methods.supabase_helper import init_supabase
        client = init_supabase()
        if not client: return {"success": False, "message": "Supabase client not initialized"}
        
        assets = self.fetch_assets()
        upserted = 0
        batch_size = 200
        
        for i in range(0, len(assets), batch_size):
            batch = assets[i:i + batch_size]
            data_list = []
            for asset in batch:
                data_list.append({
                    'provider': self.provider_name,
                    'provider_public_id': asset['storage_id'],
                    'filename': asset['filename'],
                    'public_url': asset['public_url'],
                    'mime': asset.get('format', 'unknown')
                })
            
            try:
                client.table('storage_assets').upsert(
                    data_list, 
                    on_conflict='provider,provider_public_id',
                    ignore_duplicates=True
                ).execute()
                upserted += len(data_list)
                import time
                time.sleep(0.1) # Small delay to let sockets breathe
            except Exception as e:
                print(f"Error in batch sync: {e}")
                
        return {"success": True, "upserted": upserted}
        
    def health_check(self) -> bool:
        return True
