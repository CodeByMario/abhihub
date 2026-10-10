"""
tarika_agent_memory.py — Partitioned cognitive memory and goal-tracking for Tarika AI.

Partitions:
- goal: target objective
- completed_summary: high-level summary of finished work
- remaining: list of remaining sub-tasks
- next_action: immediate next step
- status: 'in_progress' | 'completed' | 'paused'
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional
from methods.supabase_helper import init_supabase

log = logging.getLogger(__name__)

ALL_SECTIONS = ("goal", "completed_summary", "remaining", "next_action", "status", "step_count")


def get_or_create_goal_state(
    user_id: str,
    goal: str,
    conversation_id: Optional[str] = None,
    max_steps: int = 5
) -> Dict[str, Any]:
    """Retrieve existing active goal state or initialize a new partitioned memory record."""
    client = init_supabase()
    if not client:
        return {}
    try:
        # Check active in_progress goal for conversation or user
        query = client.table("tarika_agent_state").select("*").eq("user_id", user_id).eq("status", "in_progress")
        if conversation_id:
            query = query.eq("conversation_id", conversation_id)
        res = query.order("created_at", desc=True).limit(1).execute()
        if res.data:
            return res.data[0]

        # Initialize fresh state
        new_row = {
            "user_id": user_id,
            "conversation_id": conversation_id,
            "goal": goal.strip(),
            "completed_summary": "Goal initialized.",
            "remaining": ["Plan execution", "Execute primary work", "Verify results"],
            "next_action": "Plan execution",
            "status": "in_progress",
            "step_count": 0,
            "max_steps": max_steps
        }
        ins = client.table("tarika_agent_state").insert(new_row).execute()
        return ins.data[0] if ins.data else new_row
    except Exception as exc:
        log.warning("[tarika_agent_memory] get_or_create_goal_state error: %s", exc)
        return {}


def get_partitioned_memory(
    state_id: str,
    sections: Optional[List[str]] = None
) -> Dict[str, Any]:
    """Fetch only requested memory partitions to minimize token overhead."""
    client = init_supabase()
    if not client:
        return {}
    try:
        res = client.table("tarika_agent_state").select("*").eq("id", state_id).limit(1).execute()
        if not res.data:
            return {}
        full_record = res.data[0]
        if not sections:
            return full_record

        # Return only the requested keys
        return {k: full_record.get(k) for k in sections if k in full_record}
    except Exception as exc:
        log.warning("[tarika_agent_memory] get_partitioned_memory error: %s", exc)
        return {}


def update_partitioned_memory(
    state_id: str,
    completed_summary: Optional[str] = None,
    remaining: Optional[List[str]] = None,
    next_action: Optional[str] = None,
    status: Optional[str] = None,
    step_inc: bool = True
) -> Dict[str, Any]:
    """Persist updates to memory partitions."""
    client = init_supabase()
    if not client:
        return {}
    try:
        patch: Dict[str, Any] = {}
        if completed_summary is not None:
            patch["completed_summary"] = completed_summary
        if remaining is not None:
            patch["remaining"] = remaining
        if next_action is not None:
            patch["next_action"] = next_action
        if status is not None:
            patch["status"] = status

        if step_inc:
            cur = client.table("tarika_agent_state").select("step_count, max_steps").eq("id", state_id).limit(1).execute()
            if cur.data:
                cnt = (cur.data[0].get("step_count") or 0) + 1
                patch["step_count"] = cnt
                max_s = cur.data[0].get("max_steps") or 5
                if cnt >= max_s and patch.get("status") != "completed":
                    patch["status"] = "paused"

        res = client.table("tarika_agent_state").update(patch).eq("id", state_id).execute()
        return res.data[0] if res.data else patch
    except Exception as exc:
        log.warning("[tarika_agent_memory] update_partitioned_memory error: %s", exc)
        return {}


def format_memory_prompt(partition: Dict[str, Any]) -> str:
    """Format partition memory into high-density Markdown for AI model context."""
    lines = ["### [Tarika Cognitive State]"]
    if "goal" in partition:
        lines.append(f"- **Current Goal:** {partition['goal']}")
    if "completed_summary" in partition and partition["completed_summary"]:
        lines.append(f"- **Completed Summary:** {partition['completed_summary']}")
    if "remaining" in partition and partition["remaining"]:
        rem_str = ", ".join(partition["remaining"]) if isinstance(partition["remaining"], list) else str(partition["remaining"])
        lines.append(f"- **Remaining Items:** {rem_str}")
    if "next_action" in partition and partition["next_action"]:
        lines.append(f"- **Immediate Action:** {partition['next_action']}")
    if "step_count" in partition:
        lines.append(f"- **Step:** {partition.get('step_count', 0)}")
    return "\n".join(lines)


def run_goal_loop(
    state_id: str,
    step_worker_fn: Callable[[Dict[str, Any]], Dict[str, Any]],
    max_turns: int = 3
) -> Dict[str, Any]:
    """Execute iterative steps until goal status is 'completed' or turn limit reached."""
    current_state = get_partitioned_memory(state_id)
    turns = 0

    while current_state.get("status") == "in_progress" and turns < max_turns:
        turns += 1
        step_result = step_worker_fn(current_state)
        new_status = step_result.get("status") or ("completed" if not step_result.get("remaining") else "in_progress")

        current_state = update_partitioned_memory(
            state_id=state_id,
            completed_summary=step_result.get("completed_summary"),
            remaining=step_result.get("remaining"),
            next_action=step_result.get("next_action"),
            status=new_status,
            step_inc=True
        )

    return current_state


def save_generated_exam(
    user_id: Optional[str],
    user_email: Optional[str],
    doc_id: Optional[str],
    doc_title: Optional[str],
    text: str,
    model_used: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Two-phase exam persistence:
    Phase 1 — Save exam header to ai_practice_tests → get test_id.
    Phase 2 — Save each question individually to ai_practice_questions with
               keywords + sample answer enrichment, one row at a time.

    Returns the test header row if successful, None if no valid exam found.
    """
    import json
    import re

    # ── Extract exam_stimulus JSON block from model output ─────────────────────
    match = re.search(r'```(?:exam_stimulus|json)?\s*(\{[\s\S]*?"questions"[\s\S]*?)(?:```|$)', text, re.IGNORECASE)
    raw_json = match.group(1).strip() if match else None

    if not raw_json:
        match2 = re.search(r'(\{[\s\S]*?"questions"\s*:\s*\[[\s\S]*\]\s*\})', text)
        if match2:
            raw_json = match2.group(1).strip()

    if not raw_json:
        return None

    # ── Parse JSON — repair common truncation suffixes if needed ───────────────
    parsed = None
    try:
        parsed = json.loads(raw_json)
    except Exception:
        for suffix in (']}', '"}', '"}]}', '"]}', '"}]}'):
            try:
                parsed = json.loads(raw_json + suffix)
                break
            except Exception:
                continue

    if not parsed or not isinstance(parsed, dict) or not isinstance(parsed.get("questions"), list):
        return None

    raw_questions: list = parsed.get("questions", [])
    if not raw_questions:
        return None

    # ── Enrich each question: guarantee keywords + sample/model answer ─────────
    clean_questions: list = []
    total_marks: int = 0

    for idx, q in enumerate(raw_questions, 1):
        if not isinstance(q, dict):
            continue

        q_type  = (q.get("type") or "mcq").lower().strip()
        q_marks = int(q.get("marks") or (1 if q_type == "one_word" else 2))
        total_marks += q_marks

        # Build keyword list from correct_answer / model_answer / explanation
        keywords = q.get("keywords")
        if not keywords or not isinstance(keywords, list):
            sample_src = " ".join(filter(None, [
                str(q.get("correct_answer") or ""),
                str(q.get("model_answer")   or ""),
                str(q.get("explanation")    or ""),
            ]))
            words    = [w.strip() for w in re.findall(r'\b[a-zA-Z][a-zA-Z0-9_]{3,}\b', sample_src)]
            keywords = list(dict.fromkeys(words))[:5] or ["core_concept"]

        cq: Dict[str, Any] = {
            "id":          q.get("id") or idx,
            "type":        q_type,
            "question":    (q.get("question") or f"Question {idx}").strip(),
            "marks":       q_marks,
            "keywords":    keywords,
            "explanation": (q.get("explanation") or "Step-by-step solution provided.").strip(),
        }
        if "options" in q and isinstance(q["options"], list):
            cq["options"] = q["options"]
        if "correct_answer" in q:
            cq["correct_answer"] = q["correct_answer"]
        if "correct_options" in q:
            cq["correct_options"] = q["correct_options"]
        if "model_answer" in q:
            cq["model_answer"] = q["model_answer"]
        elif q_type in ("short", "detail", "one_word") and "correct_answer" not in cq:
            cq["model_answer"] = (q.get("explanation") or "Sample answer.").strip()

        clean_questions.append(cq)

    if not clean_questions:
        return None

    title   = (parsed.get("title") or (f"Practice Test: {doc_title}" if doc_title else "Practice Exam")).strip()
    subject = doc_title or parsed.get("subject") or "General"

    client = init_supabase()
    if not client:
        return None

    # ── Phase 1: Save exam header ──────────────────────────────────────────────
    header_row: Dict[str, Any] = {
        "creator_user_id": user_id     or "anonymous",
        "creator_email":   user_email  or "anonymous@abhihub.local",
        "doc_id":          doc_id      or None,
        "title":           title,
        "subject":         subject,
        "total_questions": len(clean_questions),
        "total_marks":     total_marks,
        "questions":       clean_questions,   # keep JSONB copy for fast access
        "model_used":      model_used  or "unknown",
        "is_public":       True,
    }
    try:
        header_res = client.table("ai_practice_tests").insert(header_row).execute()
        test_id    = (header_res.data or [{}])[0].get("id")
        header_row = (header_res.data or [header_row])[0]
        log.info("[tarika_agent_memory] Phase 1 ✓ — exam header saved (test_id=%s, %d questions)", test_id, len(clean_questions))
    except Exception as exc:
        log.warning("[tarika_agent_memory] Phase 1 ✗ — header insert failed: %s", exc)
        return None

    if not test_id:
        log.warning("[tarika_agent_memory] Phase 1 — no test_id returned, skipping Phase 2")
        return header_row

    # ── Phase 2: Save each question individually ───────────────────────────────
    saved_count = 0
    failed_count = 0

    for q in clean_questions:
        q_row: Dict[str, Any] = {
            "test_id":        test_id,
            "question_no":    int(q.get("id") or 1),
            "question_type":  q.get("type",  "mcq"),
            "question_text":  q.get("question", ""),
            "marks":          q.get("marks", 1),
            "keywords":       q.get("keywords", []),
            "explanation":    q.get("explanation", ""),
            "subject":        subject,
            "doc_id":         doc_id or None,
            "creator_user_id": user_id or "anonymous",
        }
        # Type-specific fields
        if "options" in q:
            q_row["options"] = q["options"]
        if "correct_answer" in q:
            q_row["correct_answer"] = str(q["correct_answer"])
        if "correct_options" in q:
            q_row["correct_options"] = q["correct_options"]
        if "model_answer" in q:
            q_row["model_answer"] = str(q["model_answer"])

        try:
            client.table("ai_practice_questions").insert(q_row).execute()
            saved_count += 1
        except Exception as q_exc:
            failed_count += 1
            log.warning(
                "[tarika_agent_memory] Phase 2 ✗ — Q%s save failed: %s",
                q.get("id"), q_exc
            )

    log.info(
        "[tarika_agent_memory] Phase 2 ✓ — %d/%d questions saved individually (test_id=%s)",
        saved_count, len(clean_questions), test_id
    )

    return header_row
