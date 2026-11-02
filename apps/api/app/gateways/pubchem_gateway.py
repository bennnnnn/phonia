"""PubChem gateway — compound lookup by name, IUPAC name by SMILES (server-side only).

Provides:
- name → properties (SMILES, molecular formula, weight, CID) via the PUG-REST API
- SMILES → IUPACName via the PUG-REST API

A 404 means the name does not exist and is remembered for an hour; a 429, a 5xx or a network
error is PubChem being busy, is retried once after a bounded wait, and is never remembered.

All calls are server-side (Golden Rule 1 — no provider keys in the app).
PubChem is a free public API; no key required.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from redis.asyncio import Redis

from app.gateways.http_client import get_pooled_client

logger = logging.getLogger(__name__)

PUG_REST_URL = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
DEFAULT_TIMEOUT_SECONDS = 10.0
_CACHE_TTL_SECONDS = 24 * 60 * 60
_MISSING_TTL_SECONDS = 60 * 60
_TRANSIENT_STATUSES = frozenset({429, 500, 502, 503, 504})
# The turn waits at most a couple of seconds for PubChem, so a retry must be short.
_RETRY_DEFAULT_SECONDS = 0.25
_RETRY_MAX_SECONDS = 1.0
# PubChem renamed CanonicalSMILES to ConnectivitySMILES (and IsomericSMILES to SMILES) in the
# response; whichever it sends, the connectivity form comes first.
_SMILES_KEYS = ("CanonicalSMILES", "ConnectivitySMILES", "SMILES")


@dataclass(frozen=True)
class PubChemCompound:
    """A compound resolved from PubChem."""

    cid: int  # PubChem Compound ID
    name: str
    smiles: str  # canonical SMILES
    molecular_formula: str
    molecular_weight: float
    error: str | None = None


@dataclass(frozen=True)
class PubChemResult:
    """Result of a PubChem lookup — either a compound or an error."""

    compound: PubChemCompound | None = None
    error: str | None = None


@dataclass(frozen=True)
class _Fetched:
    """One PUG-REST answer: JSON, a definite "does not exist", or neither (busy or broken)."""

    data: dict[str, Any] | None = None
    missing: bool = False


def _normalized(text: str) -> str:
    return " ".join(text.split()).lower()


def _name_cache_key(name: str) -> str:
    return f"pubchem:name:{_normalized(name)}"


def _iupac_cache_key(smiles: str) -> str:
    return f"pubchem:iupac:{smiles.strip()}"


def _compound_from_cache(raw: str) -> PubChemCompound | None:
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    try:
        return _valid(
            PubChemCompound(
                cid=int(data["cid"]),
                name=str(data["name"]),
                smiles=str(data["smiles"]),
                molecular_formula=str(data["molecular_formula"]),
                molecular_weight=float(data["molecular_weight"]),
            )
        )
    except (KeyError, ValueError, TypeError):
        return None


def _compound_to_cache(compound: PubChemCompound) -> str:
    return json.dumps(
        {
            "cid": compound.cid,
            "name": compound.name,
            "smiles": compound.smiles,
            "molecular_formula": compound.molecular_formula,
            "molecular_weight": compound.molecular_weight,
        }
    )


def _valid(compound: PubChemCompound) -> PubChemCompound | None:
    """A compound with no CID, SMILES, formula or weight is a broken record, not a result."""
    if compound.cid <= 0 or not compound.smiles or not compound.molecular_formula:
        return None
    if compound.molecular_weight <= 0:
        return None
    return compound


def _first_properties(data: dict[str, Any]) -> dict[str, Any] | None:
    table = data.get("PropertyTable")
    rows = table.get("Properties") if isinstance(table, dict) else None
    if isinstance(rows, list) and rows and isinstance(rows[0], dict):
        return rows[0]
    return None


def _compound_from_properties(props: dict[str, Any], name: str) -> PubChemCompound | None:
    try:
        smiles = next((str(props[key]) for key in _SMILES_KEYS if props.get(key)), "")
        return _valid(
            PubChemCompound(
                cid=int(props.get("CID", 0)),
                name=name,
                smiles=smiles,
                molecular_formula=str(props.get("MolecularFormula", "")),
                molecular_weight=float(props.get("MolecularWeight", 0.0)),
            )
        )
    except (ValueError, TypeError):
        return None


def _retry_delay(headers: Any) -> float:
    """``Retry-After`` in seconds when PubChem sends one, capped; otherwise a short default."""
    try:
        return min(max(float(headers.get("Retry-After")), 0.0), _RETRY_MAX_SECONDS)
    except (AttributeError, TypeError, ValueError):
        return _RETRY_DEFAULT_SECONDS


async def wait_before_retry(seconds: float) -> None:
    """The pause before the one retry. A test replaces this, never ``asyncio.sleep``."""
    await asyncio.sleep(seconds)


async def _pug_get(url: str) -> _Fetched:
    """GET from PUG-REST as JSON, retrying once when PubChem is busy."""
    client = get_pooled_client(DEFAULT_TIMEOUT_SECONDS)
    for attempt in range(2):
        delay = _RETRY_DEFAULT_SECONDS
        try:
            resp = await client.get(url, headers={"Accept": "application/json"})
        except Exception as exc:
            logger.info("PubChem GET failed url=%s: %s", url, exc)
        else:
            if resp.status_code == 200:
                try:
                    body = resp.json()
                except ValueError:
                    logger.info("PubChem returned invalid JSON url=%s", url)
                    return _Fetched()
                return _Fetched(data=body if isinstance(body, dict) else None)
            if resp.status_code in {400, 404}:
                return _Fetched(missing=True)
            if resp.status_code not in _TRANSIENT_STATUSES:
                return _Fetched()
            delay = _retry_delay(resp.headers)
        if attempt == 0:
            await wait_before_retry(delay)
    return _Fetched()


async def _read_name_cache(redis: Redis, key: str, name: str) -> PubChemResult | None:
    try:
        cached = await redis.get(key)
    except Exception:
        logger.debug("PubChem cache read failed", exc_info=True)
        return None
    if cached is None:
        return None
    raw = cached.decode() if isinstance(cached, bytes) else cached
    if raw == "missing":
        return PubChemResult(error=f"compound '{name}' not found")
    compound = _compound_from_cache(raw)
    return None if compound is None else PubChemResult(compound=compound)


async def _write_cache(redis: Redis, key: str, value: str, ttl: int) -> None:
    try:
        await redis.set(key, value, ex=ttl)
    except Exception:
        logger.debug("PubChem cache write failed", exc_info=True)


async def lookup_by_name(name: str, redis: Redis | None = None) -> PubChemResult:
    """Resolve a compound name (e.g. 'aspirin') to a PubChem compound.

    Returns PubChemResult with error set when the name is not found.
    """
    name = " ".join(name.split())
    if not name:
        return PubChemResult(error="empty name")

    cache_key = _name_cache_key(name)
    if redis is not None:
        cached = await _read_name_cache(redis, cache_key, name)
        if cached is not None:
            return cached

    # PUG-REST: /compound/name/<name>/property/<properties>/JSON
    url = (
        f"{PUG_REST_URL}/compound/name/{quote(name, safe='')}/property/"
        "CanonicalSMILES,MolecularFormula,MolecularWeight/JSON"
    )
    fetched = await _pug_get(url)
    if fetched.missing:
        if redis is not None:
            await _write_cache(redis, cache_key, "missing", _MISSING_TTL_SECONDS)
        return PubChemResult(error=f"compound '{name}' not found")
    props = None if fetched.data is None else _first_properties(fetched.data)
    if props is None:
        return PubChemResult(error=f"compound '{name}' not found")
    compound = _compound_from_properties(props, name)
    if compound is None:
        return PubChemResult(error=f"PubChem returned no usable record for '{name}'")
    if redis is not None:
        await _write_cache(redis, cache_key, _compound_to_cache(compound), _CACHE_TTL_SECONDS)
    return PubChemResult(compound=compound)


async def lookup_iupac_name(smiles: str, redis: Redis | None = None) -> str | None:
    """Return PubChem's IUPACName property, or None when it is absent.

    A common title is not a substitute. Callers must not label a missing
    property as a verified IUPAC name.
    """
    smiles = smiles.strip()
    if not smiles:
        return None
    cache_key = _iupac_cache_key(smiles)
    if redis is not None:
        try:
            cached = await redis.get(cache_key)
        except Exception:
            logger.debug("PubChem cache read failed", exc_info=True)
            cached = None
        if cached:
            return cached.decode() if isinstance(cached, bytes) else str(cached)
    url = f"{PUG_REST_URL}/compound/smiles/{quote(smiles, safe='')}/property/IUPACName/JSON"
    fetched = await _pug_get(url)
    props = None if fetched.data is None else _first_properties(fetched.data)
    name = None if props is None else props.get("IUPACName")
    if not isinstance(name, str) or not name.strip():
        return None
    name = name.strip()
    if redis is not None:
        await _write_cache(redis, cache_key, name, _CACHE_TTL_SECONDS)
    return name
