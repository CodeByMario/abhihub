"""
Admin analytics dashboard API endpoints.
Requires admin authentication (uses @admin_required decorator).
"""

import logging
from flask import request, jsonify, session

def register_reporter_routes(app):
    """Register admin analytics dashboard API endpoints."""
    
    @app.route('/api/admin/analytics/overview', methods=['GET'])
    def api_admin_analytics_overview():
        """Return overview KPIs for the analytics dashboard."""
        from methods.analytics_reporter import get_overview_kpis
        
        days = min(int(request.args.get('days', 30)), 365)
        result = get_overview_kpis(days=days)
        return jsonify(result), 200 if result.get('success') else 500
    
    @app.route('/api/admin/analytics/trending-files', methods=['GET'])
    def api_admin_trending_files():
        """Return most viewed files."""
        from methods.analytics_reporter import get_trending_files
        
        days = min(int(request.args.get('days', 30)), 365)
        limit = min(int(request.args.get('limit', 20)), 100)
        result = get_trending_files(days=days, limit=limit)
        return jsonify(result), 200 if result.get('success') else 500
    
    @app.route('/api/admin/analytics/demographics', methods=['GET'])
    def api_admin_demographics():
        """Return user demographics breakdown."""
        from methods.analytics_reporter import get_user_demographics
        
        days = min(int(request.args.get('days', 30)), 365)
        result = get_user_demographics(days=days)
        return jsonify(result), 200 if result.get('success') else 500
    
    @app.route('/api/admin/analytics/usage-patterns', methods=['GET'])
    def api_admin_usage_patterns():
        """Return hourly/daily usage patterns."""
        from methods.analytics_reporter import get_usage_patterns
        
        days = min(int(request.args.get('days', 30)), 365)
        result = get_usage_patterns(days=days)
        return jsonify(result), 200 if result.get('success') else 500
    
    @app.route('/api/admin/analytics/traffic-sources', methods=['GET'])
    def api_admin_traffic_sources():
        """Return top referrer URLs."""
        from methods.analytics_reporter import get_traffic_sources
        
        days = min(int(request.args.get('days', 30)), 365)
        limit = min(int(request.args.get('limit', 15)), 50)
        result = get_traffic_sources(days=days, limit=limit)
        return jsonify(result), 200 if result.get('success') else 500
    
    @app.route('/api/admin/analytics/devices', methods=['GET'])
    def api_admin_devices():
        """Return device type distribution."""
        from methods.analytics_reporter import get_device_breakdown
        
        days = min(int(request.args.get('days', 30)), 365)
        result = get_device_breakdown(days=days)
        return jsonify(result), 200 if result.get('success') else 500
    
    @app.route('/api/admin/analytics/recent-activity', methods=['GET'])
    def api_admin_recent_activity():
        """Return recent file view activity feed."""
        from methods.analytics_reporter import get_recent_activity
        
        limit = min(int(request.args.get('limit', 50)), 200)
        result = get_recent_activity(limit=limit)
        return jsonify(result), 200 if result.get('success') else 500
    
    @app.route('/api/admin/analytics/trending-subjects', methods=['GET'])
    def api_admin_trending_subjects():
        """Return most viewed subjects."""
        from methods.analytics_reporter import get_trending_subjects
        
        days = min(int(request.args.get('days', 30)), 365)
        limit = min(int(request.args.get('limit', 15)), 50)
        result = get_trending_subjects(days=days, limit=limit)
        return jsonify(result), 200 if result.get('success') else 500
    
    @app.route('/api/admin/analytics/errors', methods=['GET'])
    def api_admin_errors():
        """Return recent errors."""
        from methods.analytics_reporter import get_error_summary
        
        days = min(int(request.args.get('days', 7)), 30)
        limit = min(int(request.args.get('limit', 20)), 100)
        result = get_error_summary(days=days, limit=limit)
        return jsonify(result), 200 if result.get('success') else 500
    
    @app.route('/api/admin/analytics/daily-views', methods=['GET'])
    def api_admin_daily_views():
        """Return daily view counts for chart."""
        from methods.analytics_reporter import get_daily_views
        
        days = min(int(request.args.get('days', 30)), 365)
        result = get_daily_views(days=days)
        return jsonify(result), 200 if result.get('success') else 500
