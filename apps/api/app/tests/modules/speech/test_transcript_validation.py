from app.modules.speech.transcript_validation import sanitize_transcript


def test_sanitize_keeps_real_watching_phrase_on_enough_audio():
    text = sanitize_transcript("Thank you for watching.", audio_size=80_000)
    assert text == "Thank you for watching."


def test_sanitize_drops_watching_hallucination_on_tiny_clip():
    assert sanitize_transcript("thanks for watching!", audio_size=800) == ""


def test_sanitize_keeps_ordinary_dictation():
    assert sanitize_transcript("remind me to call mom", audio_size=800) == "remind me to call mom"
