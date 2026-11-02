"""The sections ``core.config.Settings`` is made of, one purpose each.

Code never imports a section: it reads ``settings.<field>`` from
``app.core.config.get_settings()``. Each field is read from the environment
(or ``.env``) by its own name in upper case, exactly as when every field sat in
one class. A new setting is one field, with its default and a comment saying
why, in the section it belongs to; ``tests/core/test_config.py`` checks that every
field loads from its env name and that no two sections declare the same one.
"""
