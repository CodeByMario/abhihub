"""
Patch routes/app_pages.py and templates/delete_account.html for account deletion form handling.
"""
import os

pages_path = os.path.join('routes', 'app_pages.py')
with open(pages_path, 'r', encoding='utf-8') as f:
    content = f.read()

target = """@app_pages_bp.route('/delete-account')
@auth_required
def delete_account():
    \"\"\"Account deletion request page\"\"\"
    return render_template('delete_account.html')"""

replacement = """@app_pages_bp.route('/delete-account', methods=['GET', 'POST'])
def delete_account():
    \"\"\"Account deletion request page and form submission handler.\"\"\"
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip()
        username = request.form.get('username', '').strip()
        reason = request.form.get('reason', '').strip()
        details = request.form.get('details', '').strip()
        confirm = request.form.get('confirm_deletion')

        if not confirm or not email:
            flash('Please confirm deletion and provide an email.', 'error')
            return render_template('delete_account.html'), 400

        import json, datetime
        from datetime import timezone
        req_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'account_deletion_requests.json')
        existing = []
        if os.path.exists(req_file):
            try:
                with open(req_file, 'r', encoding='utf-8') as fh:
                    existing = json.load(fh)
            except Exception:
                existing = []

        record = {
            'full_name': full_name,
            'email': email,
            'username': username,
            'reason': reason,
            'details': details,
            'created_at': datetime.datetime.now(timezone.utc).isoformat()
        }
        existing.append(record)
        os.makedirs(os.path.dirname(req_file), exist_ok=True)
        with open(req_file, 'w', encoding='utf-8') as fh:
            json.dump(existing, fh, indent=2)

        flash('Request received. Our team will verify and process your deletion request.', 'success')
        return render_template('delete_account.html', success=True), 200

    return render_template('delete_account.html')"""

if target in content:
    content = content.replace(target, replacement, 1)
    with open(pages_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Patched delete_account in routes/app_pages.py")
else:
    print("Target not found in routes/app_pages.py")

tmpl_path = os.path.join('templates', 'delete_account.html')
with open(tmpl_path, 'r', encoding='utf-8') as f:
    tmpl = f.read()

target_tmpl = """  <div class="del-card">
    <div class="del-icon">🗑️</div>"""

replacement_tmpl = """  <div class="del-card">
    {% if success %}
    <div class="alert alert-success" style="padding: 1rem 1.25rem; background: #ecfdf5; border: 1px solid #a7f3d0; border-radius: 12px; color: #065f46; margin-bottom: 1.5rem; font-weight: 700;">
      ✓ Request received. Our team will verify and process your deletion request.
    </div>
    {% endif %}
    <div class="del-icon">🗑️</div>"""

if target_tmpl in tmpl:
    tmpl = tmpl.replace(target_tmpl, replacement_tmpl, 1)
    with open(tmpl_path, 'w', encoding='utf-8') as f:
        f.write(tmpl)
    print("Patched templates/delete_account.html")
