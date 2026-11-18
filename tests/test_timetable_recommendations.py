"""
Unit tests for Timetable Recommendation Service and Demand Forecast Engine.
Tests Asia/Kolkata timezone handling, exam ranking algorithms, category matching,
and demand score calculations.
"""
import pytest
from datetime import datetime, date, timedelta
import zoneinfo

from services.recommendation_service import (
    KOLKATA_TZ,
    get_current_kolkata_date,
    calculate_file_exam_match_score
)
from services.demand_service import KOLKATA_TZ as DEMAND_TZ

def test_kolkata_timezone():
    """Verify system operates under Asia/Kolkata timezone."""
    now_kolkata = get_current_kolkata_date()
    assert now_kolkata.tzinfo.key == "Asia/Kolkata"
    assert DEMAND_TZ.key == "Asia/Kolkata"

def test_exam_proximity_ranking():
    """Verify closer exams receive higher priority weighting."""
    doc = {
        'id': 'doc-1',
        'title': 'Data Structures Lecture Notes',
        'document_category': 'notes',
        'file_type': 'pdf',
        'like_count': 5,
        'view_count': 100
    }
    
    exam_today = {'exam_type': 'THEORY', 'days_until_exam': 0}
    exam_3_days = {'exam_type': 'THEORY', 'days_until_exam': 3}
    exam_14_days = {'exam_type': 'THEORY', 'days_until_exam': 14}
    exam_30_days = {'exam_type': 'THEORY', 'days_until_exam': 30}

    score_today = calculate_file_exam_match_score(doc, exam_today)
    score_3 = calculate_file_exam_match_score(doc, exam_3_days)
    score_14 = calculate_file_exam_match_score(doc, exam_14_days)
    score_30 = calculate_file_exam_match_score(doc, exam_30_days)

    assert score_today > score_3 > score_14 > score_30

def test_exam_type_alignment():
    """Verify practical exams prioritize lab manuals and theory exams prioritize notes/papers."""
    exam_practical = {'exam_type': 'PRACTICAL', 'days_until_exam': 5}
    exam_theory = {'exam_type': 'THEORY', 'days_until_exam': 5}

    lab_manual = {
        'id': 'doc-lab',
        'title': 'Data Structures Lab Manual & Viva Questions',
        'document_category': 'practical',
        'like_count': 2,
        'view_count': 10
    }

    theory_paper = {
        'id': 'doc-paper',
        'title': 'Solved Previous Year Question Papers',
        'document_category': 'papers',
        'like_count': 2,
        'view_count': 10
    }

    # For practical exam, lab manual scores higher than theory paper
    assert calculate_file_exam_match_score(lab_manual, exam_practical) > calculate_file_exam_match_score(theory_paper, exam_practical)

    # For theory exam, theory paper scores higher than lab manual
    assert calculate_file_exam_match_score(theory_paper, exam_theory) > calculate_file_exam_match_score(lab_manual, exam_theory)

def test_quality_weighting():
    """Verify likes and views increase file score."""
    exam = {'exam_type': 'THEORY', 'days_until_exam': 7}

    doc_low_quality = {
        'id': 'doc-low',
        'title': 'Notes',
        'document_category': 'notes',
        'like_count': 0,
        'view_count': 2
    }

    doc_high_quality = {
        'id': 'doc-high',
        'title': 'Notes',
        'document_category': 'notes',
        'like_count': 15,
        'view_count': 500
    }

    score_low = calculate_file_exam_match_score(doc_low_quality, exam)
    score_high = calculate_file_exam_match_score(doc_high_quality, exam)

    assert score_high > score_low

def test_pyq_over_notes_and_recency():
    """Verify PYQs rank above notes, and recent years rank first."""
    exam = {'exam_type': 'THEORY', 'days_until_exam': 5}

    pyq_2026 = {
        'id': 'doc-pyq-2026',
        'title': 'Data Structures 2026 ESE Question Paper PYQ',
        'document_category': 'papers',
        'created_at': '2026-11-01T10:00:00Z'
    }
    pyq_2024 = {
        'id': 'doc-pyq-2024',
        'title': 'Data Structures 2024 Question Paper PYQ',
        'document_category': 'papers',
        'created_at': '2024-11-01T10:00:00Z'
    }
    notes_2026 = {
        'id': 'doc-notes-2026',
        'title': 'Data Structures 2026 Topper Notes Complete',
        'document_category': 'notes',
        'created_at': '2026-11-01T10:00:00Z'
    }

    score_pyq_2026 = calculate_file_exam_match_score(pyq_2026, exam)
    score_pyq_2024 = calculate_file_exam_match_score(pyq_2024, exam)
    score_notes_2026 = calculate_file_exam_match_score(notes_2026, exam)

    # 1. 2026 PYQ scores higher than 2024 PYQ (recent first)
    assert score_pyq_2026 > score_pyq_2024
    # 2. PYQ scores higher than Notes (PYQ first, then notes)
    assert score_pyq_2026 > score_notes_2026
