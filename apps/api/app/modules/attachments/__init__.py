"""Attachments — upload, gallery, and retrieval.

Importing modules.attachments.models must not load the service graph.
"""

# Seams the chat turn uses. Repositories stay private; reach them through ``service``.
_MODULE_EXPORTS = (
    "content",
    "content_types",
    "lifecycle",
    "markers",
    "quota",
    "rag",
    "reuse",
    "vision_input",
)
