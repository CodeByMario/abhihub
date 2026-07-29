"""Fix all bare except clauses and add logging import to supabase_helper.py"""
import re, ast

path = r'e:\Users\abhihub\New folder\abhihub\methods\supabase_helper.py'
# Read in binary to preserve exact bytes, decode as utf-8
raw = open(path, 'rb').read()
# Detect line ending
has_crlf = b'\r\n' in raw
eol = '\r\n' if has_crlf else '\n'
print(f"Line ending: {'CRLF' if has_crlf else 'LF'}")

# Work in text mode using the detected EOL
src = raw.decode('utf-8')
# Normalize to \n for replacements, then restore
src_n = src.replace('\r\n', '\n')
original_len = len(src_n)

changes = 0

def rep(old, new, count=1):
    global src_n, changes
    if old in src_n:
        src_n = src_n.replace(old, new, count)
        changes += 1
        print(f"  [OK] replaced: {repr(old[:50])}")
    else:
        print(f"  [MISS] not found: {repr(old[:60])}")

print("\n--- Applying fixes ---")

# 1. Add logging + traceback imports
rep(
    'import os\nimport json\nfrom datetime import datetime',
    'import os\nimport json\nimport logging\nimport traceback\nfrom datetime import datetime'
)

# 2. Add logger instance
rep(
    'load_dotenv()\n\n# Try to import supabase',
    'load_dotenv()\n\nlog = logging.getLogger(__name__)\n\n# Try to import supabase'
)

# 3. validate_uuid - bare except
rep(
    '        uuid.UUID(str(val))\n        return True\n    except:\n        return False',
    '        uuid.UUID(str(val))\n        return True\n    except Exception:\n        return False'
)

# 4. _doc_to_json - bare except (unique context)
rep(
    "    except:\n        pass\n\n    file_path = url if url else",
    "    except Exception as e:\n        log.debug(f'_doc_to_json: failed to parse description: {e}')\n\n    file_path = url if url else"
)

# 5. search_file_records
rep(
    "        res = q.order('created_at', desc=True).limit(limit).execute()\n        return res.data if res.data else []\n    except:\n        return []",
    "        res = q.order('created_at', desc=True).limit(limit).execute()\n        return res.data if res.data else []\n    except Exception as e:\n        log.error(f'search_file_records error: {e}')\n        return []"
)

# 6. delete_file_record
rep(
    "        res = client.table('documents').delete().eq('id', record_id).eq('uploader_id', u_id).execute()\n        return {'success': True} if res.data else {'success': False}\n    except:\n        return {'success': False}",
    "        res = client.table('documents').delete().eq('id', record_id).eq('uploader_id', u_id).execute()\n        return {'success': True} if res.data else {'success': False}\n    except Exception as e:\n        log.error(f'delete_file_record error: {e}')\n        return {'success': False}"
)

# 7. check_profile_completed
rep(
    "        if res.data: return res.data[0].get('profile_completed', False)\n        return False\n    except:\n        return False",
    "        if res.data: return res.data[0].get('profile_completed', False)\n        return False\n    except Exception as e:\n        log.error(f'check_profile_completed error: {e}')\n        return False"
)

# 8. update_file_record inner try (json.loads)
rep(
    "        try:\n            desc = json.loads(current_desc_str)\n        except:\n            desc = {}",
    "        try:\n            desc = json.loads(current_desc_str)\n        except Exception as e:\n            log.debug(f'update_file_record: invalid JSON in description: {e}')\n            desc = {}"
)

# 9. badge insert bare except
rep(
    "                except:\n                    pass # unique constraint handles duplicates",
    "                except Exception:\n                    pass  # unique constraint handles duplicates"
)

# 10. check_if_labeled
rep(
    "        return len(res.data) > 0\n    except:\n        return False\ndef save_labeled_paper",
    "        return len(res.data) > 0\n    except Exception as e:\n        log.error(f'check_if_labeled error: {e}')\n        return False\ndef save_labeled_paper"
)

# 11. Remove inline traceback import in init_supabase
rep(
    "        except Exception as e:\n            import traceback\n            traceback.print_exc()",
    "        except Exception as e:\n            traceback.print_exc()"
)

# 12. Remove inline traceback import in save_file_record
rep(
    "    except Exception as e:\n        import traceback\n        traceback.print_exc()\n        print(f\"[Supabase] Error saving file record: {e}\")",
    "    except Exception as e:\n        traceback.print_exc()\n        print(f\"[Supabase] Error saving file record: {e}\")"
)

print(f"\n{changes} replacements made")

# Restore line endings if file was CRLF
if has_crlf:
    output = src_n.replace('\n', '\r\n')
else:
    output = src_n

# Write back
with open(path, 'wb') as f:
    f.write(output.encode('utf-8'))

# Verify
try:
    tree = ast.parse(src_n)
    bare = [n.lineno for n in ast.walk(tree) if isinstance(n, ast.ExceptHandler) and n.type is None]
    print(f"Remaining bare excepts: {bare}")
except SyntaxError as e:
    print(f"SyntaxError after edits: {e}")

print(f"Final size: {len(output)} bytes")
