"""The model reader (``docs/MODEL_READER.md``): a model reads a question, in any language,
into one catalog law and the values it states; the server checks the read against the
message, and the subject's own binder must read it back to the same law and values.

A module of its own, below chat and above the subjects: it makes model calls, so it is not
one of the pure message readers (``turn_reading``, structure ticket ST-04). Chat calls
``service``; each subject owns its menu and the step from a read to an intent.
"""
