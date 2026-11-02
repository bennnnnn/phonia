"""The subjects a turn is solved by (structure ticket ST-07).

- ``registry``: each subject's adapter, one entry per subject;
- ``order``: which subject a line is, the one place precedence between subjects is written;
- ``dispatch``: a line's subject, its solve and its direct reply, asked through the registry.

The package imports nothing here, so reading the order does not load the dispatcher.
"""
