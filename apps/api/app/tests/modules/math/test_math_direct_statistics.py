"""Only complete, unweighted descriptive-statistics asks bypass the model."""

from dataclasses import replace

import pytest

from app.core.config import Settings
from app.modules.math.tools.direct import maybe_direct_math_reply
from app.modules.math.tools.direct_statistics import statistics_direct_request
from app.modules.math.tools.prompt import build_math_augmentation
from app.services.solving import VerifiedMathBlock


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query,answer",
    [
        ("Find the mean of 1,2,3", "2"),
        ("Find the median of 1,3,5", "3"),
        ("Find the mode of 1,2,2,3", "2"),
        ("Find the population variance of 1,2,3", "0.666667"),
        ("Find the sample variance of 1,2,3", "1"),
        ("Find the population standard deviation of 1,2,3", "0.8165"),
        ("Find the sample standard deviation of 1,2,3", "1"),
        ("Please calculate the average of [1, 2, 3].", "2"),
        ("What is the mean of (1/2, 1.5)?", "1"),
        ("Compute the median of {-1; +2; 3}", "2"),
        ("Mean .5, 1.5", "1"),
        ("Find the mean of 1e1 and 2e1", "15"),
        ("Find the mean of 1, 2, and 3", "2"),
    ],
)
async def test_complete_statistics_returns_one_existing_verified_answer(query: str, answer: str):
    _, verified = await build_math_augmentation(query, Settings(math_tools_enabled=True))
    assert verified is not None and verified.canonical_answer == answer
    assert statistics_direct_request(query) is True
    # A spread names which one it is: population (sigma) or sample (s).
    shown = (verified.display_answer or answer).strip()
    assert shown.endswith(answer)
    assert maybe_direct_math_reply(verified, query) == f"```answer\n{shown}\n```\n"


@pytest.mark.parametrize(
    "query",
    [
        "Find the mean of 1,2,3 and explain the formula",
        "Explain the population variance of 1,2,3",
        "Find the sample variance of 1,2,3 with steps",
        "Find the mean of 1,2,3, hint only",
        "Find the mean and median of 1,2,3",
        "Find the mean of 1,2,3 and 2+2",
        "Find the mean of 1,2,3 and tell a joke",
        "Find the mean of 1,2,3 and the variance",
        "Find the weighted mean of 1,2,3",
        "Find the mean of values 1,2,3 with probabilities .2,.3,.5",
        "Find the mean of 1,2,3 weights 1,2,3",
        "Find the population sample variance of 1,2,3",
        "Find the mean of 1,,2",
        "Find the mean of 1,2,",
        "Find the mean of ,1,2",
        "Find the mean of [1,2)",
        "Find the mean of [[1,2]]",
        "Find the mean of 1,2]",
        "Find the mean of [1,2",
        "Find the mean of 1-2",
        "Find the mean of 1and 2",
        "Find the mean of 1,2..",
        "Find the mean of 1,2!",
        "Find the mean of 1,,2 and",
        "Find the mean of 1/0,2",
        "Find the mean of 1,inf",
        "Find the mean of 1,nan",
        "Find the mean of 1,1e9999",
        "Find the mean of 1",
        "Find the mean of 1 cm,2 cm",
        "Find the mean of [1,2], [3,4]",
        "Find the mean of 1,2 rounded to the nearest 10",
        "What do you mean by 1,2,3",
    ],
)
def test_malformed_or_extra_statistics_requests_keep_model_path(query: str):
    # An existing permissive extractor may have verified a partial value;
    # the direct gate must still decline the full request in every case.
    verified = VerifiedMathBlock(
        text="verified", canonical_answer="2", canonical_fence={"type": "answer", "content": "2"}
    )
    assert statistics_direct_request(query) is False
    assert maybe_direct_math_reply(verified, query) is None


@pytest.mark.asyncio
async def test_statistics_keeps_camera_disabled_and_multiple_result_paths():
    query = "Find the mean of 1,2,3"
    _, verified = await build_math_augmentation(query, Settings(math_tools_enabled=True))
    assert verified is not None
    assert maybe_direct_math_reply(verified, query, has_image_attachment=True) is None
    assert maybe_direct_math_reply(replace(verified, allow_direct=False), query) is None
    assert (
        maybe_direct_math_reply(
            replace(verified, canonical_fences=[{"type": "answer", "content": "3"}]), query
        )
        is None
    )
    assert (
        maybe_direct_math_reply(
            replace(verified, canonical_fence={"type": "answer", "content": "3"}), query
        )
        is None
    )


def test_statistics_data_limits_and_unrelated_arithmetic():
    assert statistics_direct_request("Find the mean of " + ",".join(["1"] * 201)) is False
    assert statistics_direct_request("Find the mean of " + "1" * 1001) is False
    assert statistics_direct_request("2+2") is None
    block = VerifiedMathBlock(text="verified", canonical_answer="4")
    assert maybe_direct_math_reply(block, "2+2") == "```answer\n4\n```\n"
