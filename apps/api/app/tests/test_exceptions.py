from app.exceptions import (
    ChatBusyError,
    ChatNotFoundError,
    ChatServiceError,
    QuotaExceededError,
)


def test_chat_service_errors_carry_message():
    err = ChatServiceError("boom")
    assert err.message == "boom"
    assert str(err) == "boom"
    assert isinstance(QuotaExceededError("q"), ChatServiceError)
    assert isinstance(ChatNotFoundError("missing"), ChatServiceError)
    assert isinstance(ChatBusyError(), ChatServiceError)
    assert ChatBusyError().message.startswith("Still generating")
