"""Importing the chemistry package loads nothing: callers import the submodule they use.

It used to import its solvers, equations, stoichiometry and ``smiles`` (about a second
and NumPy) for a public list nothing read.
"""

import subprocess
import sys


def test_importing_the_package_loads_none_of_its_submodules() -> None:
    probe = (
        "import sys\n"
        "import app.modules.chemistry\n"
        "loaded = sorted(n for n in sys.modules if n.startswith('app.modules.chemistry.'))\n"
        "heavy = sorted({n.split('.')[0] for n in sys.modules} & {'numpy', 'rdkit', 'sympy'})\n"
        "assert not loaded and not heavy, (loaded, heavy)\n"
    )
    result = subprocess.run(  # noqa: S603 - fixed argv: this interpreter and a literal script
        [sys.executable, "-c", probe], capture_output=True, text=True, timeout=120, check=False
    )
    assert result.returncode == 0, result.stderr
