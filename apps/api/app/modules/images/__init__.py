"""Image generation and reference-photo lookup.

Importing a submodule must not pull the other product's service graph.
"""

# The chat turn checks both intents and runs generation or lookup in place of a reply;
# answer_photo puts a real photo above an ordinary reply, and reply_picture a drawn one
# above the reply to a message that asked for a picture among other things.
_MODULE_EXPORTS = (
    "answer_photo",
    "gen_intent",
    "generation",
    "intent",
    "lookup_intent",
    "reply_picture",
    "search",
)
