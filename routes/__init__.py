"""
AbhiHub modular routes package.
"""
from .site import site_bp
from .auth import auth_bp
from .library import library_bp
from .app_pages import app_pages_bp
from .api import api_bp
from .admin import admin_bp
from .webhooks import webhooks_bp
from .seo import seo_bp
from .store_room import store_room_bp
from .payments import payments_bp
from .ai import ai_bp
from .channels import channels_bp

def register_blueprints(app):
    """Register all modular route blueprints."""
    app.register_blueprint(seo_bp)
    app.register_blueprint(site_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(library_bp)
    app.register_blueprint(app_pages_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(webhooks_bp)
    app.register_blueprint(store_room_bp)
    app.register_blueprint(payments_bp)
    app.register_blueprint(ai_bp)
    app.register_blueprint(channels_bp)
