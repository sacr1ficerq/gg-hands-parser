# GG Hands Parser

A small, dependency-free Python module for parsing GGPoker-style hand histories into dataclasses and serializing them back to text. It targets **six-max, dollar-denominated No-Limit Texas Hold’em** histories in the format shown in [`hand.txt`](hand.txt).

## Requirements

- Python 3.10 or newer
- No third-party packages

Use the module directly from the project directory. There is no package installation step or command-line interface.

## Quick start

```python
from pathlib import Path

from parser import card_to_str, get_hand, serialize

raw = Path("hand.txt").read_text(encoding="utf-8")
hand = get_hand(raw)
if hand is None:
    raise ValueError("Unrecognized hand history")

print(hand.id)              # HD2200824209
print(hand.table_name)      # NLHBlue9
print(hand.total_pot)       # 2.45
print(hand.preflop_action)  # ('c', 'f', 'f', 'f', 'c', 'r0.20')

flop, turn, river = hand.board
if flop is not None:
    print([card_to_str(card) for card in flop])  # ['4c', 'Tc', '3h']

normalized = serialize(hand)
Path("hand.normalized.txt").write_text(normalized, encoding="utf-8")
```

Pass one hand history at a time to `get_hand()`; split multi-hand files before parsing.

## API

| Function | Description |
| --- | --- |
| `get_hand(text: str) -> Hand \| None` | Parse a single hand history. Returns `None` for empty input and some unrecognized formats; malformed input can also raise exceptions. |
| `serialize(hand) -> str` | Reconstruct a normalized hand history from a `Hand` instance. |
| `get_card(text: str \| None) -> Card \| None` | Convert a two-character card such as `"As"` into a `Card`. Returns `None` for `None`. |
| `card_to_str(card: Card) -> str` | Convert a `Card` back to its two-character representation. |

### Hand data

`Hand` and `Card` are dataclasses defined in [`parser.py`](parser.py).

| Fields | Contents |
| --- | --- |
| `raw_data` | Original input text. |
| `id`, `timestamp`, `table_name` | Hand identifier, timezone-naive `datetime`, and table name. |
| `sb`, `bb` | Small and big blind amounts as floats. |
| `btn_seat`, `sb_seat`, `bb_seat` | One-based seat numbers. |
| `names`, `stacks` | Six-element tuples of player names and starting stacks; empty seats use `None`. |
| `preflop_action`, `flop_action`, `turn_action`, `river_action` | Per-seat action strings, or `None` when no actions were captured for that street. |
| `board` | `(flop, turn, river)`, where the flop is a three-card tuple and missing streets are `None`. |
| `showdown` | Per-seat collection strings, such as `"collected $2.33"`, or `None` when no showdown section was parsed. |
| `total_pot`, `rake`, `jackpot`, `bingo`, `fortune`, `tax` | Monetary amounts from the summary, stored as floats. |
| `results` | Per-seat summary text, such as `"showed [Kd 7d] and lost"`; defaults to an empty string. |
| `holdings` | Per-seat two-card tuples extracted from summary lines containing `showed`; otherwise `None`. |
| `in_hand` | Per-seat flags set to `False` for recognized folded results. All flags initially default to `True`, including empty seats. |

All per-seat tuples have six entries in seat order: **index `0` corresponds to seat `1`**.

### Action encoding

Each street stores a six-element tuple. A player's actions are concatenated in the order they occurred; `None` means no action was captured for that seat.

| Token | Meaning |
| --- | --- |
| `f` | Fold |
| `x` | Check |
| `c` | Call; the amount is inferred during serialization |
| `b5.07` | Bet $5.07 |
| `r20.99` | Raise **to** $20.99 |

For example, `"xr20.99"` means check, then raise to $20.99, and `"b5.07c"` means bet $5.07, then call. Bet and raise amounts are formatted to two decimal places.

### Card encoding

`Card(suit, nominal)` stores zero-based integer indices. Suits use `"shdc"` (spades, hearts, diamonds, clubs). The current rank lookup is `"23456789TJKQA"`; notably, its order is **J, K, Q**, so `nominal` should not be treated as a conventional poker-strength ranking. Use `get_card()` and `card_to_str()` to convert card notation.

## Format and limitations

- Input must use the expected `Poker Hand #...: Hold'em No Limit (...)` header and `Table '...' 6-max Seat #... is the button` line.
- Summary totals are recognized in the order `Total pot`, `Rake`, `Jackpot`, `Bingo`, `Fortune`, and `Tax`. Unrecognized totals leave the corresponding fields at their default zero values.
- Action parsing handles folds, checks, calls, bets, and raises in the expected seat order. All-in suffixes, side pots, antes, tournament formats, and other history variants are not explicitly supported.
- Hole cards come from recognized `showed` summary lines. `Dealt to` lines do not populate `holdings`.
- Serialization normalizes whitespace and monetary formatting, reconstructs call amounts and action order, and does not preserve every input line. Keep `raw_data` when the exact original text is needed.

## Project files

- [`parser.py`](parser.py): dataclasses, parser, card helpers, and serializer.
- [`hand.txt`](hand.txt): sample hand history for trying the module.
