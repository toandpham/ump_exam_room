"""Candidate identifier classification (CCCD vs passport) — AD-58."""
import pytest

from app.core.identifier import CCCD, PASSPORT, classify_identifier


def test_twelve_digits_is_cccd():
    assert classify_identifier("079095000111") == ("079095000111", CCCD)


def test_passport_uppercased_and_classified():
    assert classify_identifier("  c1234567 ") == ("C1234567", PASSPORT)
    assert classify_identifier("ab123456") == ("AB123456", PASSPORT)


def test_six_to_nine_alnum_is_passport():
    assert classify_identifier("A12345")[1] == PASSPORT      # 6
    assert classify_identifier("AB1234567")[1] == PASSPORT   # 9


@pytest.mark.parametrize("bad", [
    "", "   ", "12345",          # too short
    "0790950001",               # 10 digits: not CCCD, too long for passport
    "07909500011",              # 11 digits
    "AB12345678901",            # 13 chars
    "AB-12345",                 # punctuation
    "PАSS12",                   # cyrillic char
])
def test_invalid_identifiers_raise(bad):
    with pytest.raises(ValueError):
        classify_identifier(bad)
