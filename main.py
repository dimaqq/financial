from __future__ import annotations

import csv
import shelve
from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING
from typing import Literal

import typer


type Action = Literal["Buy", "Sell", "Split"]


@dataclass(frozen=True)
class State:
    shares: Decimal = Decimal("0")
    unit_basis_jpy: Decimal = Decimal("0")  # rounded-up yen/share

    @property
    def total_basis_jpy(self) -> Decimal:
        return self.shares * self.unit_basis_jpy

    def __str__(self):
        return f"<S {self.shares} shares {self.unit_basis_jpy} b/sh {self.total_basis_jpy} basis>"


def coerce(x: str | int | float) -> Decimal:
    return Decimal(str(x).replace(",", ""))


def ceil_yen(x: Decimal) -> Decimal:
    return x.quantize(Decimal("1"), rounding=ROUND_CEILING)


def transact(
    state: State,
    date: str,
    action: Action,
    quantity: str | int | float,
    net_amount: str | int | float = "0",
    fx_rate: str | int | float = "1",
    note: str = "",
) -> State:
    q = coerce(quantity)
    net = coerce(net_amount)
    fx = coerce(fx_rate)
    amount_jpy = net * fx

    #print(f"\n{date} {action.upper()} {q} {note}")

    if action == "Buy":
        if q <= 0:
            raise ValueError("Buy quantity must be positive")

        new_shares = state.shares + q
        new_total_basis = state.total_basis_jpy + amount_jpy
        new_unit_basis = ceil_yen(new_total_basis / new_shares)

        new_state = State(new_shares, new_unit_basis)

        print(f"  Buy cost: {ceil_yen(amount_jpy)} JPY")
        return new_state

    if action == "Sell":
        if q <= 0:
            raise ValueError("Sell quantity must be positive")
        if q > state.shares:
            raise ValueError(f"selling {q}, but only have {state.shares}")

        proceeds_jpy = amount_jpy
        basis_sold_jpy = state.unit_basis_jpy * q
        gain_jpy = proceeds_jpy - basis_sold_jpy

        new_shares = state.shares - q
        new_state = State() if new_shares == 0 else State(new_shares, state.unit_basis_jpy)

        print(f"  proceeds:   {ceil_yen(proceeds_jpy)} JPY")
        print(f"  basis sold: {basis_sold_jpy} JPY")
        print(f"  gain/loss:  {ceil_yen(gain_jpy)} JPY")
        return new_state

    if action == "Split":
        if q <= 0:
            raise ValueError("Split multiplier must be positive")

        new_state = State(
            shares=state.shares * q,
            unit_basis_jpy=ceil_yen(state.unit_basis_jpy / q),
        )

        print(f"  Split multiplier: {q}")
        return new_state

    raise ValueError(f"unknown action: {action}")


def main(filename: str, stock: str, mode: Literal["Cash", "CDP", "SRS"] = "Cash"):
    with shelve.open('rates.db') as db:
        if not db:
            data = csv.reader(open("Mizuho fx quote.csv"))
            head = next(data)
            currency_index = {tag: i for i, tag in enumerate(head)}
            currencies = {tag: {} for tag in "EUR USD SGD".split()}
            for row in data:
                bits = ["%02d" % i for i in map(int, row[0].split("/"))]
                date = "-".join(bits)
                for c in currencies:
                    currencies[c][date] = row[currency_index[c]]
            db.update(currencies)

        with open(filename) as raw:
            def parser():
                timestamp = next(raw).strip()
                print("raw file", timestamp)
                _head = next(raw).strip()
                # [(0, 'Date'),
                # (1, 'Account'), (2, 'Code'), (3, 'Name'), (4, 'Action'),
                # (5, 'Quantity'), (6, 'Price'), (7, 'Nett amount'), (8, 'Contract/Reference')]
                while True:
                    try:
                        main = next(raw).strip()
                        if not main.startswith('"'):
                            continue
                        tail = next(raw).strip()
                        yield f"{main}{tail}"
                    except StopIteration:
                        return

            data = csv.reader(parser())
            txs = []
            for row in data:
                d,m,y = map(int, row[0].split("/"))
                date = f"{y}-{m:02d}-{d:02d}"
                if mode != row[1]:
                    continue
                if stock != row[2]:
                    continue
                action = row[4]
                # FIXME parse split actions by:
                # Stock Split (Debit) <N>:1
                if action in ("Buy", "Sell"):
                    quantity = row[5]
                    net_amount=row[7]
                    fx_rate=db[row[18]][date]
                elif action.startswith("Stock Split (Debit) "):
                    quantity, den = map(int, action.split()[3].split(":"))
                    assert den == 1
                    action = "Split"
                    net_amount = 0
                    fx_rate = 0
                elif action == "Stock Split (Credit)":
                    continue
                elif action.startswith("Avg cost price adjustment"):
                    continue
                elif action.startswith("Cash Dividend"):
                    continue
                else:
                    raise ValueError(f"bad {action=}")
                txs.append(dict(date=date, action=action, quantity=quantity,
                                net_amount=net_amount, fx_rate=fx_rate))

            txs.sort(key=lambda d: d["date"])

    s = State()
    for tx in txs:
        print(tx)
        s = transact(s, **tx)
        print(s)
        print()


if __name__ == "__main__":
    typer.run(main)
