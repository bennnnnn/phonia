"""Chemistry: typed solvers, RDKit and PubChem.

Importing the package loads nothing: RDKit comes with ``smiles`` only, when a molecule
is drawn or described. Other modules import the submodules below.
"""

# What the subject order (services/subjects/order) reads of a line: the extracted intent,
# its text, a question's cues and a reaction's species; and ``subject``, chemistry as the
# subject registry (services/subjects/registry) asks it: its verified block, its direct
# reply, its prompt copy, its follow-ups and its fences.
_MODULE_EXPORTS = (
    "extract",
    "input_text",
    "request",
    "species",
    "subject",
)
