"""Hosted account-deletion page (Google Play Data safety "Delete account URL").

What is deleted and what is kept follows ``modules/account/lifecycle.py``
(``delete_account``), ``modules/account/quota_carryover.py`` and SECURITY.md.
"""

# Legal prose is one paragraph or bullet per line.
# ruff: noqa: E501

from __future__ import annotations

from app.content.legal import contact_markdown

_ACCOUNT_DELETION_MD = """# Delete Your Recall Account

You can delete your Recall account and its data at any time, in the app or by asking us.

## Delete in the app

1. Open Recall and sign in.
2. Open the sidebar and tap your profile photo or initials to open Settings.
3. Tap Data controls.
4. Tap Delete your account, then confirm.

Deletion is permanent and starts at once. Every device you are signed in on is signed out. If Recall cannot start it right now, nothing is deleted and the app asks you to try again in a moment.

## Ask us to delete it

If you no longer have the app, {contact} from the email address your Recall account uses and ask us to delete the account. If you use Sign in with Apple with Hide My Email, include that relay address (shown in Settings → Account). We may ask you to confirm the request before we delete the account.

## What is deleted

- Your profile and settings.
- Every chat and its messages, including archived chats.
- Your saved memory.
- Your reminders and to-dos.
- Files and photos you uploaded, AI images you created, the text read from them, and their search indexes.
- Usage counts, product events, push notification tokens and signed-in sessions.
- Cached copies of your data and queued background work that contains your text.

## What is kept, and for how long

- **Usage limits**: So that deleting an account and signing up again cannot reset today's limits, Recall keeps a record holding only counts (today's usage and this month's live talk time). It is filed under one-way codes, never your name, your email address itself or any content. The codes are made from your Google or Apple sign-in and, if your email address is a Gmail, iCloud, me.com, mac.com or Hide My Email address, from your email address too. If you sign in again with the same Google or Apple account, or with either one on an email address filed this way, the Recall account you sign in to (a new one, or one that already uses your email) starts from at least those counts and the copies it used are deleted. Any copy left expires when the month ends (UTC), after at most 35 days.
- **Technical markers**: A few records that hold only internal ids, such as the one that keeps your old sign-in tokens rejected, expire within a day.
- **Subscriptions**: Deleting your account does not cancel a subscription. Cancel it in the App Store or Google Play first. Purchase records stay with Apple or Google and RevenueCat under their terms.
- **Backups, logs and crash reports**: Copies held by our service providers are removed as their retention periods end.
- **Data already sent to AI and search services** is handled under those services' terms, as described in the [Privacy Policy](/legal/privacy).

## Questions

If you have questions about deleting your data, {contact}."""


def account_deletion_markdown(support_email: str) -> str:
    return _ACCOUNT_DELETION_MD.format(contact=contact_markdown(support_email))
