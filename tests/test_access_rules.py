"""One test per row of the access-rule tables in the ScaNEU documentation."""
from datetime import date

from scaneu.gate.access_rules import GRANTED, NEU, NON_NEU, PENDING, UNKNOWN, Card, decide_entrance, decide_exit

TODAY = date(2026, 10, 28)
VALID = Card(user_id=1, status="Active", valid_until=date(2027, 6, 30), plates=frozenset({"ABC1234"}))
EXPIRED = Card(user_id=2, status="Active", valid_until=date(2025, 6, 30), plates=frozenset({"NEU5678"}))
BLOCKED = Card(user_id=3, status="Blocked", valid_until=date(2027, 6, 30), plates=frozenset({"XYZ9012"}))


def entrance(card=None, plate=None, card_tapped=None, known_non_neu=False):
    if card_tapped is None:
        card_tapped = card is not None
    return decide_entrance(card=card, card_tapped=card_tapped, plate=plate, known_non_neu=known_non_neu, today=TODAY)


# ---- Entrance ----

def test_neu_normal_opens():
    d = entrance(VALID, "ABC1234")
    assert (d.open_barrier, d.access_result, d.owner_type, d.flags) == (True, GRANTED, NEU, ())


def test_neu_plate_unreadable_opens_and_fills_plate_from_card():
    d = entrance(VALID, None)
    assert d.open_barrier and d.access_result == GRANTED
    assert d.plate == "ABC1234"
    assert "plate_unreadable" in d.flags


def test_valid_card_opens_even_if_plate_differs():
    d = entrance(VALID, "ZZZ0000")
    assert (d.open_barrier, d.access_result, d.owner_type, d.plate, d.flags) == (True, GRANTED, NEU, "ZZZ0000", ())


def test_expired_card_waits_for_guard():
    d = entrance(EXPIRED, "NEU5678")
    assert (d.open_barrier, d.access_result) == (False, PENDING)
    assert "card_expired" in d.flags


def test_blocked_card_waits_for_guard():
    d = entrance(BLOCKED, "XYZ9012")
    assert (d.open_barrier, d.access_result) == (False, PENDING)
    assert "card_blocked" in d.flags


def test_card_with_no_expiry_is_valid():
    card = Card(user_id=4, status="Active", valid_until=None, plates=frozenset({"AAA1111"}))
    assert entrance(card, "AAA1111").open_barrier


def test_non_neu_first_visit_waits_for_guard():
    d = entrance(None, "NEW1111")
    assert (d.open_barrier, d.access_result, d.owner_type) == (False, PENDING, NON_NEU)
    assert "first_visit" in d.flags


def test_unknown_card_is_treated_as_non_neu():
    d = entrance(None, "NEW1111", card_tapped=True)
    assert d.owner_type == NON_NEU and not d.open_barrier
    assert "unknown_card" in d.flags


def test_non_neu_returning_never_opens_automatically():
    d = entrance(None, "VIS4321", known_non_neu=True)
    assert (d.open_barrier, d.owner_type) == (False, NON_NEU)
    assert "returning" in d.flags


# ---- Exit ----

def test_exit_neu_with_open_entry_opens():
    d = decide_exit(card=VALID, plate="ABC1234", open_entry_owner=NEU, today=TODAY)
    assert (d.open_barrier, d.access_result) == (True, GRANTED)


def test_exit_non_neu_waits_for_guard():
    d = decide_exit(card=None, plate="VIS4321", open_entry_owner=NON_NEU, today=TODAY)
    assert (d.open_barrier, d.owner_type) == (False, NON_NEU)


def test_exit_without_matching_entry_is_exit_only():
    d = decide_exit(card=None, plate="GHOST01", open_entry_owner=None, today=TODAY)
    assert (d.open_barrier, d.owner_type) == (False, UNKNOWN)
    assert "exit_only" in d.flags


def test_exit_neu_vehicle_without_valid_card_waits_for_guard():
    d = decide_exit(card=None, plate="ABC1234", open_entry_owner=NEU, today=TODAY)
    assert not d.open_barrier
    assert "no_valid_card" in d.flags
