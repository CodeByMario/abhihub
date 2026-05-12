#!/usr/bin/env python3
"""
Full integration test for Document History Management System.
Tests with real data from the Supabase database.
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from data.db import get_client
from data.interactions import DocumentView

def test_with_real_data():
    """Test with actual documents from the database."""
    print("\n[INTEGRATION TEST] Full History Flow with Real Data")
    print("-" * 60)
    
    client = get_client()
    if not client:
        print("❌ Failed to get Supabase client")
        return False
    
    try:
        # Get a real document
        print("\n1. Finding a real document...")
        docs_response = client.table("documents").select("id, title, uploader_id").limit(1).execute()
        
        if not docs_response.data:
            print("⚠️  No documents found in database")
            return False
        
        doc = docs_response.data[0]
        document_id = doc["id"]
        print(f"   Found document: {doc['title']} (ID: {document_id})")
        
        # Get a real user (the document uploader)
        uploader_id = doc.get("uploader_id")
        if not uploader_id:
            print("   No uploader for this document, getting a random user...")
            users_response = client.table("profiles").select("id").limit(1).execute()
            if users_response.data:
                uploader_id = users_response.data[0]["id"]
            else:
                print("⚠️  No users found in database")
                return False
        
        print(f"   Using user: {uploader_id}")
        
        # Log a document view
        print("\n2. Logging document view...")
        result = DocumentView.log_view(
            user_id=uploader_id,
            document_id=document_id,
            ip_address="127.0.0.1",
            device_type="mobile"
        )
        
        if result.get('success'):
            view_record = result.get('view', {})
            print(f"   ✅ View logged successfully")
            print(f"      View ID: {view_record.get('id')}")
            print(f"      Accessed at: {view_record.get('accessed_at')}")
        else:
            print(f"   ❌ Failed: {result.get('message')}")
            return False
        
        # Retrieve recent documents for the user
        print("\n3. Retrieving recent documents...")
        recent_result = DocumentView.get_recent_for_user(
            user_id=uploader_id,
            limit=5
        )
        
        if recent_result.get('success'):
            count = recent_result.get('count', 0)
            print(f"   ✅ Retrieved {count} recent document(s)")
            
            if count > 0:
                data = recent_result.get('data', [])
                for i, item in enumerate(data, 1):
                    doc_info = item.get('document', {})
                    accessed_at = item.get('accessed_at', 'N/A')
                    print(f"      {i}. {doc_info.get('title', 'Unknown')} - Accessed: {accessed_at}")
        else:
            print(f"   ❌ Failed: {recent_result.get('message')}")
            return False
        
        print("\n✅ Full integration test passed!")
        return True
        
    except Exception as e:
        print(f"\n❌ Exception: {e}")
        import traceback
        traceback.print_exc()
        return False

def check_table_stats():
    """Display statistics about the document_views table."""
    print("\n[TABLE STATS] Document Views Statistics")
    print("-" * 60)
    
    client = get_client()
    if not client:
        print("❌ Failed to get Supabase client")
        return False
    
    try:
        # Get record count
        response = client.table("document_views").select("id", count="exact").limit(1).execute()
        print(f"Total views recorded: {response.count}")
        
        # Get recent views
        recent = client.table("document_views").select("*").order("accessed_at", desc=True).limit(5).execute()
        if recent.data:
            print(f"\nLast 5 views:")
            for i, view in enumerate(recent.data, 1):
                print(f"  {i}. User: {view.get('user_id', 'N/A')[:8]}... | Doc: {view.get('document_id', 'N/A')[:8]}... | Accessed: {view.get('accessed_at', 'N/A')}")
        
        print("\n✅ Table statistics retrieved")
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def main():
    print("\n" + "=" * 60)
    print("Document History Management System - Integration Test")
    print("=" * 60)
    
    # Check table stats first
    check_table_stats()
    
    # Run full integration test
    result = test_with_real_data()
    
    if result:
        print("\n" + "=" * 60)
        print("✅ All integration tests PASSED!")
        print("=" * 60)
        print("\nThe file history management system is working correctly.")
        print("Document views are being properly recorded in Supabase.")
        return 0
    else:
        print("\n" + "=" * 60)
        print("⚠️  Integration test encountered issues")
        print("=" * 60)
        return 1

if __name__ == "__main__":
    sys.exit(main())
