"""Push notifications and transactional email."""

from pydantic import BaseModel


class NotificationSettings(BaseModel):
    push_enabled: bool = True
    server_todo_push_enabled: bool = True  # server owns due-at; skip local when push is on

    # Transactional email (welcome / receipts). Provider is Resend when
    # `resend_api_key` is set; otherwise a mock that logs the message so dev
    # works with zero external setup. Sending is always best-effort via the
    # background jobs stream — it never blocks auth or the chat path.
    email_enabled: bool = True
    # Opt-in todo-due emails (separate from welcome/receipt).
    email_reminders_scheduler_enabled: bool = True
    resend_api_key: str = ""
    resend_api_url: str = "https://api.resend.com/emails"
    email_from: str = "Recall <noreply@recall.app>"
