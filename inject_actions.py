import sys

def inject_ui():
    files_to_update = [
        "e:/code/projects/abhiHub/abhihub/abhi-hub/templates/p_index.html",
        "e:/code/projects/abhiHub/abhihub/abhi-hub/templates/p_store_room.html",
        "e:/code/projects/abhiHub/abhihub/abhi-hub/templates/p_profile.html"
    ]
    
    # We want to add a footer to .file-card cards
    # The hook will be just before the closing </a> tag or </div> of the card for p_index.html
    # Look for loop iteration where we can inject the action bar.
    
    # Actually, it's safer to just inject CSS and JS globally, and add a small snippet inside the card.
    
    action_html = r'''
            <div class="file-card-actions" style="display: flex; gap: 0.5rem; justify-content: space-around; padding-top: 0.5rem; border-top: 1px solid #e5e7eb; width: 100%; margin-top: auto;" onclick="event.preventDefault(); event.stopPropagation();">
              <button class="action-btn like-btn {% if file.get('is_liked') %}active{% endif %}" data-id="{{ file.get('record_id', '') }}" onclick="toggleFileAction(this, 'like')" style="background:none; border:none; cursor:pointer; color: {% if file.get('is_liked') %}#ef4444{% else %}#6b7280{% endif %}; display:flex; gap:4px; align-items:center;">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="{% if file.get('is_liked') %}currentColor{% else %}none{% endif %}" stroke="currentColor" stroke-width="2"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"></path></svg>
                <span class="count">{{ file.get('like_count', 0) }}</span>
              </button>
              <button class="action-btn comment-btn" data-id="{{ file.get('record_id', '') }}" onclick="openComments('{{ file.get('record_id', '') }}')" style="background:none; border:none; cursor:pointer; color: #6b7280; display:flex; gap:4px; align-items:center;">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>
                <span class="count">{{ file.get('comment_count', 0) }}</span>
              </button>
              <button class="action-btn bookmark-btn {% if file.get('is_bookmarked') %}active{% endif %}" data-id="{{ file.get('record_id', '') }}" onclick="toggleFileAction(this, 'bookmark')" style="background:none; border:none; cursor:pointer; color: {% if file.get('is_bookmarked') %}#3b82f6{% else %}#6b7280{% endif %}; display:flex; gap:4px; align-items:center;">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="{% if file.get('is_bookmarked') %}currentColor{% else %}none{% endif %}" stroke="currentColor" stroke-width="2"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"></path></svg>
                <span class="count">{{ file.get('bookmark_count', 0) }}</span>
              </button>
            </div>
'''
    
    for fp in files_to_update:
        try:
            with open(fp, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # For each file, find where to append inside the file card body before the </a> tag.
            # In p_index.html: we look for `</div>\n        </div>\n      </a>`
            
            if 'toggleFileAction(this,' in content:
                print(f"Skipping {fp}, already injected.")
                continue
                
            updated = content.replace(
                '</div>\n        </div>\n      </a>',
                '</div>\n' + action_html + '        </div>\n      </a>'
            )
            
            if updated != content:
                with open(fp, 'w', encoding='utf-8') as f:
                    f.write(updated)
                print(f"Successfully injected HTML into {fp}")
            else:
                print(f"No match found for standard replacement in {fp}")
                
        except Exception as e:
            print(f"Error touching {fp}: {e}")

if __name__ == "__main__":
    inject_ui()
