"""Fix upload_notifier.py bare except at line 138"""
import ast

path = r'e:\Users\abhihub\New folder\abhihub\methods\upload_notifier.py'
src = open(path, encoding='utf-8').read()
orig = src

src = src.replace(
    "        except:\n            logging.warning(f\"Could not update status/notified columns for {file_record_id} (might be missing in abhihub schema)\")\n            return True # Return true so we don't spam errors in scheduler",
    "        except Exception as e:\n            logging.warning(f\"Could not update status/notified columns for {file_record_id}: {e}\")\n            return True  # Return true so we don't spam errors in scheduler"
)

if src != orig:
    open(path, 'w', encoding='utf-8').write(src)
    print("upload_notifier.py: fixed")
    tree = ast.parse(src)
    bare = [n.lineno for n in ast.walk(tree) if isinstance(n, ast.ExceptHandler) and n.type is None]
    print(f"Remaining bare excepts: {bare}")
else:
    print("MISS: pattern not found")
    # show what's around line 138
    lines = src.splitlines()
    for i in range(133, 145):
        print(f"L{i+1}: {repr(lines[i])}")
