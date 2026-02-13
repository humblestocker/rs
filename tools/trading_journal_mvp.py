#!/usr/bin/env python3
"""Local-first trading journal automation MVP.

Features:
- Capture trade plans/executions with position rules.
- Build daily one-page portfolio snapshot.
- Generate next-step alerts per ticker.
- Export Telegram-friendly report text.

This script is intentionally stdlib-only for easy Windows deployment.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

DB_PATH = Path("DATA/trading_journal.db")


SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_time TEXT NOT NULL,
    ticker TEXT NOT NULL,
    side TEXT NOT NULL CHECK(side IN ('BUY','SELL')),
    price REAL NOT NULL,
    qty REAL NOT NULL,
    unit_target INTEGER NOT NULL,
    capital_target_krw REAL NOT NULL,
    loss_cut_pct REAL NOT NULL,
    split_plan TEXT NOT NULL,
    rationale TEXT,
    emotion_note TEXT,
    review TEXT,
    screenshot_link TEXT,
    source TEXT DEFAULT 'manual'
);
"""


@dataclass
class Position:
    ticker: str
    buy_qty: float
    sell_qty: float
    buy_value: float
    sell_value: float
    unit_target: int
    capital_target_krw: float
    loss_cut_pct: float
    split_plan: str

    @property
    def open_qty(self) -> float:
        return self.buy_qty - self.sell_qty

    @property
    def avg_buy(self) -> float:
        return self.buy_value / self.buy_qty if self.buy_qty else 0.0

    @property
    def realized_pnl(self) -> float:
        return self.sell_value - (self.avg_buy * self.sell_qty if self.buy_qty else 0.0)

    @property
    def invested(self) -> float:
        return self.avg_buy * self.open_qty if self.open_qty > 0 else 0.0

    @property
    def progress_pct(self) -> float:
        if self.capital_target_krw <= 0:
            return 0.0
        return max(0.0, min(100.0, self.invested / self.capital_target_krw * 100))


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute(SCHEMA)
    conn.commit()
    return conn


def add_trade(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    trade_time = args.trade_time or dt.datetime.now().isoformat(timespec="minutes")
    conn.execute(
        """
        INSERT INTO trades (
            trade_time, ticker, side, price, qty, unit_target, capital_target_krw,
            loss_cut_pct, split_plan, rationale, emotion_note, review, screenshot_link, source
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            trade_time,
            args.ticker.upper(),
            args.side.upper(),
            args.price,
            args.qty,
            args.unit_target,
            args.capital_target_krw,
            args.loss_cut_pct,
            args.split_plan,
            args.rationale,
            args.emotion_note,
            args.review,
            args.screenshot_link,
            args.source,
        ),
    )
    conn.commit()


def rows_to_positions(rows: Iterable[sqlite3.Row]) -> Dict[str, Position]:
    pos: Dict[str, Position] = {}
    for r in rows:
        ticker = r["ticker"]
        p = pos.get(ticker)
        if p is None:
            p = Position(
                ticker=ticker,
                buy_qty=0,
                sell_qty=0,
                buy_value=0,
                sell_value=0,
                unit_target=r["unit_target"],
                capital_target_krw=r["capital_target_krw"],
                loss_cut_pct=r["loss_cut_pct"],
                split_plan=r["split_plan"],
            )
            pos[ticker] = p
        if r["side"] == "BUY":
            p.buy_qty += r["qty"]
            p.buy_value += r["qty"] * r["price"]
        else:
            p.sell_qty += r["qty"]
            p.sell_value += r["qty"] * r["price"]
    return pos


def load_positions(conn: sqlite3.Connection) -> Dict[str, Position]:
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM trades ORDER BY trade_time ASC, id ASC"
    ).fetchall()
    return rows_to_positions(rows)


def load_latest_prices(path: Optional[str]) -> Dict[str, float]:
    if not path:
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {k.upper(): float(v) for k, v in data.items()}


def build_snapshot(positions: Dict[str, Position], prices: Dict[str, float]) -> List[dict]:
    snapshot = []
    for ticker, p in sorted(positions.items()):
        mkt = prices.get(ticker)
        unrealized = None
        if mkt is not None and p.open_qty > 0:
            unrealized = (mkt - p.avg_buy) * p.open_qty
        snapshot.append(
            {
                "ticker": ticker,
                "open_qty": round(p.open_qty, 4),
                "avg_buy": round(p.avg_buy, 2),
                "invested": round(p.invested, 0),
                "target": round(p.capital_target_krw, 0),
                "progress_pct": round(p.progress_pct, 1),
                "loss_cut_price": round(p.avg_buy * (1 - p.loss_cut_pct / 100), 2)
                if p.avg_buy
                else 0,
                "split_plan": p.split_plan,
                "realized_pnl": round(p.realized_pnl, 0),
                "unrealized_pnl": round(unrealized, 0) if unrealized is not None else None,
            }
        )
    return snapshot


def suggest_actions(snapshot: List[dict], prices: Dict[str, float]) -> List[str]:
    alerts: List[str] = []
    for row in snapshot:
        ticker = row["ticker"]
        price = prices.get(ticker)
        if row["open_qty"] <= 0:
            alerts.append(f"{ticker}: 포지션 없음. 신규 시나리오 재작성 권장")
            continue
        if row["progress_pct"] < 60:
            alerts.append(f"{ticker}: 투입률 {row['progress_pct']}% (계획 대비 낮음). 분할매수 다음 트리거 점검")
        if row["progress_pct"] >= 100:
            alerts.append(f"{ticker}: 목표 투입 완료. 신규 매수 제한/청산 전략 점검")
        if price is not None and price <= row["loss_cut_price"]:
            alerts.append(f"{ticker}: 현재가 {price:.2f} ≤ 손절가 {row['loss_cut_price']:.2f}. 손절 규칙 확인")
    return alerts


def export_markdown(snapshot: List[dict], alerts: List[str], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# Daily Portfolio One-Page ({dt.date.today().isoformat()})",
        "",
        "## Positions",
        "",
        "| Ticker | Open Qty | Avg Buy | Invested(KRW) | Target(KRW) | Progress | Loss Cut | Realized | Unrealized |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in snapshot:
        lines.append(
            f"| {r['ticker']} | {r['open_qty']} | {r['avg_buy']} | {int(r['invested'])} | {int(r['target'])} | {r['progress_pct']}% | {r['loss_cut_price']} | {int(r['realized_pnl'])} | {r['unrealized_pnl'] if r['unrealized_pnl'] is not None else '-'} |"
        )
    lines.extend(["", "## Next Step Alerts", ""])
    if alerts:
        lines.extend([f"- {a}" for a in alerts])
    else:
        lines.append("- 특이사항 없음")
    output.write_text("\n".join(lines), encoding="utf-8")


def cmd_snapshot(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    positions = load_positions(conn)
    prices = load_latest_prices(args.price_json)
    snapshot = build_snapshot(positions, prices)
    alerts = suggest_actions(snapshot, prices)
    export_markdown(snapshot, alerts, Path(args.output))
    print(f"saved: {args.output}")


def cmd_init(conn: sqlite3.Connection, _: argparse.Namespace) -> None:
    conn.execute(SCHEMA)
    conn.commit()
    print(f"initialized: {DB_PATH}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Trading journal MVP")
    p.add_argument("--db", default=str(DB_PATH), help="SQLite file path")

    sub = p.add_subparsers(dest="command", required=True)

    s_init = sub.add_parser("init", help="initialize database")
    s_init.set_defaults(func=cmd_init)

    s_add = sub.add_parser("add", help="add one trade record")
    s_add.add_argument("--trade-time", help="ISO datetime, default now")
    s_add.add_argument("--ticker", required=True)
    s_add.add_argument("--side", choices=["BUY", "SELL", "buy", "sell"], required=True)
    s_add.add_argument("--price", type=float, required=True)
    s_add.add_argument("--qty", type=float, required=True)
    s_add.add_argument("--unit-target", type=int, required=True)
    s_add.add_argument("--capital-target-krw", type=float, required=True)
    s_add.add_argument("--loss-cut-pct", type=float, default=10.0)
    s_add.add_argument("--split-plan", default="5:3:2")
    s_add.add_argument("--rationale", default="")
    s_add.add_argument("--emotion-note", default="")
    s_add.add_argument("--review", default="")
    s_add.add_argument("--screenshot-link", default="")
    s_add.add_argument("--source", default="manual")
    s_add.set_defaults(func=add_trade)

    s_snapshot = sub.add_parser("snapshot", help="build daily one-page markdown")
    s_snapshot.add_argument("--price-json", help="JSON path: {\"005930\": 75400}")
    s_snapshot.add_argument("--output", default="DATA/daily_portfolio.md")
    s_snapshot.set_defaults(func=cmd_snapshot)

    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    conn = connect(Path(args.db))
    args.func(conn, args)


if __name__ == "__main__":
    main()
