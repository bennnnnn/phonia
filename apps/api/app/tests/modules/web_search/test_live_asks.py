"""Job openings and prices search without waiting on the classifier (T5.2, T5.8).

Each rule names what is looked up, so the look-alikes ("I got the job", "cron job",
"the price of freedom") stay ordinary chat.
"""

from __future__ import annotations

import pytest

from app.modules.web_search.detection import needs_web_search, web_search_fast_yes
from app.modules.web_search.live_asks import (
    asks_for_a_price,
    asks_for_entry_rules,
    asks_for_job_listings,
    asks_for_official_charges,
)
from app.modules.web_search.release_asks import asks_if_released


@pytest.mark.parametrize(
    "text",
    [
        "find remote backend engineering jobs",
        "find software jobs posted today",
        "remote python developer openings",
        "any data analyst vacancies in Nairobi?",
        "who is hiring react developers right now",
        "job openings at Google",
        "find me a job as a nurse in Nairobi",
        "show me software engineering internships in Berlin",
        "what jobs are available for nurses in Kenya",
        "I want to find remote backend engineering jobs",
        "entry-level marketing roles in London",
    ],
)
def test_job_listings_search_at_once(text: str) -> None:
    assert asks_for_job_listings(text)
    assert web_search_fast_yes(text)
    assert needs_web_search(text)


@pytest.mark.parametrize(
    "text",
    [
        "I got the job",
        "set up a cron job that runs every night",
        "job interview tips",
        "write a cover letter for a backend job",
        "how do I find a job after college",
        "you're doing a great job today",
        "what jobs can I get with a biology degree",
        "best jobs for introverts",
        "tell me about Steve Jobs",
        "the jobs to be done framework",
        "my celery jobs keep failing",
        "chess openings for beginners",
        "best yoga positions for back pain",
        "I'm looking for a new job",
        "what is a job description",
        "kubernetes jobs vs cronjobs",
        "I have two jobs and no time",
        "how do I list background jobs in sidekiq",
    ],
)
def test_job_lookalikes_are_not_listings(text: str) -> None:
    assert not asks_for_job_listings(text)


@pytest.mark.parametrize(
    "text",
    [
        "how much does the iPhone 17 Pro cost?",
        "how much does the iphone 17 pro cost",
        "bitcoin price today",
        "what is the current price of bitcoin?",
        "USD to ETB exchange rate",
        "usd to etb",
        "how many birr is a dollar",
        "price of gold today",
        "Tesla stock price",
        "how much is a PS5 now",
        "what's the price of a MacBook Air M4",
    ],
)
def test_prices_search_at_once(text: str) -> None:
    assert asks_for_a_price(text)
    assert web_search_fast_yes(text)


@pytest.mark.parametrize(
    "text",
    [
        "what's the price of freedom",
        "how should I price my online course",
        "what is price elasticity of demand",
        "If apples cost $2 each, how much do 5 apples cost?",
        "the price is right",
        "how much does it cost to build a house",
        "write a poem about the price of fame",
        "what's a good pricing strategy for a startup",
        "how much do you love me",
        "price discrimination examples",
        "how much is 2x + 3 when x = 4",
    ],
)
def test_price_lookalikes_are_not_lookups(text: str) -> None:
    assert not asks_for_a_price(text)


@pytest.mark.parametrize(
    "text",
    [
        "UK visa rules for Ethiopian citizens",
        "do I need a visa for Japan?",
        "visa requirements for Kenya",
        "is there visa on arrival in Rwanda",
    ],
)
def test_visa_rules_search_at_once(text: str) -> None:
    assert asks_for_entry_rules(text)
    assert web_search_fast_yes(text)


@pytest.mark.parametrize(
    "text",
    [
        # Answered from memory with a "CSTA levy" and a 0.75% stamp duty no schedule lists.
        "Give me a table of the exact transaction charges when buying 30,000 KES of NSE shares",
        "what are the official stamp duty rates on a car sale in Kenya",
        "what are the M-PESA withdrawal charges",
        "what are the brokerage fees for buying shares on the NSE",
        "list the current registration fees for a new company in Rwanda",
    ],
)
def test_what_an_institution_charges_is_read_not_recalled(text: str) -> None:
    assert asks_for_official_charges(text)
    assert needs_web_search(text)


@pytest.mark.parametrize(
    "text",
    [
        "calculate the exact tax on 50,000 at 16%",
        "work out the transaction fee as 2% of 30,000",
        "write a poem about fees and charges",
        "my phone charges slowly, is that normal",
        "what is the formula for the current in a circuit",
        "I paid a brokerage fee yesterday and it annoyed me",
        "What is a brokerage fee?",
        "I paid a withdrawal fee, why?",
    ],
)
def test_charge_lookalikes_do_not_search(text: str) -> None:
    assert not needs_web_search(text)


@pytest.mark.parametrize(
    "text",
    [
        "what is a visa",
        "write a cover letter for my visa application",
        "my Visa card was declined",
        "how do I pay with Visa on Amazon",
    ],
)
def test_visa_lookalikes_are_not_rules(text: str) -> None:
    assert not asks_for_entry_rules(text)


@pytest.mark.parametrize(
    "text",
    [
        # Answered "the current model is the iPhone 16" from training data.
        "Is iPhone 19 out?",
        "Is the iPhone 17 out yet?",
        "has gta 6 been released",
        "has GTA 6 come out yet",
        "did season 5 of stranger things drop",
        "when does iphone 19 come out",
        "When will Windows 12 be released?",
        "when is the new Zelda coming out",
        "is Grand Theft Auto VI out",
        "GTA 6 release date",
        "release date of the iPhone 19",
        "is the new Kendrick album out",
        "when is Avatar 3 coming out",
        "is ios 27 out yet",
        "Is GPT-6 available yet?",
        "has the Switch 2 launched",
        "is Stranger Things season 5 out on netflix yet",
        "Are the AirPods Pro 3 out?",
    ],
)
def test_release_questions_search_at_once(text: str) -> None:
    assert asks_if_released(text)
    assert web_search_fast_yes(text)
    assert needs_web_search(text)


@pytest.mark.parametrize(
    "text",
    [
        "is the power out",
        "is the moon out tonight",
        "Is Tom out yet?",
        "Is Dad out?",
        "is my order out for delivery",
        "is it out yet",
        "are my exam results out",
        "is the cake out yet",
        "when does school get out",
        "when is mom coming out",
        "has the baby come out yet",
        "is he out of surgery",
        "when does the sun come out",
        "is 5 out of 10 good",
        "is the tide out at 6",
        "is Tom out on bail",
    ],
)
def test_out_that_is_not_a_release_is_not_one(text: str) -> None:
    assert not asks_if_released(text)


@pytest.mark.parametrize(
    "text",
    [
        # Answered "it hasn't been released yet" from training data (2026-10-24).
        "which chip does the iPhone 18 Pro Max have and when was it released?",
        "which chip does the iphone 18 pro max have and when was it released",
        "do you know when the Galaxy S26 came out?",
        "can you tell me if GTA 6 is out yet?",
        "I'm thinking of getting the Pixel 11, is it out yet?",
        "what's the battery life on the iPhone 18 Pro, and when did it come out?",
        "tell me whether the Switch 2 has been released",
        "I keep hearing about GPT-6 \u2014 when does it come out?",
        "GTA 6 \u2013 when does it come out",
        "is the iPhone 19 out? and how much will it cost?",
        "The new Pixel 11 looks great but is it available in Kenya?",
        "I loved Severance season 2, when is season 3 coming out?",
        "do you know if the new Zelda is out",
        "I watched Oppenheimer in 2023, when did it come out on streaming?",
    ],
)
def test_a_release_ask_inside_a_longer_message_searches(text: str) -> None:
    assert asks_if_released(text)
    assert web_search_fast_yes(text)


@pytest.mark.parametrize(
    "text",
    [
        "I have 2 dogs, are they out yet?",
        "OK so I have 2 cats, are they out yet?",
        "My phone is 2 years old, when was it released?",
        "I put the cake in at 3, is it out yet?",
        "my iPhone 15 battery died, is it out of warranty?",
        "I got the iPhone 17 yesterday, is it any good?",
        "I love Windows 11 but when it crashes I lose work",
        "do you know if the store is out of milk",
        "do you know when the sun comes out",
        "tell me if Tom is out",
        "do you know if Dad is out yet",
        "can you tell me when my package came out",
        "the meeting is at 3, is it out on the calendar",
        "Tom and Jerry is out of the house",
        "I scored 5 out of 10, is it good",
        "my kid is in grade 3 and when does school get out",
        "we have 2 kids and they are out at school",
    ],
)
def test_a_longer_message_with_out_in_it_is_no_release_ask(text: str) -> None:
    """ "It" is a release only when the message names a product: a brand, or a name with a
    model number ("Pixel 11"). A pet, a cake, a phone of the user's own are not."""
    assert not asks_if_released(text)
