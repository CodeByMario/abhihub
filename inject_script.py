import sys

def inject_script_src():
    files_to_update = [
        "e:/code/projects/abhiHub/abhihub/abhi-hub/templates/p_index.html",
        "e:/code/projects/abhiHub/abhihub/abhi-hub/templates/p_store_room.html",
        "e:/code/projects/abhiHub/abhihub/abhi-hub/templates/p_profile.html"
    ]
    
    script_tag = '<script src="{{ url_for(\'static\', filename=\'premium/js/interactions.js\') }}"></script>'
    
    for fp in files_to_update:
        try:
            with open(fp, 'r', encoding='utf-8') as f:
                content = f.read()
                
            if 'interactions.js' in content:
                print(f"interactions.js already linked in {fp}")
                continue
                
            if '</head>' in content:
                updated = content.replace('</head>', script_tag + '\n</head>')
                with open(fp, 'w', encoding='utf-8') as f:
                    f.write(updated)
                print(f"Successfully linked scripts in {fp}")
            else:
                 updated = content + '\n' + script_tag
                 with open(fp, 'w', encoding='utf-8') as f:
                    f.write(updated)
                 print(f"Appended linked scripts in {fp}")
        except Exception as e:
            print(f"Error {e}")

if __name__ == "__main__":
    inject_script_src()
