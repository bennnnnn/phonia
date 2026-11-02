"""Tests for the post-stream prose artifact normalizer."""

import pytest

from app.modules.chat.prose_normalizer import (
    fill_sender_name_slots,
    normalize_prose_artifacts,
    prose_changed,
    strip_unrequested_recipient_placeholders,
)


class TestNormalizeProseArtifacts:
    def test_orphan_colon_line_removed(self):
        text = "Step 1: Simplify\n:\n$2x + 3 = 7$"
        result = normalize_prose_artifacts(text)
        assert ":" not in result.split("\n")
        assert "Step 1: Simplify" in result
        assert "$2x + 3 = 7$" in result

    def test_colon_with_whitespace_removed(self):
        text = "Step 1\n  :  \nFormula here"
        result = normalize_prose_artifacts(text)
        assert result == "Step 1\n\nFormula here"

    def test_inline_colon_preserved(self):
        text = "For x = 3: the result is 6"
        result = normalize_prose_artifacts(text)
        assert result == "For x = 3: the result is 6"

    def test_colon_in_code_fence_preserved(self):
        text = "```python\nx: int = 0\n```"
        result = normalize_prose_artifacts(text)
        # The colon inside the code fence should not be removed because
        # it's not on its own line — it's part of a code line.
        assert "x: int = 0" in result

    def test_lone_colon_line_inside_yaml_fence_preserved(self):
        text = "```yaml\nkey: value\n:\nnested: 1\n```"
        result = normalize_prose_artifacts(text)
        assert ":\n" in result or "\n:" in result
        assert "nested: 1" in result

    def test_blank_lines_inside_python_fence_preserved(self):
        text = "```python\ndef a():\n    return 1\n\n\n\ndef b():\n    return 2\n```"
        result = normalize_prose_artifacts(text)
        assert "def a():" in result
        assert "def b():" in result
        inner = result.split("```python")[1].split("```")[0]
        assert inner.count("\n\n\n") >= 1

    def test_multiple_orphan_colons_removed(self):
        text = "Step 1\n:\nStep 2\n:\nStep 3"
        result = normalize_prose_artifacts(text)
        assert result == "Step 1\n\nStep 2\n\nStep 3"

    def test_excess_blank_lines_collapsed(self):
        text = "Paragraph 1\n\n\n\n\nParagraph 2"
        result = normalize_prose_artifacts(text)
        assert result == "Paragraph 1\n\nParagraph 2"

    def test_double_newline_preserved(self):
        text = "Paragraph 1\n\nParagraph 2"
        result = normalize_prose_artifacts(text)
        assert result == "Paragraph 1\n\nParagraph 2"

    def test_no_change_returns_unchanged(self):
        text = "Hello world\n\nThis is fine."
        result = normalize_prose_artifacts(text)
        assert result == text

    def test_strips_trailing_whitespace(self):
        text = "Hello\n\n\n"
        result = normalize_prose_artifacts(text)
        assert result == "Hello"

    def test_strips_leading_whitespace(self):
        text = "\n\n\nHello"
        result = normalize_prose_artifacts(text)
        assert result == "Hello"

    def test_combined_orphan_colon_and_excess_blanks(self):
        text = "Step 1: Simplify\n:\n\n\n$2x = 4$\n\n\n\nStep 2"
        result = normalize_prose_artifacts(text)
        assert result == "Step 1: Simplify\n\n$2x = 4$\n\nStep 2"

    def test_unwraps_fenced_pipe_table(self):
        text = "```\n| Type | Mutable |\n|:---|:---:|\n| list | Yes |\n```"

        result = normalize_prose_artifacts(text)

        assert result == "| Type | Mutable |\n|:---|:---:|\n| list | Yes |"

    def test_unwraps_markdown_tagged_pipe_table_with_surrounding_prose(self):
        text = (
            "Comparison:\n\n```markdown\n| Type | Ordered |\n|---|---|\n"
            "| dict | Yes |\n```\n\nDone."
        )

        result = normalize_prose_artifacts(text)

        assert "```" not in result
        assert "| dict | Yes |" in result
        assert result.startswith("Comparison:")
        assert result.endswith("Done.")

    def test_does_not_unwrap_mixed_generic_code_fence(self):
        text = "```\n| value = left | right\nprint(value)\n```"

        assert normalize_prose_artifacts(text) == text

    def test_does_not_unwrap_language_code_fence_that_contains_a_table(self):
        text = "```python\n| Type | Mutable |\n|---|---|\n| list | Yes |\n```"

        assert normalize_prose_artifacts(text) == text


class TestProseChanged:
    def test_changed_when_colon_removed(self):
        original = "Step 1\n:\nFormula"
        normalized = normalize_prose_artifacts(original)
        assert prose_changed(original, normalized) is True

    def test_unchanged_when_no_artifacts(self):
        original = "Hello world\n\nThis is fine."
        normalized = normalize_prose_artifacts(original)
        assert prose_changed(original, normalized) is False

    def test_unchanged_for_empty_string(self):
        original = ""
        normalized = normalize_prose_artifacts(original)
        assert prose_changed(original, normalized) is False


class TestRecipientPlaceholderCleanup:
    def test_unknown_coworker_name_becomes_generic_greeting(self):
        text = "```message\nHey [Coworker's Name], I'll be 20 minutes late.\n```"

        result = strip_unrequested_recipient_placeholders(text, "Write a message to my coworker")

        assert result == "```message\nHey, I'll be 20 minutes late.\n```"

    def test_unknown_recipient_in_email_becomes_generic_greeting(self):
        text = "```email\nDear [Recipient Name],\n\nThanks.\n```"

        result = strip_unrequested_recipient_placeholders(text, "Write an email saying thanks")

        assert result == "```email\nHello,\n\nThanks.\n```"

    def test_an_unnamed_hiring_manager_keeps_the_letters_greeting(self):
        text = "```copy\nDear [Hiring Manager's Name],\n\nI am applying for the role.\n```"

        result = strip_unrequested_recipient_placeholders(text, "write a cover letter")

        assert result == "```copy\nDear Hiring Manager,\n\nI am applying for the role.\n```"

    def test_explicit_template_keeps_placeholder(self):
        text = "```message\nHi [Name], welcome!\n```"

        result = strip_unrequested_recipient_placeholders(text, "Make a reusable message template")

        assert result == text

    def test_non_copy_fence_is_unchanged(self):
        text = "```python\nlabel = '[Recipient Name]'\n```"

        assert strip_unrequested_recipient_placeholders(text, "Explain this code") == text


class TestSenderNameSlots:
    """A draft signed "[Your name]" was a card the user had to edit before sending."""

    @pytest.mark.parametrize(
        ("draft", "signed"),
        [
            (
                "```email\nSubject: Recap\n\nHi all,\n\nThanks!\n\nBest,\n[Your name]\n```",
                "```email\nSubject: Recap\n\nHi all,\n\nThanks!\n\nBest,\nBini\n```",
            ),
            (
                "```sms\nHi, this is [your name], I have a haircut booked for 2pm.\n```",
                "```sms\nHi, this is Bini, I have a haircut booked for 2pm.\n```",
            ),
            ("```copy\nSincerely, [Your Full Name]\n```", "```copy\nSincerely, Bini\n```"),
        ],
    )
    def test_the_sender_slot_is_the_users_first_name(self, draft: str, signed: str) -> None:
        assert fill_sender_name_slots(draft, "write a recap email", "Bini") == signed

    def test_with_no_name_the_draft_ends_on_its_closing_word(self) -> None:
        draft = "```email\nThanks!\n\nBest,\n[Your Name]\n```"
        assert fill_sender_name_slots(draft, "write an email", None) == (
            "```email\nThanks!\n\nBest,\n```"
        )
        signed_inline = "```message\nSee you soon! Love, [your name]\n```"
        assert fill_sender_name_slots(signed_inline, "text my mom", None) == signed_inline
        closing = "```copy\nSincerely, [Your Name]\n```"
        assert fill_sender_name_slots(closing, "write a letter", None) == "```copy\nSincerely,\n```"

    def test_a_template_another_persons_slot_and_prose_keep_their_slots(self) -> None:
        template = "```email\nBest,\n[Your name]\n```"
        assert (
            fill_sender_name_slots(template, "make a reusable email template", "Bini") == template
        )
        aunt = "```copy\nDear Aunt [Name],\n\nThank you!\n```"
        assert fill_sender_name_slots(aunt, "write a thank you card", "Bini") == aunt
        prose = "Replace [Your name] with how you sign emails."
        assert fill_sender_name_slots(prose, "how do I sign an email", "Bini") == prose
