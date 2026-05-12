#!/usr/bin/env python3
"""
Test script for Document History Management System.
Verifies that document views are properly logged to Supabase.
"""

import os
import uuid
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize Supabase client
from data.db import get_client
from data.interactions import DocumentView

def test_supabase_connection():
    """Test if Supabase connection works."""
    print("\n[TEST 1] Supabase Connection")
    print("-" * 50)
    client = get_client()
    if client:
        print("✅ Supabase client initialized successfully")
        return True
    else:
        print("❌ Failed to initialize Supabase client")
        return False

def test_document_views_table():
    """Test if document_views table exists and is accessible."""
    print("\n[TEST 2] Document Views Table Existence")
    print("-" * 50)
    client = get_client()
    if not client:
        print("❌ No Supabase client")
        return False
    
    try:
        # Try to query the table (just count)
        response = client.table("document_views").select("id", count="exact").limit(1).execute()
        print("✅ document_views table is accessible")
        print(f"   Current record count: {response.count}")
        return True
    except Exception as e:
        print(f"❌ Failed to access document_views table: {e}")
        return False

def test_document_view_logging():
    """Test logging a document view."""
    print("\n[TEST 3] Log Document View")
    print("-" * 50)
    
    # Use dummy UUIDs for testing
    test_user_id = str(uuid.uuid4())
    test_doc_id = str(uuid.uuid4())
    
    print(f"Test User ID: {test_user_id}")
    print(f"Test Doc ID: {test_doc_id}")
    
    result = DocumentView.log_view(
        user_id=test_user_id,
        document_id=test_doc_id,
        ip_address="192.168.1.100",
        device_type="desktop"
    )
    
    print(f"Result: {result}")
    
    if result.get('success'):
        print("✅ Document view logged successfully")
        view_record = result.get('view', {})
        print(f"   View ID: {view_record.get('id')}")
        print(f"   Accessed at: {view_record.get('accessed_at')}")
        return True
    else:
        print(f"❌ Failed to log view: {result.get('message')}")
        return False

def test_get_recent_documents():
    """Test retrieving recent documents for a user."""
    print("\n[TEST 4] Get Recent Documents")
    print("-" * 50)
    
    # Use a test user ID
    test_user_id = str(uuid.uuid4())
    print(f"Test User ID: {test_user_id}")
    
    result = DocumentView.get_recent_for_user(
        user_id=test_user_id,
        limit=10
    )
    
    print(f"Result: {result}")
    
    if result.get('success'):
        count = result.get('count', 0)
        print(f"✅ Retrieved recent documents (count: {count})")
        
        if count > 0:
            docs = result.get('data', [])
            for i, item in enumerate(docs[:3]):  # Show first 3
                print(f"   Document {i+1}: {item.get('document', {}).get('title', 'Unknown')}")
        return True
    else:
        print(f"❌ Failed to get recent documents: {result.get('message')}")
        return False

def test_uuid_validation():
    """Test UUID validation."""
    print("\n[TEST 5] UUID Validation")
    print("-" * 50)
    
    from data.db import validate_uuid
    
    valid_uuid = str(uuid.uuid4())
    invalid_uuid = "not-a-uuid"
    
    print(f"Valid UUID: {valid_uuid} → {validate_uuid(valid_uuid)}")
    print(f"Invalid UUID: {invalid_uuid} → {validate_uuid(invalid_uuid)}")
    
    if validate_uuid(valid_uuid) and not validate_uuid(invalid_uuid):
        print("✅ UUID validation working correctly")
        return True
    else:
        print("❌ UUID validation failed")
        return False

def main():
    """Run all tests."""
    print("\n" + "=" * 50)
    print("Document History Management System - Test Suite")
    print("=" * 50)
    
    tests = [
        test_supabase_connection,
        test_document_views_table,
        test_uuid_validation,
        test_document_view_logging,
        test_get_recent_documents,
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"\n❌ Test exception: {e}")
            import traceback
            traceback.print_exc()
            results.append(False)
    
    # Summary
    print("\n" + "=" * 50)
    print("Test Summary")
    print("=" * 50)
    passed = sum(results)
    total = len(results)
    print(f"Passed: {passed}/{total}")
    
    if all(results):
        print("\n✅ All tests passed! Document history system is working correctly.")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Please review the output above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
