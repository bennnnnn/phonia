"""Reference-photo lookup: a real photo for "show me an ear", and above an answer."""

# The chat turn checks the lookup intent and runs the lookup in place of a reply;
# answer_photo puts a real photo above an ordinary reply.
_MODULE_EXPORTS = (
    "answer_photo",
    "lookup_intent",
    "search",
)
