from uuid import uuid4

from app.modules.chat.turn_timing import TurnTimingTracker


def test_turn_timing_tracker_records_phases_and_logs(caplog):
    tracker = TurnTimingTracker()
    tracker.mark_phase("preparing")
    tracker.mark_prompt_ready()
    tracker.mark_first_token()

    user_id = uuid4()
    chat_id = uuid4()
    with caplog.at_level("INFO"):
        tracker.log_summary(
            user_id=user_id, chat_id=chat_id, model="free-chat", lightweight=True, content_chars=2
        )

    assert "chat_stream_timing" in caplog.text
    assert str(user_id) in caplog.text
    assert "lightweight=True" in caplog.text
    assert "content_chars=2" in caplog.text
    assert "prompt_ready_ms=" in caplog.text
    assert "first_token_ms=" in caplog.text
    assert "post_prompt_first_token_ms=" in caplog.text
    assert "gateway_to_first_token_ms=None" in caplog.text
    assert tracker._first_token_ms is not None
    assert tracker._prompt_ready_ms is not None
