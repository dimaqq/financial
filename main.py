from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal


Action = Literal["Buy", "Sell", "Split"]


@dataclass
class Transaction:
    date: str                 # "2025-10-17"
    action: Action            # "Buy", "Sell", or "Split"
    quantity: Decimal         # shares bought/sold; for split, use multiplier numerator
    net_amount: Decimal       # trade cash amount in original currency, including fees
    fx: Decimal = Decimal("1")  # currency -> JPY rate; use 1 if already JPY
    note: str = ""


@dataclass
class LotState:
    shares: Decimal = Decimal("0")
    basis_jpy: Decimal = Decimal("0")  # total remaining acquisition cost

    @property
    def avg_basis_per_share(self) -> Decimal:
        if self.shares == 0:
            return Decimal("0")
        return self.basis_jpy / self.shares


def yen(x: Decimal) -> Decimal:
    return x.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def process_transactions(transactions: list[Transaction]) -> list[dict]:
    txs = sorted(transactions, key=lambda t: datetime.fromisoformat(t.date))
    state = LotState()
    rows = []

    for tx in txs:
        before_shares = state.shares
        before_basis = state.basis_jpy
        before_avg = state.avg_basis_per_share

        realized_gain = None
        proceeds_jpy = None
        basis_sold_jpy = None

        if tx.action == "Buy":
            # net_amount should be positive cash paid, including fees
            cost_jpy = tx.net_amount * tx.fx
            state.shares += tx.quantity
            state.basis_jpy += cost_jpy

        elif tx.action == "Sell":
            # net_amount should be positive cash received, after fees
            if tx.quantity > state.shares:
                raise ValueError(
                    f"{tx.date}: selling {tx.quantity} but only have {state.shares}"
                )

            proceeds_jpy = tx.net_amount * tx.fx
            basis_sold_jpy = before_avg * tx.quantity
            realized_gain = proceeds_jpy - basis_sold_jpy

            state.shares -= tx.quantity
            state.basis_jpy -= basis_sold_jpy

            # avoid tiny residue from Decimal division
            if state.shares == 0:
                state.basis_jpy = Decimal("0")

        elif tx.action == "Split":
            # Example: 10-for-1 split: quantity=10, net_amount=0
            # Total basis unchanged; shares multiplied.
            if tx.quantity <= 0:
                raise ValueError(f"{tx.date}: split multiplier must be positive")
            state.shares *= tx.quantity

        else:
            raise ValueError(f"Unknown action: {tx.action}")

        rows.append({
            "date": tx.date,
            "action": tx.action,
            "quantity": tx.quantity,
            "net_amount": tx.net_amount,
            "fx": tx.fx,
            "before_shares": before_shares,
            "before_basis_jpy": yen(before_basis),
            "before_avg_jpy": before_avg,
            "proceeds_jpy": yen(proceeds_jpy) if proceeds_jpy is not None else None,
            "basis_sold_jpy": yen(basis_sold_jpy) if basis_sold_jpy is not None else None,
            "realized_gain_jpy": yen(realized_gain) if realized_gain is not None else None,
            "after_shares": state.shares,
            "after_basis_jpy": yen(state.basis_jpy),
            "after_avg_jpy": state.avg_basis_per_share,
            "note": tx.note,
        })

    return rows


def main():
    transactions = [
        Transaction("2018-01-10", "Buy",  Decimal("5900"),  Decimal("9945.42")),
        Transaction("2018-10-01", "Buy",  Decimal("10000"), Decimal("16154.28")),
        Transaction("2020-11-06", "Buy",  Decimal("2200"),  Decimal("4230.93")),
        Transaction("2025-10-17", "Sell", Decimal("18000"), Decimal("25830.63")),
    ]

    rows = process_transactions(transactions)

    for row in rows:
        print(row)

    last = rows[-1]
    print("End shares:", last["after_shares"])
    print("End basis:", last["after_basis_jpy"])
    print("Avg basis/share:", last["after_avg_jpy"])


if __name__ == "__main__":
    main()
