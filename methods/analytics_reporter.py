"""
Analytics Reporter Module for AbhiHub Admin Dashboard.

Provides comprehensive insights by querying Supabase tables:
- document_views: pageviews, file views, time spent
- user_sessions: session duration, device breakdown
- security_audit_logs: error tracking
- documents: file metadata, upload info
- profiles/students: user demographics (college, branch, year)

All queries use the abhihub schema via supabase helper.
"""

import logging
from datetime import datetime, timedelta
from collections import Counter

# ============================================================================
# Internal helpers
# ============================================================================

def _client():
    """Get Supabase client (abhihub schema)."""
    try:
        from methods.supabase_helper import init_supabase
        return init_supabase()
    except Exception as e:
        logging.error(f"[Reporter] Supabase init failed: {e}")
        return None


def _safe_ts(col="accessed_at"):
    """Return ISO timestamp for 30 days ago."""
    return (datetime.utcnow() - timedelta(days=30)).isoformat() + "Z"


def _safe_ts_days(days=30):
    return (datetime.utcnow() - timedelta(days=days)).isoformat() + "Z"


# ============================================================================
# 1. OVERVIEW KPIs
# ============================================================================

def get_overview_kpis(days=30):
    """Return top-level KPIs: total views, unique users, sessions, avg duration."""
    client = _client()
    if not None in (client,):
        pass
    if not client:
        return {"success": False, "data": None}
    
    try:
        since = _safe_ts_days(days)
        
        # Total pageviews
        pv_res = client.table('document_views').select('*', count='exact').gte('accessed_at', since).execute()
        total_views = pv_res.count if hasattr(pv_res, 'count') and pv_res.count else len(pv_res.data or [])
        
        # Total file views (excluding pageviews)
        fv_res = client.table('document_views').select('user_id', count='exact').gte('accessed_at', since).eq('view_type', 'view').execute()
        file_views_count = fv_res.count if hasattr(fv_res, 'count') and fv_res.count else len(fv_res.data or [])
        
        # Unique users
        unique_res = client.table('document_views').select('user_id').gte('accessed_at', since).execute()
        unique_user_ids = set(r['user_id'] for r in (unique_res.data or []) if r.get('user_id'))
        unique_users = len(unique_user_ids)
        
        # Total sessions from user_sessions
        sess_res = client.table('user_sessions').select('*', count='exact').gte('login_time', since).execute()
        total_sessions = sess_res.count if hasattr(sess_res, 'count') and sess_res.count else len(sess_res.data or [])
        
        # Average session duration
        durations = [s.get('duration_minutes', 0) or 0 for s in (sess_res.data or [])]
        avg_duration = round(sum(durations) / len(durations), 1) if durations else 0
        
        # Avg time on file (from document_views metadata)
        time_res = client.table('document_views').select('time_spent_seconds').gte('accessed_at', since).execute()
        times = [r.get('time_spent_seconds', 0) or 0 for r in (time_res.data or [])]
        avg_time_on_file = round(sum(times) / len(times), 1) if times else 0
        
        return {
            "success": True,
            "data": {
                "total_views": total_views,
                "file_views": file_views_count,
                "unique_users": unique_users,
                "total_sessions": total_sessions,
                "avg_session_minutes": avg_duration,
                "avg_time_on_file_seconds": avg_time_on_file,
                "period_days": days,
                "generated_at": datetime.utcnow().isoformat() + "Z"
            }
        }
    except Exception as e:
        logging.error(f"[Reporter] Overview KPIs error: {e}")
        return {"success": False, "data": None, "message": str(e)}


# ============================================================================
# 2. TRENDING FILES
# ============================================================================

def get_trending_files(days=30, limit=20):
    """Return most viewed files with view count and avg time spent."""
    client = _client()
    if not client:
        return {"success": False, "data": []}
    
    try:
        since = _safe_ts_days(days)
        
        # Get all file views in period
        res = client.table('document_views').select(
            'document_id, time_spent_seconds, accessed_at, user_id, device_type'
        ).gte('accessed_at', since).execute()
        
        views = res.data or []
        
        # Aggregate by document_id
        doc_stats = {}
        for v in views:
            doc_id = v.get('document_id', '')
            if not doc_id:
                continue
            
            if doc_id not in doc_stats:
                doc_stats[doc_id] = {
                    "document_id": doc_id,
                    "view_count": 0,
                    "total_time_seconds": 0,
                    "unique_users": set(),
                    "last_accessed": v.get('accessed_at', '')
                }
            
            doc_stats[doc_id]["view_count"] += 1
            doc_stats[doc_id]["total_time_seconds"] += v.get('time_spent_seconds', 0) or 0
            if v.get('user_id'):
                doc_stats[doc_id]["unique_users"].add(v['user_id'])
            
            # Track latest access
            if v.get('accessed_at', '') > doc_stats[doc_id]["last_accessed"]:
                doc_stats[doc_id]["last_accessed"] = v['accessed_at']
        
        # Fetch document metadata (title, subject, college, type)
        doc_ids = list(doc_stats.keys())
        if doc_ids:
            meta_res = client.table('documents').select(
                'id, title, subject_id, college_id, department_id, file_type, view_count'
            ).in_('id', doc_ids).execute()
            
            # Build lookups
            subjects = {}
            colleges = {}
            departments = {}
            
            for doc in (meta_res.data or []):
                doc_id = doc.get('id')
                if doc_id in doc_stats:
                    doc_stats[doc_id]["title"] = doc.get('title', 'Unknown')
                    doc_stats[doc_id]["file_type"] = doc.get('file_type', '')
                    doc_stats[doc_id]["subject_id"] = doc.get('subject_id', '')
                    doc_stats[doc_id]["college_id"] = doc.get('college_id', '')
                    doc_stats[doc_id]["department_id"] = doc.get('department_id', '')
                    
                    # Track needed metadata lookups
                    if doc.get('subject_id'):
                        subjects[doc['subject_id']] = True
                    if doc.get('college_id'):
                        colleges[doc['college_id']] = True
                    if doc.get('department_id'):
                        departments[doc['department_id']] = True
            
            # Batch fetch subject names
            if subjects:
                subj_res = client.table('subjects').select('id, name').in_('id', list(subjects.keys())).execute()
                for s in (subj_res.data or []):
                    subjects[s['id']] = s.get('name', '')
            
            # Batch fetch college names
            if colleges:
                col_res = client.table('colleges').select('id, name').in_('id', list(colleges.keys())).execute()
                for c in (col_res.data or []):
                    colleges[c['id']] = c.get('name', '')
            
            # Batch fetch department names
            if departments:
                dep_res = client.table('departments').select('id, name').in_('id', list(departments.keys())).execute()
                for d in (dep_res.data or []):
                    departments[d['id']] = d.get('name', '')
        
        # Finalize stats
        result = []
        for doc_id, stats in doc_stats.items():
            avg_time = round(stats["total_time_seconds"] / stats["view_count"], 1) if stats["view_count"] > 0 else 0
            
            # Resolve metadata
            subject_id = stats.get('subject_id', '')
            college_id = stats.get('college_id', '')
            dept_id = stats.get('department_id', '')
            
            result.append({
                "document_id": doc_id,
                "title": stats.get('title', 'Unknown'),
                "file_type": stats.get('file_type', ''),
                "subject": subjects.get(subject_id, '') if isinstance(subjects, dict) else '',
                "college": colleges.get(college_id, '') if isinstance(colleges, dict) else '',
                "department": departments.get(dept_id, '') if isinstance(departments, dict) else '',
                "view_count": stats["view_count"],
                "unique_viewers": len(stats["unique_users"]),
                "avg_time_seconds": avg_time,
                "total_time_minutes": round(stats["total_time_seconds"] / 60, 1),
                "last_accessed": stats["last_accessed"]
            })
        
        # Sort by view count descending
        result.sort(key=lambda x: x["view_count"], reverse=True)
        
        return {
            "success": True,
            "data": result[:limit],
            "period_days": days
        }
    except Exception as e:
        logging.error(f"[Reporter] Trending files error: {e}")
        return {"success": False, "data": [], "message": str(e)}


# ============================================================================
# 3. USER DEMOGRAPHICS
# ============================================================================

def get_user_demographics(days=30):
    """Return user breakdown by college, branch, year of study."""
    client = _client()
    if not client:
        return {"success": False, "data": {}}
    
    try:
        since = _safe_ts_days(days)
        
        # Get unique user IDs from views
        views_res = client.table('document_views').select('user_id').gte('accessed_at', since).execute()
        user_ids = list(set(r['user_id'] for r in (views_res.data or []) if r.get('user_id')))
        
        if not user_ids:
            return {"success": True, "data": {"colleges": [], "branches": [], "years": [], "total": 0}}
        
        # Fetch student profiles for these users
        profiles_res = client.table('students').select(
            'profile_id, pursuing_year, profiles(college_id, department_id)'
        ).in_('profile_id', user_ids).execute()
        
        profiles = profiles_res.data or []
        
        college_counter = Counter()
        branch_counter = Counter()
        year_counter = Counter()
        
        college_ids = set()
        dept_ids = set()
        
        for p in profiles:
            # Year of study
            year = p.get('pursuing_year')
            if year:
                year_counter[f"Year {year}"] += 1
            
            # Profile data is nested
            profile_data = p.get('profiles', {}) or {}
            if profile_data.get('college_id'):
                college_counter[profile_data['college_id']] += 1
                college_ids.add(profile_data['college_id'])
            if profile_data.get('department_id'):
                branch_counter[profile_data['department_id']] += 1
                dept_ids.add(profile_data['department_id'])
        
        # Resolve college names
        if college_ids:
            col_res = client.table('colleges').select('id, name').in_('id', list(college_ids)).execute()
            col_map = {c['id']: c.get('name', '') for c in (col_res.data or [])}
            college_counter_named = Counter()
            for cid, count in college_counter.items():
                name = col_map.get(cid, cid)
                college_counter_named[name] += count
            college_counter = college_counter_named
        
        # Resolve department names
        if dept_ids:
            dep_res = client.table('departments').select('id, name').in_('id', list(dept_ids)).execute()
            dep_map = {d['id']: d.get('name', '') for d in (dep_res.data or [])}
            branch_counter_named = Counter()
            for did, count in branch_counter.items():
                name = dep_map.get(did, did)
                branch_counter_named[name] += count
            branch_counter = branch_counter_named
        
        return {
            "success": True,
            "data": {
                "total_unique_users": len(user_ids),
                "total_with_profiles": len(profiles),
                "colleges": [{"name": k, "count": v} for k, v in college_counter.most_common(10)],
                "branches": [{"name": k, "count": v} for k, v in branch_counter.most_common(10)],
                "years": [{"name": k, "count": v} for k, v in year_counter.most_common()],
                "period_days": days
            }
        }
    except Exception as e:
        logging.error(f"[Reporter] User demographics error: {e}")
        return {"success": False, "data": {}, "message": str(e)}


# ============================================================================
# 4. USAGE PATTERNS (WHEN)
# ============================================================================

def get_usage_patterns(days=30):
    """Return hourly and daily usage patterns."""
    client = _client()
    if not client:
        return {"success": False, "data": {}}
    
    try:
        since = _safe_ts_days(days)
        
        res = client.table('document_views').select('accessed_at').gte('accessed_at', since).execute()
        
        views = res.data or []
        
        # Hour-of-day distribution (0-23)
        hourly = [0] * 24
        # Day-of-week distribution (0=Monday)
        daily = [0] * 7
        
        for v in views:
            ts = v.get('accessed_at', '')
            if not ts:
                continue
            try:
                dt = datetime.fromisoformat(ts.replace('Z', '+00:00').replace('+00:00', ''))
                hourly[dt.hour] += 1
                daily[dt.weekday()] += 1
            except Exception:
                continue
        
        # Format hourly data
        hourly_data = [{"hour": f"{h:02d}:00", "views": c} for h, c in enumerate(hourly)]
        
        # Format daily data
        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        daily_data = [{"day": day_names[i], "views": c} for i, c in enumerate(daily)]
        
        # Peak hour
        peak_hour = max(range(24), key=lambda h: hourly[h])
        
        return {
            "success": True,
            "data": {
                "hourly": hourly_data,
                "daily": daily_data,
                "peak_hour": f"{peak_hour:02d}:00",
                "peak_hour_views": hourly[peak_hour],
                "total_views": len(views),
                "period_days": days
            }
        }
    except Exception as e:
        logging.error(f"[Reporter] Usage patterns error: {e}")
        return {"success": False, "data": {}, "message": str(e)}


# ============================================================================
# 5. TRAFFIC SOURCES (REFERRERS)
# ============================================================================

def get_traffic_sources(days=30, limit=15):
    """Return top referrer URLs."""
    client = _client()
    if not client:
        return {"success": False, "data": []}
    
    try:
        since = _safe_ts_days(days)
        
        res = client.table('document_views').select('metadata').gte('accessed_at', since).execute()
        
        views = res.data or []
        
        referrer_counter = Counter()
        direct_count = 0
        
        for v in views:
            meta = v.get('metadata', {}) or {}
            referrer = meta.get('referrer', '')
            
            if not referrer or referrer == '':
                direct_count += 1
            else:
                # Extract domain
                try:
                    from urllib.parse import urlparse
                    parsed = urlparse(referrer)
                    domain = parsed.netloc or referrer[:50]
                    referrer_counter[domain] += 1
                except Exception:
                    referrer_counter[referrer[:50]] += 1
        
        # Build result
        result = [{"source": "Direct / None", "views": direct_count}]
        for domain, count in referrer_counter.most_common(limit):
            result.append({"source": domain, "views": count})
        
        return {
            "success": True,
            "data": result,
            "period_days": days
        }
    except Exception as e:
        logging.error(f"[Reporter] Traffic sources error: {e}")
        return {"success": False, "data": [], "message": str(e)}


# ============================================================================
# 6. DEVICE BREAKDOWN
# ============================================================================

def get_device_breakdown(days=30):
    """Return device type distribution."""
    client = _client()
    if not client:
        return {"success": False, "data": {}}
    
    try:
        since = _safe_ts_days(days)
        
        res = client.table('document_views').select('device_type').gte('accessed_at', since).execute()
        
        views = res.data or []
        
        device_counter = Counter()
        for v in views:
            device = v.get('device_type', 'unknown') or 'unknown'
            device_counter[device] += 1
        
        total = len(views) or 1
        
        return {
            "success": True,
            "data": {
                "devices": [
                    {"type": k, "count": v, "percentage": round(v / total * 100, 1)}
                    for k, v in device_counter.most_common()
                ],
                "total": len(views),
                "period_days": days
            }
        }
    except Exception as e:
        logging.error(f"[Reporter] Device breakdown error: {e}")
        return {"success": False, "data": {}, "message": str(e)}


# ============================================================================
# 7. RECENT ACTIVITY FEED
# ============================================================================

def get_recent_activity(limit=50):
    """Return most recent file views with user and document info."""
    client = _client()
    if not client:
        return {"success": False, "data": []}
    
    try:
        res = client.table('document_views').select(
            '*, documents(title, file_type)'
        ).order('accessed_at', desc=True).limit(limit).execute()
        
        activities = []
        for v in (res.data or []):
            doc = v.get('documents', {}) or {}
            activities.append({
                "document_id": v.get('document_id', ''),
                "document_title": doc.get('title', 'Unknown'),
                "file_type": doc.get('file_type', ''),
                "user_id": v.get('user_id', ''),
                "device_type": v.get('device_type', 'unknown'),
                "time_spent_seconds": v.get('time_spent_seconds', 0) or 0,
                "accessed_at": v.get('accessed_at', '')
            })
        
        return {
            "success": True,
            "data": activities
        }
    except Exception as e:
        logging.error(f"[Reporter] Recent activity error: {e}")
        return {"success": False, "data": [], "message": str(e)}


# ============================================================================
# 8. TRENDING SUBJECTS
# ============================================================================

def get_trending_subjects(days=30, limit=15):
    """Return most viewed subjects."""
    client = _client()
    if not client:
        return {"success": False, "data": []}
    
    try:
        since = _safe_ts_days(days)
        
        res = client.table('document_views').select('document_id').gte('accessed_at', since).execute()
        
        views = res.data or []
        
        # Get document IDs
        doc_ids = [v['document_id'] for v in views if v.get('document_id')]
        
        if not doc_ids:
            return {"success": True, "data": []}
        
        # Fetch documents with subject info
        docs_res = client.table('documents').select('id, subject_id').in_('id', doc_ids).execute()
        
        subject_counter = Counter()
        for doc in (docs_res.data or []):
            if doc.get('subject_id'):
                subject_counter[doc['subject_id']] += 1
        
        if not subject_counter:
            return {"success": True, "data": []}
        
        # Resolve subject names
        subject_ids = list(subject_counter.keys())
        subj_res = client.table('subjects').select('id, name').in_('id', subject_ids).execute()
        subj_map = {s['id']: s.get('name', '') for s in (subj_res.data or [])}
        
        result = [
            {"subject_id": sid, "name": subj_map.get(sid, sid), "view_count": count}
            for sid, count in subject_counter.most_common(limit)
        ]
        
        return {
            "success": True,
            "data": result,
            "period_days": days
        }
    except Exception as e:
        logging.error(f"[Reporter] Trending subjects error: {e}")
        return {"success": False, "data": [], "message": str(e)}


# ============================================================================
# 9. ERROR SUMMARY
# ============================================================================

def get_error_summary(days=7, limit=20):
    """Return recent errors from security_audit_logs."""
    client = _client()
    if not client:
        return {"success": False, "data": []}
    
    try:
        since = _safe_ts_days(days)
        
        res = client.table('security_audit_logs').select(
            'event, metadata, accessed_at'
        ).gte('accessed_at', since).like('event', '%analytics_error%').order('accessed_at', desc=True).limit(limit).execute()
        
        errors = []
        for e in (res.data or []):
            meta = e.get('metadata', {}) or {}
            errors.append({
                "error_type": e.get('event', '').replace('analytics_error_', ''),
                "error_message": meta.get('error_message', ''),
                "severity": meta.get('severity', 'warning'),
                "page_path": meta.get('page_path', ''),
                "timestamp": e.get('accessed_at', '')
            })
        
        return {
            "success": True,
            "data": errors,
            "period_days": days
        }
    except Exception as e:
        logging.error(f"[Reporter] Error summary: {e}")
        return {"success": False, "data": [], "message": str(e)}


# ============================================================================
# 10. DAILY VIEWS TIME SERIES (for chart)
# ============================================================================

def get_daily_views(days=30):
    """Return daily view counts for time series chart."""
    client = _client()
    if not client:
        return {"success": False, "data": []}
    
    try:
        since = _safe_ts_days(days)
        
        res = client.table('document_views').select('accessed_at').gte('accessed_at', since).execute()
        
        views = res.data or []
        
        # Count by date
        date_counter = Counter()
        for v in views:
            ts = v.get('accessed_at', '')
            if ts:
                date_str = ts[:10]  # YYYY-MM-DD
                date_counter[date_str] += 1
        
        # Fill missing dates with 0
        result = []
        for i in range(days):
            d = (datetime.utcnow() - timedelta(days=days - 1 - i)).strftime('%Y-%m-%d')
            result.append({"date": d, "views": date_counter.get(d, 0)})
        
        return {
            "success": True,
            "data": result,
            "period_days": days
        }
    except Exception as e:
        logging.error(f"[Reporter] Daily views error: {e}")
        return {"success": False, "data": [], "message": str(e)}
