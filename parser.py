from dataclasses import dataclass
from datetime import datetime
import re


@dataclass
class Card:
    suit: int
    nominal: int


suits = "shdc"
nominals = "23456789TJKQA"


def get_card(s: str | None) -> Card | None:
    if s is None:
        return None
    assert len(s) == 2

    nominal = nominals.index(s[0])
    suit = suits.index(s[1])
    return Card(suit, nominal)


def card_to_str(card: Card) -> str:
    return f"{nominals[card.nominal]}{suits[card.suit]}"


Holding = tuple[Card, Card]

Action6 = tuple[str | None, str | None, str | None, str | None, str | None, str | None]

Seat6Bool = tuple[bool, bool, bool, bool, bool, bool]
Seat6Result = tuple[str, str, str, str, str, str]
Seat6Holding = tuple[
    Holding | None,
    Holding | None,
    Holding | None,
    Holding | None,
    Holding | None,
    Holding | None,
]


# This is assumed to be Texal Holdem 6 max hand played in dollars
@dataclass
class Hand:
    raw_data: str
    timestamp: datetime
    id: str
    table_name: str

    sb: float
    bb: float

    btn_seat: int

    names: tuple[
        str | None,
        str | None,
        str | None,
        str | None,
        str | None,
        str | None,
    ]

    stacks: tuple[
        float | None,
        float | None,
        float | None,
        float | None,
        float | None,
        float | None,
    ]

    sb_seat: int
    bb_seat: int

    in_hand: Seat6Bool

    # preflop
    # example: ["xr20.99", "xf", "b5.07c", "f", None, "cf"]
    preflop_action: Action6 | None
    flop_action: Action6 | None
    turn_action: Action6 | None
    river_action: Action6 | None

    board: tuple[
        tuple[Card, Card, Card] | None,
        Card | None,
        Card | None,
    ]

    # who won
    showdown: (
        tuple[str | None, str | None, str | None, str | None, str | None, str | None]
        | None
    )

    # summary
    total_pot: float
    rake: float
    jackpot: float
    bingo: float
    fortune: float
    tax: float

    # example:
    #  showed [Kd 7d] and lost
    #  folded before Flop (didn't bet)
    #  folded before Flop (didn't bet)
    #  folded before Flop (didn't bet)
    #  folded on the River
    #  showed [7c 7h] and won ($2.33)
    results: Seat6Result
    holdings: Seat6Holding


SEAT_RE = re.compile(r"^Seat (\d+): (.+) \(\$(\d+(?:\.\d+)?) in chips\)$")
POST_RE = re.compile(r"^(.+): posts (small blind|big blind) \$(\d+(?:\.\d+)?)$")
ACTION_RE = re.compile(
    r"^(.+): (folds|checks|calls \$(\d+(?:\.\d+)?)|bets \$(\d+(?:\.\d+)?)|raises \$(\d+(?:\.\d+)?) to \$(\d+(?:\.\d+)?))$"
)
SHOWDOWN_COLLECT_RE = re.compile(r"^(.+) collected \$(\d+(?:\.\d+)?) from pot$")
SUMMARY_RE = re.compile(
    r"^Total pot \$(\d+(?:\.\d+)?) \| Rake \$(\d+(?:\.\d+)?) \| Jackpot \$(\d+(?:\.\d+)?) \| Bingo \$(\d+(?:\.\d+)?) \| Fortune \$(\d+(?:\.\d+)?) \| Tax \$(\d+(?:\.\d+)?)$"
)
SHOWED_RE = re.compile(
    r"^Seat (\d+): .+ showed \[([2-9TJQKA][shdc]) ([2-9TJQKA][shdc])\] and (lost|won(?: \(\$\d+(?:\.\d+)?\))?)$"
)
RESULT_RE = re.compile(
    r"^Seat (\d+): .+?((?: showed \[[^\]]+\] and (?:lost|won(?: \(\$\d+(?:\.\d+)?\))?))|(?: folded before Flop \(didn't bet\))|(?: folded on the (?:Flop|Turn|River)))$"
)


def _money(v: float) -> str:
    return f"{v:.2f}"


def _seat_tuple(values: list):
    return tuple(values)  # type: ignore[return-value]


def _iter_seats(start_seat: int):
    seat = start_seat
    for _ in range(6):
        yield seat
        seat = seat % 6 + 1


def _next_active(start_seat: int, active: list[bool]) -> int:
    for seat in _iter_seats(start_seat):
        if active[seat - 1]:
            return seat
    raise ValueError("no active seat found")


def _street_start_seat(hand: Hand, street: str, active: list[bool]) -> int:
    if street == "preflop":
        return _next_active(hand.bb_seat % 6 + 1, active)
    return _next_active(hand.btn_seat % 6 + 1, active)


def _starting_active(hand: Hand) -> list[bool]:
    return [name is not None for name in hand.names]


def _apply_folds(active: list[bool], action6: Action6 | None) -> list[bool]:
    next_active = active[:]
    if action6 is None:
        return next_active
    for seat, action in enumerate(action6, start=1):
        for kind, _ in _parse_action_tokens(action):
            if kind == "f":
                next_active[seat - 1] = False
    return next_active


def _active_for_street(hand: Hand, street: str) -> list[bool]:
    active = _starting_active(hand)
    if street == "preflop":
        return active
    active = _apply_folds(active, hand.preflop_action)
    if street == "flop":
        return active
    active = _apply_folds(active, hand.flop_action)
    if street == "turn":
        return active
    active = _apply_folds(active, hand.turn_action)
    return active


def _parse_action_tokens(action: str | None) -> list[tuple[str, float | None]]:
    if action is None:
        return []

    tokens: list[tuple[str, float | None]] = []
    i = 0
    while i < len(action):
        kind = action[i]
        if kind in "fxc":
            tokens.append((kind, None))
            i += 1
            continue
        if kind in "br":
            j = i + 1
            while j < len(action) and (action[j].isdigit() or action[j] == "."):
                j += 1
            tokens.append((kind, float(action[i + 1 : j])))
            i = j
            continue
        raise ValueError(f"unknown action token in {action!r}")
    return tokens


def _append_action(actions: list[str | None], seat: int, token: str) -> None:
    current = actions[seat - 1]
    actions[seat - 1] = token if current is None else current + token


def _capture_street_actions(
    lines: list[str], start: int, hand: Hand, street: str
) -> tuple[Action6 | None, int]:
    active = _active_for_street(hand, street)
    contributions = [0.0] * 6
    if street == "preflop":
        contributions[hand.sb_seat - 1] = hand.sb
        contributions[hand.bb_seat - 1] = hand.bb

    pending = {seat for seat in range(1, 7) if active[seat - 1]}
    if street == "preflop":
        pending.discard(hand.sb_seat)
        pending.discard(hand.bb_seat)
        if active[hand.sb_seat - 1]:
            pending.add(hand.sb_seat)
        if active[hand.bb_seat - 1]:
            pending.add(hand.bb_seat)

    actions: list[str | None] = [None] * 6
    seat = _street_start_seat(hand, street, active)
    idx = start

    while idx < len(lines):
        line = lines[idx]
        if line.startswith("*** "):
            break
        match = ACTION_RE.match(line)
        if not match:
            idx += 1
            continue

        name, full_action, call_amount, bet_amount, raise_amount, raise_to = (
            match.groups()
        )
        current_seat = hand.names.index(name) + 1
        while not active[seat - 1]:
            seat = seat % 6 + 1
        if current_seat != seat:
            raise ValueError(
                f"unexpected action order: expected seat {seat}, got seat {current_seat}"
            )

        if full_action == "folds":
            _append_action(actions, seat, "f")
            active[seat - 1] = False
            pending.discard(seat)
        elif full_action == "checks":
            _append_action(actions, seat, "x")
            pending.discard(seat)
        elif call_amount is not None:
            amount = float(call_amount)
            contributions[seat - 1] += amount
            _append_action(actions, seat, "c")
            pending.discard(seat)
        elif bet_amount is not None:
            amount = float(bet_amount)
            contributions[seat - 1] += amount
            _append_action(actions, seat, f"b{amount:.2f}")
            pending = {s for s in range(1, 7) if active[s - 1] and s != seat}
        else:
            to_amount = float(raise_to)
            contributions[seat - 1] = to_amount
            _append_action(actions, seat, f"r{to_amount:.2f}")
            pending = {s for s in range(1, 7) if active[s - 1] and s != seat}

        idx += 1
        if not pending:
            break
        seat = seat % 6 + 1

    return (_seat_tuple(actions) if any(v is not None for v in actions) else None), idx


def _action_line(
    name: str, token: tuple[str, float | None], to_call: float, contributed: float
) -> str:
    kind, amount = token
    if kind == "f":
        return f"{name}: folds"
    if kind == "x":
        return f"{name}: checks"
    if kind == "c":
        call_amount = max(to_call - contributed, 0.0)
        return f"{name}: calls ${_money(call_amount)}"
    if kind == "b":
        assert amount is not None
        return f"{name}: bets ${_money(amount)}"
    if kind == "r":
        assert amount is not None
        raise_by = amount - to_call
        return f"{name}: raises ${_money(raise_by)} to ${_money(amount)}"
    raise ValueError(f"unknown token {kind}")


def _serialize_street_actions(
    hand: Hand, street: str, action6: Action6 | None
) -> list[str]:
    if action6 is None:
        return []

    tokens = [_parse_action_tokens(action) for action in action6]
    token_idx = [0] * 6
    active = _active_for_street(hand, street)
    contributed = [0.0] * 6
    to_call = hand.bb if street == "preflop" else 0.0
    if street == "preflop":
        contributed[hand.sb_seat - 1] = hand.sb
        contributed[hand.bb_seat - 1] = hand.bb

    pending = {seat for seat in range(1, 7) if active[seat - 1]}
    if street == "preflop":
        pending.discard(hand.sb_seat)
        pending.discard(hand.bb_seat)
        if active[hand.sb_seat - 1]:
            pending.add(hand.sb_seat)
        if active[hand.bb_seat - 1]:
            pending.add(hand.bb_seat)

    seat = _street_start_seat(hand, street, active)
    lines: list[str] = []
    while pending:
        if not active[seat - 1]:
            seat = seat % 6 + 1
            continue

        idx = token_idx[seat - 1]
        seat_tokens = tokens[seat - 1]
        if idx >= len(seat_tokens):
            raise ValueError(f"missing action token for seat {seat} on {street}")

        token = seat_tokens[idx]
        token_idx[seat - 1] += 1
        name = hand.names[seat - 1]
        if name is None:
            raise ValueError(f"missing player name for seat {seat}")
        lines.append(_action_line(name, token, to_call, contributed[seat - 1]))

        kind, amount = token
        if kind == "f":
            active[seat - 1] = False
            pending.discard(seat)
        elif kind == "x":
            pending.discard(seat)
        elif kind == "c":
            contributed[seat - 1] = to_call
            pending.discard(seat)
        elif kind == "b":
            assert amount is not None
            contributed[seat - 1] += amount
            to_call = contributed[seat - 1]
            pending = {s for s in range(1, 7) if active[s - 1] and s != seat}
        elif kind == "r":
            assert amount is not None
            contributed[seat - 1] = amount
            to_call = amount
            pending = {s for s in range(1, 7) if active[s - 1] and s != seat}

        seat = seat % 6 + 1

    return lines


def get_hand(s: str) -> Hand | None:
    lines = [line.rstrip() for line in s.strip().splitlines()]
    if not lines:
        return None

    header = re.match(
        r"^Poker Hand #(\S+): Hold'em No Limit \(\$(\d+(?:\.\d+)?)/\$(\d+(?:\.\d+)?)\) - (\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2})$",
        lines[0],
    )
    if not header:
        return None
    hand_id, sb, bb, timestamp = header.groups()

    table_line = re.match(r"^Table '(.+)' 6-max Seat #(\d+) is the button$", lines[1])
    if not table_line:
        return None
    table_name, btn_seat = table_line.groups()

    names: list[str | None] = [None] * 6
    stacks: list[float | None] = [None] * 6
    idx = 2
    while idx < len(lines) and lines[idx] == "":
        idx += 1
    while idx < len(lines) and lines[idx].startswith("Seat "):
        match = SEAT_RE.match(lines[idx])
        if not match:
            return None
        seat, name, stack = match.groups()
        names[int(seat) - 1] = name
        stacks[int(seat) - 1] = float(stack)
        idx += 1

    while idx < len(lines) and lines[idx] == "":
        idx += 1

    sb_seat = 0
    bb_seat = 0
    while idx < len(lines):
        match = POST_RE.match(lines[idx])
        if not match:
            break
        name, blind_kind, _ = match.groups()
        seat = names.index(name) + 1
        if blind_kind == "small blind":
            sb_seat = seat
        else:
            bb_seat = seat
        idx += 1

    while idx < len(lines) and lines[idx] != "*** HOLE CARDS ***":
        idx += 1
    if idx >= len(lines):
        return None
    idx += 1

    while idx < len(lines) and lines[idx].startswith("Dealt to "):
        idx += 1

    hand = Hand(
        raw_data=s,
        timestamp=datetime.strptime(timestamp, "%Y/%m/%d %H:%M:%S"),
        id=hand_id,
        table_name=table_name,
        sb=float(sb),
        bb=float(bb),
        btn_seat=int(btn_seat),
        names=_seat_tuple(names),
        stacks=_seat_tuple(stacks),
        sb_seat=sb_seat,
        bb_seat=bb_seat,
        in_hand=_seat_tuple([True] * 6),
        preflop_action=None,
        flop_action=None,
        turn_action=None,
        river_action=None,
        board=(None, None, None),
        showdown=None,
        total_pot=0.0,
        rake=0.0,
        jackpot=0.0,
        bingo=0.0,
        fortune=0.0,
        tax=0.0,
        results=_seat_tuple([""] * 6),
        holdings=_seat_tuple([None] * 6),
    )

    preflop_action, idx = _capture_street_actions(lines, idx, hand, "preflop")
    hand.preflop_action = preflop_action

    flop: tuple[Card, Card, Card] | None = None
    turn: Card | None = None
    river: Card | None = None
    flop_action = turn_action = river_action = None

    while idx < len(lines):
        line = lines[idx]
        if line.startswith("*** FLOP *** "):
            cards = re.findall(r"\[([^\]]+)\]", line)[0].split()
            flop = (get_card(cards[0]), get_card(cards[1]), get_card(cards[2]))  # type: ignore[arg-type]
            idx += 1
            flop_action, idx = _capture_street_actions(lines, idx, hand, "flop")
            hand.flop_action = flop_action
            continue
        if line.startswith("*** TURN *** "):
            cards = re.findall(r"\[([^\]]+)\]", line)
            turn = get_card(cards[1])
            idx += 1
            turn_action, idx = _capture_street_actions(lines, idx, hand, "turn")
            hand.turn_action = turn_action
            continue
        if line.startswith("*** RIVER *** "):
            cards = re.findall(r"\[([^\]]+)\]", line)
            river = get_card(cards[1])
            idx += 1
            river_action, idx = _capture_street_actions(lines, idx, hand, "river")
            hand.river_action = river_action
            continue
        if line == "*** SHOWDOWN ***":
            idx += 1
            showdown = [None] * 6
            while idx < len(lines):
                match = SHOWDOWN_COLLECT_RE.match(lines[idx])
                if not match:
                    break
                name, amount = match.groups()
                showdown[names.index(name)] = f"collected ${amount}"
                idx += 1
            hand.showdown = _seat_tuple(showdown)
            continue
        if line == "*** SUMMARY ***":
            idx += 1
            break
        idx += 1

    if idx < len(lines):
        match = SUMMARY_RE.match(lines[idx])
        if match:
            total_pot, rake, jackpot, bingo, fortune, tax = match.groups()
            hand.total_pot = float(total_pot)
            hand.rake = float(rake)
            hand.jackpot = float(jackpot)
            hand.bingo = float(bingo)
            hand.fortune = float(fortune)
            hand.tax = float(tax)
            idx += 1

    if idx < len(lines) and lines[idx].startswith("Board "):
        idx += 1

    results = [""] * 6
    holdings: list[Holding | None] = [None] * 6
    in_hand = [True] * 6
    while idx < len(lines):
        line = lines[idx]
        match = RESULT_RE.match(line)
        if not match:
            idx += 1
            continue
        seat = int(match.group(1))
        result = match.group(2)
        results[seat - 1] = result.strip()
        if "folded" in result:
            in_hand[seat - 1] = False
        showed = SHOWED_RE.match(line)
        if showed:
            _, c1, c2, _ = showed.groups()
            holdings[seat - 1] = (get_card(c1), get_card(c2))  # type: ignore[arg-type]
        idx += 1

    hand.in_hand = _seat_tuple(in_hand)
    hand.preflop_action = preflop_action
    hand.flop_action = flop_action
    hand.turn_action = turn_action
    hand.river_action = river_action
    hand.board = (flop, turn, river)
    hand.results = _seat_tuple(results)
    hand.holdings = _seat_tuple(holdings)
    return hand


def serialize(Hand) -> str:
    hand = Hand
    lines = [
        f"Poker Hand #{hand.id}: Hold'em No Limit (${_money(hand.sb)}/${_money(hand.bb)}) - {hand.timestamp.strftime('%Y/%m/%d %H:%M:%S')}",
        f"Table '{hand.table_name}' 6-max Seat #{hand.btn_seat} is the button",
        "",
    ]

    for seat in range(1, 7):
        name = hand.names[seat - 1]
        stack = hand.stacks[seat - 1]
        if name is None or stack is None:
            continue
        lines.append(f"Seat {seat}: {name} (${_money(stack)} in chips)")

    lines.append("")
    lines.append(
        f"{hand.names[hand.sb_seat - 1]}: posts small blind ${_money(hand.sb)}"
    )
    lines.append(f"{hand.names[hand.bb_seat - 1]}: posts big blind ${_money(hand.bb)}")
    lines.append("")
    lines.append("*** HOLE CARDS ***")

    for name in hand.names:
        if name is not None:
            lines.append(f"Dealt to {name}")

    lines.append("")
    lines.extend(_serialize_street_actions(hand, "preflop", hand.preflop_action))

    flop, turn, river = hand.board
    if flop is not None:
        lines.append("")
        lines.append(f"*** FLOP *** [{' '.join(card_to_str(card) for card in flop)}]")
        lines.append("")
        lines.extend(_serialize_street_actions(hand, "flop", hand.flop_action))
    if turn is not None and flop is not None:
        lines.append("")
        lines.append(
            f"*** TURN *** [{' '.join(card_to_str(card) for card in flop)}] [{card_to_str(turn)}]"
        )
        lines.append("")
        lines.extend(_serialize_street_actions(hand, "turn", hand.turn_action))
    if river is not None and flop is not None and turn is not None:
        lines.append("")
        board4 = [*(card_to_str(card) for card in flop), card_to_str(turn)]
        lines.append(f"*** RIVER *** [{' '.join(board4)}] [{card_to_str(river)}]")
        lines.append("")
        lines.extend(_serialize_street_actions(hand, "river", hand.river_action))

    if hand.showdown and any(v is not None for v in hand.showdown):
        lines.append("")
        lines.append("*** SHOWDOWN ***")
        for seat in range(1, 7):
            result = hand.showdown[seat - 1]
            if result is not None:
                lines.append(f"{hand.names[seat - 1]} {result} from pot")

    lines.append("*** SUMMARY ***")
    lines.append(
        f"Total pot ${_money(hand.total_pot)} | Rake ${_money(hand.rake)} | Jackpot ${_money(hand.jackpot)} | Bingo ${_money(hand.bingo)} | Fortune ${_money(hand.fortune)} | Tax ${_money(hand.tax)}"
    )

    board_cards = []
    if flop is not None:
        board_cards.extend(card_to_str(card) for card in flop)
    if turn is not None:
        board_cards.append(card_to_str(turn))
    if river is not None:
        board_cards.append(card_to_str(river))
    if board_cards:
        lines.append(f"Board [{' '.join(board_cards)}]")
        lines.append("")

    for seat in range(1, 7):
        name = hand.names[seat - 1]
        if name is None:
            continue
        suffix = ""
        if seat == hand.btn_seat:
            suffix = " (button)"
        elif seat == hand.sb_seat:
            suffix = " (small blind)"
        elif seat == hand.bb_seat:
            suffix = " (big blind)"
        result = hand.results[seat - 1]
        spacer = " " if result else ""
        lines.append(f"Seat {seat}: {name}{suffix}{spacer}{result}")

    return "\n".join(lines)
