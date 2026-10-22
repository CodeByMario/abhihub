"""
Centralized 301 Redirect Table for AbhiHub URL Standardization.
Maintains SEO equity and prevents broken bookmarks when consolidating legacy URLs.
"""

from flask import Blueprint, redirect, request

redirects_bp = Blueprint('redirects', __name__)

# Static exact-path 301 redirects map: old_path -> new_path
STATIC_REDIRECTS = {
    # 2.2 Support & Tea donations (Redirected to dashboard)
    '/buy-me-tea': '/dashboard',
    '/buy-tea': '/dashboard',
    '/support': '/dashboard',
    '/earn-with-abhihub': '/contribute',

    # 2.3 Legal / Copyright
    '/copyright': '/dmca',

    # 2.4 Settings aliases
    '/setting': '/settings',
    '/dashboard/setting': '/settings',
    '/dashboard/about': '/about',

    # 2.6 Profile aliases
    '/dashboard/profile': '/profile',
    '/dashboard/profile/old': '/profile',
    '/account': '/profile',
    '/account/delete': '/delete-account',

    # 2.7 AI legacy routes
    '/ai': '/dashboard',
    '/ai/embed': '/dashboard',
    '/ai/setup': '/dashboard',

    # Auth & General legacy
    '/register': '/signup',
    '/show_rank': '/leaderboard',
    '/dashboard/': '/dashboard',
    '/pyq_landing': '/college',
    '/pyq': '/college',

    # Phase 4.2 Naming cleanups
    '/UHV': '/uhv',
    '/abhijeetupdate': '/admin',
}

def register_redirect_handlers(app):
    """Register all centralized redirects on the main Flask application."""
    for old_path, new_path in STATIC_REDIRECTS.items():
        endpoint_name = f"redirect_{old_path.replace('/', '_').strip('_')}"
        
        # Helper factory to capture target in closure
        def make_redirect_view(target):
            def redirect_view():
                # Preserve query string if present
                qs = request.query_string.decode('utf-8', errors='ignore')
                dest = f"{target}?{qs}" if qs else target
                return redirect(dest, code=301)
            return redirect_view

        # Avoid overriding already configured endpoints if route is exact duplicate
        if old_path not in [str(rule) for rule in app.url_map.iter_rules()]:
            app.add_url_rule(old_path, endpoint_name, make_redirect_view(new_path))

    # Dynamic parameterized redirects
    if '/prepair/<path:subject>' not in [str(rule) for rule in app.url_map.iter_rules()]:
        def redirect_prepair(subject):
            return redirect(f"/prepare/{subject}", code=301)
        app.add_url_rule('/prepair/<path:subject>', 'redirect_prepair', redirect_prepair)
