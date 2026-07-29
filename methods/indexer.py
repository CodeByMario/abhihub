"""
Background Indexer Module
Handles tokenization, alias expansion, and weighting for the search_documents table.
"""
import re
import json
from methods.supabase_helper import init_supabase

_ALNUM = re.compile(r"[A-Za-z0-9]+")

def _normalize(text: str) -> str:
    return (text or "").lower()

def _tokenize(text: str) -> list:
    return _ALNUM.findall(_normalize(text))

def generate_search_vector(title: str, subject_name: str, subject_code: str, aliases: list) -> dict:
    """
    Generate weighted tokens.
    Exact subject match = 100
    Title match = 70
    Alias match = 50
    """
    vector = {}
    
    def _add_tokens(text, weight):
        for token in _tokenize(text):
            vector[token] = max(vector.get(token, 0), weight)
            
    _add_tokens(subject_code, 100)
    _add_tokens(subject_name, 100)
    _add_tokens(title, 70)
    
    for alias in aliases:
        _add_tokens(alias, 50)
        
    return vector

def process_pending_documents():
    """
    Polls the search_documents table for 'pending' documents and indexes them.
    """
    client = init_supabase()
    if not client: return False
    
    try:
        # Get pending documents
        res = client.table('search_documents').select('*').eq('status', 'pending').limit(50).execute()
        docs = res.data or []
        
        if not docs: return True
        
        for doc in docs:
            try:
                # Fetch subject info and aliases
                subject_id = doc.get('subject_id')
                subject_name = ""
                subject_code = ""
                aliases = []
                
                if subject_id:
                    sub_res = client.table('subjects').select('name, subject_code').eq('id', subject_id).execute()
                    if sub_res.data:
                        subject_name = sub_res.data[0].get('name', '')
                        subject_code = sub_res.data[0].get('subject_code', '')
                        
                        # Auto-generate acronym from subject name (e.g., Transform Numerical Method -> tnm)
                        if subject_name:
                            words = [w for w in re.split(r'\W+', subject_name) if w and w.lower() not in ['and', 'of', 'the', '&']]
                            acronym = "".join([w[0] for w in words]).lower()
                            if len(acronym) > 1:
                                aliases.append(acronym)
                        
                    alias_res = client.table('subject_aliases').select('alias').eq('subject_id', subject_id).execute()
                    if alias_res.data:
                        aliases.extend([a.get('alias') for a in alias_res.data])
                
                title = doc.get('normalized_title') or ''
                vector = generate_search_vector(title, subject_name, subject_code, aliases)
                
                # Concatenate all searchable terms into normalized_title for easy substring matching
                searchable_text = f"{title} {subject_name} {subject_code} {' '.join(aliases)}".lower()
                
                # Update document
                client.table('search_documents').update({
                    'search_vector': vector,
                    'normalized_title': searchable_text,
                    'status': 'ready'
                }).eq('file_id', doc['file_id']).execute()
                
            except Exception as e:
                print(f"Error indexing document {doc.get('file_id')}: {e}")
                client.table('search_documents').update({'status': 'failed'}).eq('file_id', doc.get('file_id')).execute()
                
        return True
    except Exception as e:
        print(f"Indexer error: {e}")
        return False
