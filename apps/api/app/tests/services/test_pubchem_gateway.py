"""PubChem gateway — name/SMILES lookup (mocked, no real network)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.gateways import pubchem_gateway
from app.tests.fakes import redis_mock


def _mock_response(status_code: int, json_data: dict | None = None, text: str = "") -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.text = text
    return resp


@pytest.mark.asyncio
async def test_lookup_by_name_success() -> None:
    mock_resp = _mock_response(
        200,
        {
            "PropertyTable": {
                "Properties": [
                    {
                        "CID": 2244,
                        "CanonicalSMILES": "CC(=O)OC1=CC=CC=C1C(=O)O",
                        "MolecularFormula": "C9H8O4",
                        "MolecularWeight": "180.16",
                    }
                ]
            }
        },
    )
    client = AsyncMock()
    client.get = AsyncMock(return_value=mock_resp)
    with patch.object(pubchem_gateway, "get_pooled_client", return_value=client):
        result = await pubchem_gateway.lookup_by_name("aspirin")
    assert result.error is None
    assert result.compound is not None
    assert result.compound.cid == 2244
    assert result.compound.name == "aspirin"
    assert result.compound.smiles == "CC(=O)OC1=CC=CC=C1C(=O)O"
    assert result.compound.molecular_formula == "C9H8O4"
    assert result.compound.molecular_weight == 180.16


@pytest.mark.asyncio
async def test_lookup_by_name_not_found() -> None:
    mock_resp = _mock_response(404)
    client = AsyncMock()
    client.get = AsyncMock(return_value=mock_resp)
    with patch.object(pubchem_gateway, "get_pooled_client", return_value=client):
        result = await pubchem_gateway.lookup_by_name("nonexistent_compound_xyz")
    assert result.compound is None
    assert result.error is not None
    assert "not found" in result.error


@pytest.mark.asyncio
async def test_lookup_by_name_quotes_path() -> None:
    mock_resp = _mock_response(
        200,
        {
            "PropertyTable": {
                "Properties": [
                    {
                        "CID": 243,
                        "CanonicalSMILES": "C1=CC=CC=C1C(=O)O",
                        "MolecularFormula": "C7H6O2",
                        "MolecularWeight": "122.12",
                    }
                ]
            }
        },
    )
    client = AsyncMock()
    client.get = AsyncMock(return_value=mock_resp)
    with patch.object(pubchem_gateway, "get_pooled_client", return_value=client):
        result = await pubchem_gateway.lookup_by_name("benzoic acid")
    assert result.error is None
    url = client.get.await_args.args[0]
    assert "benzoic%20acid" in url
    assert "benzoic acid" not in url


@pytest.mark.asyncio
async def test_lookup_by_name_cache_hit_skips_http() -> None:
    redis = redis_mock()
    redis.get = AsyncMock(
        return_value=(
            '{"cid": 2244, "name": "aspirin", "smiles": "CC(=O)Oc1ccccc1C(=O)O",'
            ' "molecular_formula": "C9H8O4", "molecular_weight": 180.16}'
        )
    )
    with patch.object(pubchem_gateway, "get_pooled_client") as mock_client:
        result = await pubchem_gateway.lookup_by_name("aspirin", redis=redis)
    mock_client.assert_not_called()
    assert result.compound is not None
    assert result.compound.cid == 2244
    redis.get.assert_awaited_once_with("pubchem:name:aspirin")


@pytest.mark.asyncio
async def test_lookup_by_name_cache_stores_success() -> None:
    mock_resp = _mock_response(
        200,
        {
            "PropertyTable": {
                "Properties": [
                    {
                        "CID": 2244,
                        "CanonicalSMILES": "CC(=O)OC1=CC=CC=C1C(=O)O",
                        "MolecularFormula": "C9H8O4",
                        "MolecularWeight": "180.16",
                    }
                ]
            }
        },
    )
    client = AsyncMock()
    client.get = AsyncMock(return_value=mock_resp)
    redis = redis_mock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock()
    with patch.object(pubchem_gateway, "get_pooled_client", return_value=client):
        result = await pubchem_gateway.lookup_by_name("Aspirin", redis=redis)
    assert result.compound is not None
    redis.set.assert_awaited()
    assert redis.set.await_args.args[0] == "pubchem:name:aspirin"
    assert redis.set.await_args.kwargs.get("ex") == 24 * 60 * 60


@pytest.mark.asyncio
async def test_a_missing_compound_is_remembered_for_an_hour_not_a_day() -> None:
    client = AsyncMock()
    client.get = AsyncMock(return_value=_mock_response(404))
    redis = redis_mock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock()
    with patch.object(pubchem_gateway, "get_pooled_client", return_value=client):
        result = await pubchem_gateway.lookup_by_name("nope", redis=redis)
    assert result.error is not None and "not found" in result.error
    redis.set.assert_awaited_once_with("pubchem:name:nope", "missing", ex=60 * 60)
    client.get.assert_awaited_once()


@pytest.mark.asyncio
async def test_a_remembered_missing_compound_skips_http() -> None:
    redis = redis_mock()
    redis.get = AsyncMock(return_value=b"missing")
    with patch.object(pubchem_gateway, "get_pooled_client") as mock_client:
        result = await pubchem_gateway.lookup_by_name("nope", redis=redis)
    mock_client.assert_not_called()
    assert result.compound is None
    assert result.error == "compound 'nope' not found"


def _properties(**overrides: object) -> dict:
    props = {
        "CID": 2244,
        "CanonicalSMILES": "CC(=O)OC1=CC=CC=C1C(=O)O",
        "MolecularFormula": "C9H8O4",
        "MolecularWeight": "180.16",
    }
    props.update(overrides)
    return {"PropertyTable": {"Properties": [props]}}


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [429, 500, 503])
async def test_a_busy_pubchem_is_retried_once_and_never_remembered(
    status: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    sleeps: list[float] = []

    async def record(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(pubchem_gateway, "wait_before_retry", record)
    busy = _mock_response(status)
    busy.headers = {"Retry-After": "30"}
    client = AsyncMock()
    client.get = AsyncMock(return_value=busy)
    redis = redis_mock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock()
    with patch.object(pubchem_gateway, "get_pooled_client", return_value=client):
        result = await pubchem_gateway.lookup_by_name("aspirin", redis=redis)
    assert result.compound is None and result.error is not None
    assert client.get.await_count == 2
    assert sleeps == [1.0]  # Retry-After is honoured, but capped so the turn is not held
    redis.set.assert_not_called()


@pytest.mark.asyncio
async def test_a_busy_pubchem_that_recovers_on_the_retry_gives_the_compound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(pubchem_gateway, "wait_before_retry", AsyncMock())
    busy = _mock_response(503)
    busy.headers = {}
    client = AsyncMock()
    client.get = AsyncMock(side_effect=[busy, _mock_response(200, _properties())])
    with patch.object(pubchem_gateway, "get_pooled_client", return_value=client):
        result = await pubchem_gateway.lookup_by_name("aspirin")
    assert result.compound is not None and result.compound.cid == 2244


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "overrides",
    [
        {"CID": 0},
        {"CanonicalSMILES": ""},
        {"MolecularFormula": ""},
        {"MolecularWeight": "0"},
        {"MolecularWeight": "heavy"},
    ],
)
async def test_a_record_without_a_usable_cid_smiles_or_weight_is_an_error_not_a_result(
    overrides: dict[str, object],
) -> None:
    client = AsyncMock()
    client.get = AsyncMock(return_value=_mock_response(200, _properties(**overrides)))
    redis = redis_mock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock()
    with patch.object(pubchem_gateway, "get_pooled_client", return_value=client):
        result = await pubchem_gateway.lookup_by_name("aspirin", redis=redis)
    assert result.compound is None
    assert result.error is not None
    redis.set.assert_not_called()


@pytest.mark.asyncio
async def test_pubchems_renamed_smiles_key_is_read() -> None:
    body = _properties(CanonicalSMILES=None, ConnectivitySMILES="CCO")
    client = AsyncMock()
    client.get = AsyncMock(return_value=_mock_response(200, body))
    with patch.object(pubchem_gateway, "get_pooled_client", return_value=client):
        result = await pubchem_gateway.lookup_by_name("ethanol")
    assert result.compound is not None
    assert result.compound.smiles == "CCO"


@pytest.mark.asyncio
async def test_an_invalid_json_body_is_an_error() -> None:
    broken = _mock_response(200)
    broken.json.side_effect = ValueError("not json")
    client = AsyncMock()
    client.get = AsyncMock(return_value=broken)
    with patch.object(pubchem_gateway, "get_pooled_client", return_value=client):
        result = await pubchem_gateway.lookup_by_name("aspirin")
    assert result.compound is None and result.error is not None


@pytest.mark.asyncio
async def test_names_that_differ_only_in_spacing_and_case_share_a_cache_key() -> None:
    redis = redis_mock()
    redis.get = AsyncMock(return_value=b"missing")
    await pubchem_gateway.lookup_by_name("  Benzoic   ACID ", redis=redis)
    redis.get.assert_awaited_once_with("pubchem:name:benzoic acid")


@pytest.mark.asyncio
async def test_an_iupac_name_is_cached_and_a_missing_one_is_not() -> None:
    client = AsyncMock()
    client.get = AsyncMock(
        return_value=_mock_response(
            200, {"PropertyTable": {"Properties": [{"IUPACName": "ethanol"}]}}
        )
    )
    redis = redis_mock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock()
    with patch.object(pubchem_gateway, "get_pooled_client", return_value=client):
        assert await pubchem_gateway.lookup_iupac_name("CCO", redis=redis) == "ethanol"
    redis.set.assert_awaited_once_with("pubchem:iupac:CCO", "ethanol", ex=24 * 60 * 60)
    redis.get = AsyncMock(return_value=b"ethanol")
    with patch.object(pubchem_gateway, "get_pooled_client") as mock_client:
        assert await pubchem_gateway.lookup_iupac_name("CCO", redis=redis) == "ethanol"
    mock_client.assert_not_called()
    empty = AsyncMock()
    empty.get = AsyncMock(return_value=_mock_response(200, {"PropertyTable": {"Properties": [{}]}}))
    redis2 = AsyncMock()
    redis2.get = AsyncMock(return_value=None)
    redis2.set = AsyncMock()
    with patch.object(pubchem_gateway, "get_pooled_client", return_value=empty):
        assert await pubchem_gateway.lookup_iupac_name("CCO", redis=redis2) is None
    redis2.set.assert_not_called()


@pytest.mark.asyncio
async def test_lookup_by_name_empty() -> None:
    result = await pubchem_gateway.lookup_by_name("")
    assert result.compound is None
    assert result.error == "empty name"


@pytest.mark.asyncio
async def test_lookup_by_name_network_error() -> None:
    client = AsyncMock()
    client.get = AsyncMock(side_effect=Exception("network error"))
    with patch.object(pubchem_gateway, "get_pooled_client", return_value=client):
        result = await pubchem_gateway.lookup_by_name("aspirin")
    assert result.compound is None
    assert result.error is not None


@pytest.mark.asyncio
async def test_lookup_iupac_name_returns_only_that_property() -> None:
    mock_resp = _mock_response(
        200,
        {"PropertyTable": {"Properties": [{"CID": 702, "IUPACName": "  ethanol  "}]}},
    )
    client = AsyncMock()
    client.get = AsyncMock(return_value=mock_resp)
    with patch.object(pubchem_gateway, "get_pooled_client", return_value=client):
        name = await pubchem_gateway.lookup_iupac_name("CCO")
    assert name == "ethanol"
    url = client.get.await_args.args[0]
    assert url.endswith("/property/IUPACName/JSON")


@pytest.mark.asyncio
async def test_lookup_iupac_name_missing_is_not_a_common_name() -> None:
    mock_resp = _mock_response(200, {"PropertyTable": {"Properties": [{"CID": 702}]}})
    client = AsyncMock()
    client.get = AsyncMock(return_value=mock_resp)
    with patch.object(pubchem_gateway, "get_pooled_client", return_value=client):
        assert await pubchem_gateway.lookup_iupac_name("CCO") is None
    assert await pubchem_gateway.lookup_iupac_name("  ") is None
