"""Push notifications and transactional email."""

from pydantic import BaseModel


class NotificationSettings(BaseModel):
    push_enabled: bool = True
    server_todo_push_enabled: bool = True  # server owns due-at; skip local when push is on
    # Devices one account keeps a push token for; registering one more drops the oldest.
    push_tokens_max_per_user: int = 10
    # A reminder push not delivered within this long (the phone was off) is dropped by
    # the push services instead of arriving hours late.
    push_reminder_ttl_seconds: int = 4 * 60 * 60
    # A push Expo may have accepted (it timed out after the request went out, or its
    # answer was unreadable) waits this long: resent next minute, it would show twice.
    push_ambiguous_hold_seconds: int = 15 * 60

    # A reminder send that failed for now (a timeout, a 429, a 5xx) waits this long
    # before its next try, doubling up to the max; one the provider refused for good
    # waits the max. Per reminder, in Redis (``notifications.send_backoff``).
    reminder_retry_base_seconds: int = 60
    reminder_retry_max_seconds: int = 60 * 60
    # How long one reminder cycle (every minute) keeps sending while due reminders
    # remain, refreshing its lock; the rest go next cycle.
    reminder_cycle_budget_seconds: int = 50
    # How long one receipts pass (every five minutes) keeps polling ready tickets.
    push_receipt_poll_budget_seconds: int = 120

    # Transactional email (welcome / receipts). Provider is Resend when
    # `resend_api_key` is set; otherwise a mock that logs the message so dev
    # works with zero external setup. Sending is always best-effort via the
    # background jobs stream — it never blocks auth or the chat path.
    email_enabled: bool = True
    # Opt-in todo-due emails (separate from welcome/receipt).
    email_reminders_scheduler_enabled: bool = True
    resend_api_key: str = ""
    resend_api_url: str = "https://api.resend.com/emails"
    email_from: str = "Phonia <noreply@phonia.app>"
