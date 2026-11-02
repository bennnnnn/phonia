"""Safety rules shared by every deterministic subject solver."""

VERIFIED_SOLVE_SAFETY_HINT = (
    "Verified-solve safety: Never claim that an answer or procedure was verified "
    "unless this turn contains a matching [BEGIN VERIFIED ...] block. When a "
    "verified block is present, copy its canonical values and working exactly; "
    "do not independently recompute or override them."
)
