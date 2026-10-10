import pytest
from unittest.mock import MagicMock, patch
from methods.tarika_agent_memory import (
    format_memory_prompt,
    run_goal_loop,
    get_partitioned_memory
)


def test_format_memory_prompt_selective():
    state = {
        "goal": "Prepare 5 MCQs on Operating Systems",
        "completed_summary": "Drafted questions 1-3",
        "remaining": ["Draft question 4", "Draft question 5"],
        "next_action": "Draft question 4"
    }
    prompt = format_memory_prompt(state)
    assert "Prepare 5 MCQs on Operating Systems" in prompt
    assert "Drafted questions 1-3" in prompt
    assert "Draft question 4" in prompt


def test_run_goal_loop_completes_when_remaining_empty():
    initial = {
        "id": "mock-state-id",
        "status": "in_progress",
        "goal": "Test goal",
        "remaining": ["Step 1", "Step 2"]
    }

    def mock_worker(state):
        return {
            "completed_summary": "Finished all",
            "remaining": [],
            "next_action": None,
            "status": "completed"
        }

    with patch("methods.tarika_agent_memory.get_partitioned_memory", return_value=initial), \
         patch("methods.tarika_agent_memory.update_partitioned_memory", return_value={"status": "completed", "remaining": []}):
        final = run_goal_loop("mock-state-id", mock_worker, max_turns=3)
        assert final["status"] == "completed"


def test_save_generated_exam_with_keywords_and_sample_answers():
    from methods.tarika_agent_memory import save_generated_exam

    sample_output = """Here is your practice exam:
```exam_stimulus
{
  "title": "Computer Networks Practice",
  "questions": [
    {
      "id": 1,
      "type": "mcq",
      "question": "Which layer handles routing?",
      "options": ["A) Physical", "B) Network", "C) Transport", "D) Application"],
      "correct_answer": "B) Network",
      "explanation": "Network layer handles routing and IP addressing.",
      "marks": 2
    },
    {
      "id": 2,
      "type": "short",
      "question": "Define throughput.",
      "model_answer": "Actual rate at which data is successfully transferred over communication link.",
      "explanation": "Throughput measures real transmission speed.",
      "marks": 2
    }
  ]
}
```
Good luck!"""

    mock_client = MagicMock()

    # Phase 1: ai_practice_tests insert returns the header with id
    header_mock = MagicMock()
    header_mock.insert.return_value.execute.return_value.data = [{"id": "saved-123", "title": "Computer Networks Practice"}]

    # Phase 2: ai_practice_questions insert returns a simple row
    q_mock = MagicMock()
    q_mock.insert.return_value.execute.return_value.data = [{"id": "q-1"}]

    def table_router(name):
        return header_mock if name == "ai_practice_tests" else q_mock

    mock_client.table.side_effect = table_router

    with patch("methods.tarika_agent_memory.init_supabase", return_value=mock_client):
        res = save_generated_exam("user_1", "u1@example.com", "doc_1", "CN Notes", sample_output, "test-model")

        assert res is not None
        # Phase 1 — header must have been inserted
        assert header_mock.insert.called
        header_args = header_mock.insert.call_args[0][0]
        assert header_args["title"] == "Computer Networks Practice"
        assert len(header_args["questions"]) == 2
        # Check keyword fallback was generated for Q1
        assert len(header_args["questions"][0]["keywords"]) > 0
        # Check model_answer was promoted for Q2
        assert header_args["questions"][1].get("model_answer") is not None

        # Phase 2 — each question was inserted individually
        assert q_mock.insert.call_count == 2
        q1_args = q_mock.insert.call_args_list[0][0][0]
        assert q1_args["question_type"] == "mcq"
        assert q1_args["test_id"] == "saved-123"
        q2_args = q_mock.insert.call_args_list[1][0][0]
        assert q2_args["question_type"] == "short"
        assert q2_args["test_id"] == "saved-123"


def test_save_generated_exam_truncated_json_repair():
    from methods.tarika_agent_memory import save_generated_exam

    # Simulated truncated json due to max_tokens limit
    truncated_output = """```exam_stimulus
{
  "title": "OS Test",
  "questions": [
    {
      "id": 1,
      "type": "one_word",
      "question": "What program manages hardware resources?",
      "correct_answer": "Kernel",
      "marks": 1
    }
"""
    mock_client = MagicMock()

    header_mock = MagicMock()
    header_mock.insert.return_value.execute.return_value.data = [{"id": "saved-456", "title": "OS Test"}]
    q_mock = MagicMock()
    q_mock.insert.return_value.execute.return_value.data = [{"id": "q-1"}]

    def table_router(name):
        return header_mock if name == "ai_practice_tests" else q_mock

    mock_client.table.side_effect = table_router

    with patch("methods.tarika_agent_memory.init_supabase", return_value=mock_client):
        res = save_generated_exam("user_2", "u2@example.com", None, None, truncated_output, "test-model")
        assert res is not None

        # Phase 1: header saved
        header_args = header_mock.insert.call_args[0][0]
        assert len(header_args["questions"]) == 1
        assert header_args["questions"][0]["correct_answer"] == "Kernel"

        # Phase 2: individual question saved
        assert q_mock.insert.call_count == 1
        q_args = q_mock.insert.call_args_list[0][0][0]
        assert q_args["question_type"] == "one_word"
        assert q_args["correct_answer"] == "Kernel"
        assert q_args["test_id"] == "saved-456"
