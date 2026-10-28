"""Access rules from the ScaNEU documentation, as pure functions.

Nothing here touches the database or Flask: the caller looks the card and plate
up and passes plain values in, so every row of the doc's entrance and exit
tables can be unit-tested on its own.
"""
from dataclasses import dataclass
from datetime import date

GRANTED = "Granted"
GRANTED_BY_GUARD = "Granted by guard"
PENDING = "Pending"
DENIED = "Denied"

NEU = "NEU"
NON_NEU = "Non-NEU"
UNKNOWN = "Unknown"

# Text the dashboard shows for each flag stored in vehicle_logs.flags.
FLAG_LABELS = {
    "plate_unreadable": "Plate unreadable",
    "card_expired": "Card expired",
    "card_blocked": "Card blocked",
    "unknown_card": "Unknown card",
    "first_visit": "First visit",
    "returning": "Returning visitor",
    "exit_only": "Exit only",
    "no_valid_card": "No valid card",
}


@dataclass(frozen=True)
class Card:
    """A card found in the users table, with the plates registered to its holder."""

    user_id: int
    status: str  # "Active" or "Blocked"
    valid_until: date | None
    plates: frozenset[str] = frozenset()

    def problem(self, today):
        """The flag explaining why the card is not valid today, or None if it is valid."""
        if self.status != "Active":
            return "card_blocked"
        if self.valid_until is not None and self.valid_until < today:
            return "card_expired"
        return None


@dataclass(frozen=True)
class Decision:
    open_barrier: bool
    access_result: str
    owner_type: str
    plate: str | None  # the plate to log (may be filled from the card)
    flags: tuple[str, ...] = ()
    reason: str = ""


def decide_entrance(*, card, card_tapped, plate, known_non_neu, today):
    """Entrance lane.

    A valid card opens the barrier on its own; the plate is only recorded, not
    checked against the card (team decision, replaces the doc's plate-mismatch rule).

    card          -- Card for the tapped UID, or None (no card, or UID not in the database)
    card_tapped   -- True if a UID was read, even an unknown one
    plate         -- normalized plate from the camera, or None if unreadable
    known_non_neu -- True if the plate is already in non_neu_vehicles
    """
    if card is not None:
        problem = card.problem(today)
        if problem == "card_blocked":
            return Decision(False, PENDING, NEU, plate, (problem,), "Card is blocked.")
        if problem == "card_expired":
            return Decision(False, PENDING, NEU, plate, (problem,), "Card has expired.")
        if plate is None:
            filled = next(iter(card.plates)) if len(card.plates) == 1 else None
            return Decision(
                True, GRANTED, NEU, filled, ("plate_unreadable",),
                "Valid card; plate unreadable, filled from the card.",
            )
        return Decision(True, GRANTED, NEU, plate, (), "Valid card.")

    flags = []
    if card_tapped:
        flags.append("unknown_card")
    if plate is None:
        flags.append("plate_unreadable")
    if known_non_neu:
        flags.append("returning")
        reason = "Registered visitor plate. Confirm the driver and purpose."
    else:
        flags.append("first_visit")
        reason = "New visitor. Check ID and register the plate."
    return Decision(False, PENDING, NON_NEU, plate, tuple(flags), reason)


def decide_exit(*, card, plate, open_entry_owner, today):
    """Exit lane.

    open_entry_owner -- owner_type of the open entry record found for this card or
                        plate ("NEU" / "Non-NEU"), or None if there is none
    """
    if open_entry_owner is None:
        owner = NEU if card is not None else UNKNOWN
        return Decision(False, PENDING, owner, plate, ("exit_only",), "No open entry for this card or plate.")
    if open_entry_owner == NON_NEU:
        return Decision(False, PENDING, NON_NEU, plate, (), "Visitor leaving. Confirm to open.")
    if card is not None and card.problem(today) is None:
        return Decision(True, GRANTED, NEU, plate, (), "Valid card; entry record closed.")
    return Decision(False, PENDING, NEU, plate, ("no_valid_card",), "NEU vehicle without a valid card. Confirm to open.")
