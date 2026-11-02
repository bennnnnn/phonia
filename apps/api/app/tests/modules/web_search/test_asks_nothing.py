import pytest

from app.modules.web_search.asks_nothing import asks_nothing_to_look_up


@pytest.mark.parametrize(
    "text",
    [
        "Hello there how is your day going because you are doing a great job today",
        "Thanks, that was really helpful today",
        "I just watched the news and I feel overwhelmed",
        "Prices at the market were crazy high today",
        "Glad it's Friday today",
        "Write a short poem about today",
        "Teach me something new today",
        "What should I cook for dinner tonight with chicken and rice?",
        "What a day today, so much happened",
        # A learner stuck on a topic tells; the lesson answers, nothing is searched.
        "recursion makes no sense to me",
        "pointers confuse me",
        # Sample, mock or example data is made up on the spot.
        "Give me sample CSV data for 5 students with name, grade and score",
        "give me mock API responses for a login endpoint",
        "show me sample SQL inserts for a library app",
        "give me test data for a signup form",
        # Made, with no figure to find: an exact word beside something that is not a fee.
        "Give me a table of the exact synonyms for happy",
        "Give me a table of the current players in my fantasy team draft",
        # A question about the chat itself, opening with a preposition.
        "In which order did we cover topics today? List them.",
        "In what order did we talk about things today?",
        "At what point did you say that?",
        "For which topics did I ask you for sources?",
    ],
)
def test_asks_nothing_to_look_up_statements_and_requests_to_make(text):
    assert asks_nothing_to_look_up(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "latest news about Ethiopia",
        "the score of my team's game today",
        "the price of gold went up again today in London",
        "What's open near me right now?",
        "where should I eat tonight?",
        "Do I need a visa for Kenya with an Ethiopian passport?",
        "We need a hotel in Paris",
        "I want the latest news on the AI Act",
        "Write a summary of today's news",
        "Is it going to rain tonight in London?",
        "give me test results for the 2024 national exam in Ethiopia",
        "give me the sample size of the Framingham study",
        "In what year did the Berlin Wall fall?",
        "At what time does the Lakers game start tonight?",
        "From where did you get that? Find the source",
        # A table or list in form, the real figures in substance.
        "Give me a table of the exact transaction charges for buying 30,000 KES of NSE shares",
        "Give me a list of the official visa fees for Kenya",
        "Write me a summary of the current interest rates on Kenyan savings accounts",
        "Make a table of the actual brokerage commission and levy rates in Kenya",
    ],
)
def test_asks_nothing_to_look_up_keeps_lookups(text):
    assert asks_nothing_to_look_up(text) is False
