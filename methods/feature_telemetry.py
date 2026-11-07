"""
Feature Usage and Granular Telemetry Tracker.
Captures user actions, device specifications, network telemetry, and geo location.
Persists to security_audit_logs with non-blocking async execution and in-memory aggregation.
"""

import logging
import threading
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional
from methods.wallet_service import _get_client


def _extract_network_and_geo(req) -> Dict[str, Any]:
    """Extracts client IP, proxy headers, geo-location, and Cloudflare network data."""
    if not req:
        return {}
    
    headers = req.headers
    ip = (
        headers.get('CF-Connecting-IP') or
        headers.get('X-Forwarded-For', '').split(',')[0].strip() or
        req.remote_addr or
        '127.0.0.1'
    )
    
    country = headers.get('CF-IPCountry') or headers.get('X-Geo-Country') or 'Unknown'
    city = headers.get('CF-IPCity') or headers.get('X-Geo-City') or ''
    region = headers.get('CF-IPRegion') or headers.get('X-Geo-Region') or ''
    asn = headers.get('CF-Connecting-ASN') or ''
    
    return {
        'ip': ip,
        'country': country,
        'city': city,
        'region': region,
        'asn': asn,
        'user_agent': headers.get('User-Agent', '')[:250]
    }


def log_feature_event(
    user_id: Optional[str],
    feature: str,
    action: str = 'view',
    device_info: Optional[Dict[str, Any]] = None,
    network_info: Optional[Dict[str, Any]] = None,
    path: str = '/',
    metadata: Optional[Dict[str, Any]] = None,
    req: Any = None
) -> bool:
    """
    Records a feature usage action with device, network, and geo details.
    Runs asynchronously via daemon thread to keep request-response time near 0ms.
    """
    net_geo = _extract_network_and_geo(req)
    combined_network = {**net_geo, **(network_info or {})}
    
    payload = {
        'category': 'feature_usage',
        'feature': str(feature or 'general'),
        'action': str(action or 'interact'),
        'path': str(path or '/'),
        'device': device_info or {},
        'network': combined_network,
        'params': metadata or {},
        'recorded_at': datetime.now(timezone.utc).isoformat()
    }
    
    event_name = f"feature:{feature}"[:60]
    client_ip = combined_network.get('ip', '127.0.0.1')
    user_agent = combined_network.get('user_agent', '')

    def _persist():
        try:
            client = _get_client()
            if not client:
                return
            record = {
                'user_id': user_id if (user_id and len(str(user_id)) == 36) else None,
                'event': event_name,
                'ip_address': client_ip,
                'user_agent': user_agent,
                'metadata': payload,
                'detected_at': datetime.now(timezone.utc).isoformat()
            }
            client.table('security_audit_logs').insert(record).execute()
        except Exception as e:
            logging.debug("[TELEMETRY] Non-blocking log insert skipped (error=%s)", e)

    threading.Thread(target=_persist, daemon=True).start()
    return True


def get_feature_analytics_summary(days: int = 30) -> Dict[str, Any]:
    """Aggregates feature usage, device split, network stats, and user journeys from security_audit_logs."""
    client = _get_client()
    if not client:
        return {'features': {}, 'devices': {}, 'networks': {}, 'locations': {}, 'recent': [], 'total_events': 0}
    
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    try:
        res = client.table('security_audit_logs') \
            .select('user_id, event, ip_address, user_agent, metadata, detected_at') \
            .ilike('event', 'feature:%') \
            .gte('detected_at', since) \
            .order('detected_at', desc=True) \
            .limit(1000) \
            .execute()
        
        events = res.data or []
        features_counter = {}
        devices_counter = {}
        networks_counter = {}
        locations_counter = {}
        recent_feed = []

        for row in events:
            ev = row.get('event', '').replace('feature:', '')
            features_counter[ev] = features_counter.get(ev, 0) + 1
            meta = row.get('metadata') or {}
            
            dev_obj = meta.get('device') or {}
            dev_type = dev_obj.get('type') or 'unknown'
            dev_os = dev_obj.get('os') or ''
            dev_key = f"{dev_os} ({dev_type})" if dev_os else dev_type
            devices_counter[dev_key] = devices_counter.get(dev_key, 0) + 1
            
            net_obj = meta.get('network') or {}
            net_type = net_obj.get('effective_type') or 'unknown'
            networks_counter[net_type] = networks_counter.get(net_type, 0) + 1

            country = net_obj.get('country') or 'Unknown'
            city = net_obj.get('city') or ''
            loc_key = f"{city}, {country}".strip(', ') if city else country
            locations_counter[loc_key] = locations_counter.get(loc_key, 0) + 1
            
            if len(recent_feed) < 35:
                recent_feed.append({
                    'user_id': row.get('user_id') or 'Anonymous',
                    'feature': ev,
                    'action': meta.get('action', 'interact'),
                    'path': meta.get('path', '/'),
                    'device': f"{dev_os} • {dev_obj.get('browser', '')}".strip(' •') or dev_type,
                    'network': f"{net_type.upper()}{' (' + str(net_obj.get('rtt')) + 'ms)' if net_obj.get('rtt') else ''}",
                    'geo': loc_key,
                    'ip': row.get('ip_address') or '127.0.0.1',
                    'time': row.get('detected_at')
                })

        return {
            'features': dict(sorted(features_counter.items(), key=lambda x: x[1], reverse=True)),
            'devices': dict(sorted(devices_counter.items(), key=lambda x: x[1], reverse=True)),
            'networks': dict(sorted(networks_counter.items(), key=lambda x: x[1], reverse=True)),
            'locations': dict(sorted(locations_counter.items(), key=lambda x: x[1], reverse=True)),
            'recent': recent_feed,
            'total_events': len(events)
        }
    except Exception as e:
        logging.error("[TELEMETRY] Analytics summary failed: %s", e)
        return {'features': {}, 'devices': {}, 'networks': {}, 'locations': {}, 'recent': [], 'total_events': 0}
