from telegram_media.security import hash_password, new_session_token, token_hash, verify_password


def test_password_hash_round_trip():
    encoded = hash_password("a sufficiently long password", salt=b"0123456789abcdef")
    assert verify_password("a sufficiently long password", encoded)
    assert not verify_password("incorrect password", encoded)
    assert "sufficiently" not in encoded


def test_session_tokens_are_random_and_secret_bound():
    first = new_session_token()
    second = new_session_token()
    assert first != second
    assert token_hash(first, "secret-a") != token_hash(first, "secret-b")

