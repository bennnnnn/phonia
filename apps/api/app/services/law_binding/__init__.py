"""A law catalog engine any subject can read questions into.

A subject declares its laws as ``spec.FormulaSpec`` records. The engine reads the numbers
a question states (``givens``, through the subject's ``units.UnitTable``), the words
around them (``words``), fills a law from both (``fit``), and evaluates and typesets an
expression law (``expression``, in the subject's ``Notation``). Physics is the first
subject; nothing here imports a product module.
"""
