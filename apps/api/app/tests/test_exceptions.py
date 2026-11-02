from app.exceptions import (
    ChatBusyError,
    ChatNotFoundError,
    ChatServiceError,
    QuotaExceededError,
    UnknownModelOverrideError,
)


def test_chat_service_errors_carry_message():
    err = ChatServiceError("boom")
    assert err.message == "boom"
    assert str(err) == "boom"
    assert isinstance(QuotaExceededError("q"), ChatServiceError)
    assert isinstance(ChatNotFoundError("missing"), ChatServiceError)
    assert isinstance(ChatBusyError(), ChatServiceError)
    assert ChatBusyError().message.startswith("Still generating")
    unknown = UnknownModelOverrideError("smart-chat")
    assert isinstance(unknown, ChatServiceError)
    assert unknown.alias == "smart-chat"
    assert "smart-chat" in unknown.message


def test_unknown_model_override_error_payload():
    from app.modules.chat.stream_events import error_payload_for_exception

    payload = error_payload_for_exception(UnknownModelOverrideError("glm-5.2"))
    assert payload["type"] == "error"
    assert payload["code"] == "unknown_model"
    assert "glm-5.2" in payload["message"]
