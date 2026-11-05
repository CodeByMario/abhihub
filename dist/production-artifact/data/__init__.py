"""
data — Supabase models for the abhihub schema.

Usage:
    from data import College, Document, Profile
    colleges = College.get_all()
"""

from data.db import get_client, validate_uuid, format_file_size

from data.colleges import College, Department, Subject
from data.profiles import Profile, Student, Teacher, UserSession
from data.documents import Document
from data.interactions import Bookmark, Comment, Vote
from data.analytics import DocumentView, SecurityAuditLog
from data.notifications import Notification, PushSubscription

__all__ = [
    # client
    "get_client",
    "validate_uuid",
    "format_file_size",
    # hierarchy
    "College",
    "Department",
    "Subject",
    # users
    "Profile",
    "Student",
    "Teacher",
    "UserSession",
    # documents
    "Document",
    # interactions
    "Bookmark",
    "Comment",
    "Vote",
    # analytics
    "DocumentView",
    "SecurityAuditLog",
    # notifications
    "Notification",
    "PushSubscription",
]
