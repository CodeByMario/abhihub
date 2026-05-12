import os

html_path = r'e:\code\projects\abhiHub\abhihub\abhi-hub\templates\p_store_room.html'
css_path = r'e:\code\projects\abhiHub\abhihub\abhi-hub\static\css\abhihub-theme.css'

with open(html_path, 'r', encoding='utf-8') as f:
    html_content = f.read()

start_idx = html_content.find('<style>')
end_idx = html_content.find('</style>')

if start_idx != -1 and end_idx != -1:
    end_idx += len('</style>')
    css_content = html_content[start_idx + len('<style>'):end_idx - len('</style>')]
    
    with open(css_path, 'a', encoding='utf-8') as f:
        f.write('\n\n/* Store Room CSS extracted from p_store_room.html */\n')
        f.write(css_content)
        
    link_tag = '<link rel="stylesheet" href="{{ url_for(\'static\', filename=\'css/abhihub-theme.css\') }}">'
    
    new_html_content = html_content[:start_idx] + link_tag + html_content[end_idx:]
    
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(new_html_content)
    print('Successfully moved CSS.')
else:
    print('Could not find <style> tags.')
