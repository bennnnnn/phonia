"""Account — sign-in, sessions, profile and settings, data export and deletion.

``api`` serves ``/auth``. ``service`` signs users in with Google, Apple or dev
auth; ``tokens`` issues, rotates and revokes refresh sessions (the per-request
check lives in ``app.core.access_tokens``); ``web_session`` backs the web
client's refresh cookie. ``profile`` and the ``settings_*`` pair let chat
propose preference changes the user confirms. ``export`` and ``lifecycle``
serve data controls.
"""

# Seams the chat turn uses to read location and propose settings changes, and
# the outside-AI consent gate that chat, speech and scan reads stand behind.
_MODULE_EXPORTS = ("consent", "profile", "settings_intent", "settings_proposal")
