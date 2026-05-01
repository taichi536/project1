import sqlite3
import pandas as pd
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "diary.db"


def _conn():
    return sqlite3.connect(DB_PATH)


def init_db():
    with _conn() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                ticker TEXT NOT NULL,
                action TEXT NOT NULL,
                price REAL NOT NULL,
                quantity INTEGER NOT NULL,
                fee REAL DEFAULT 0,
                technical_reason TEXT,
                fundamental_reason TEXT,
                emotion TEXT,
                emotion_score INTEGER,
                stop_loss REAL,
                target_price REAL,
                notes TEXT
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                period TEXT NOT NULL,
                good_points TEXT,
                bad_points TEXT,
                lessons TEXT,
                missed_signals TEXT
            )
        """)


def add_trade(
    ticker: str,
    action: str,
    price: float,
    quantity: int,
    fee: float = 0,
    technical_reason: str = "",
    fundamental_reason: str = "",
    emotion: str = "",
    emotion_score: int = 5,
    stop_loss: float = None,
    target_price: float = None,
    notes: str = "",
):
    init_db()
    with _conn() as con:
        con.execute("""
            INSERT INTO trades
            (created_at, ticker, action, price, quantity, fee,
             technical_reason, fundamental_reason, emotion, emotion_score,
             stop_loss, target_price, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().isoformat(),
            ticker, action, price, quantity, fee,
            technical_reason, fundamental_reason, emotion, emotion_score,
            stop_loss, target_price, notes,
        ))


def get_trades(limit: int = 100) -> pd.DataFrame:
    init_db()
    with _conn() as con:
        df = pd.read_sql("SELECT * FROM trades ORDER BY created_at DESC LIMIT ?", con, params=(limit,))
    return df


def add_review(period: str, good: str, bad: str, lessons: str, missed: str):
    init_db()
    with _conn() as con:
        con.execute("""
            INSERT INTO reviews (created_at, period, good_points, bad_points, lessons, missed_signals)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (datetime.now().isoformat(), period, good, bad, lessons, missed))


def get_reviews(limit: int = 20) -> pd.DataFrame:
    init_db()
    with _conn() as con:
        df = pd.read_sql("SELECT * FROM reviews ORDER BY created_at DESC LIMIT ?", con, params=(limit,))
    return df


def trade_stats(df: pd.DataFrame) -> dict:
    if df.empty:
        return {}
    buys = df[df["action"] == "買い"]
    sells = df[df["action"] == "売り"]
    total_invested = (buys["price"] * buys["quantity"]).sum()
    avg_emotion = df["emotion_score"].mean()
    return {
        "総取引数": len(df),
        "買い": len(buys),
        "売り": len(sells),
        "投資総額": total_invested,
        "平均感情スコア": round(avg_emotion, 1) if not pd.isna(avg_emotion) else None,
    }


def calc_pnl(df: pd.DataFrame) -> dict:
    """
    FIFO方式で実現損益・保有ポジションを計算する。
    戻り値:
      realized      : 確定済みの取引ごとの損益リスト
      positions     : 現在保有中のポジション {ticker: [(取得日, 取得価格, 数量), ...]}
      summary_by_ticker : 銘柄別サマリー
      monthly       : 月別実現損益
    """
    if df.empty:
        return {"realized": [], "positions": {}, "summary_by_ticker": {}, "monthly": {}}

    df = df.sort_values("created_at").reset_index(drop=True)

    # ticker ごとに買いキューを保持（FIFO）
    queues: dict[str, list[list]] = {}   # ticker -> [[date, price, qty], ...]
    realized: list[dict] = []

    for _, row in df.iterrows():
        ticker = row["ticker"]
        action = row["action"]
        price = float(row["price"])
        qty = int(row["quantity"])
        fee = float(row["fee"]) if row["fee"] else 0.0
        date = row["created_at"][:10]

        if ticker not in queues:
            queues[ticker] = []

        if action == "買い":
            queues[ticker].append([date, price, qty])

        elif action in ("売り", "損切り"):
            remaining = qty
            cost_total = 0.0
            while remaining > 0 and queues.get(ticker):
                lot = queues[ticker][0]
                lot_date, lot_price, lot_qty = lot
                take = min(remaining, lot_qty)
                cost_total += take * lot_price
                lot[2] -= take
                remaining -= take
                if lot[2] == 0:
                    queues[ticker].pop(0)

            proceeds = qty * price - fee
            pnl = proceeds - cost_total
            realized.append({
                "日付": date,
                "銘柄": ticker,
                "種別": action,
                "売価": price,
                "株数": qty,
                "取得原価": round(cost_total, 0),
                "売却額": round(proceeds, 0),
                "実現損益": round(pnl, 0),
                "損益率(%)": round(pnl / cost_total * 100, 2) if cost_total else 0,
            })

    # 保有ポジション（未決済）
    positions = {t: lots for t, lots in queues.items() if lots}

    # 銘柄別サマリー
    summary_by_ticker: dict[str, dict] = {}
    for r in realized:
        t = r["銘柄"]
        if t not in summary_by_ticker:
            summary_by_ticker[t] = {"実現損益合計": 0, "取引回数": 0, "勝ち": 0, "負け": 0}
        summary_by_ticker[t]["実現損益合計"] += r["実現損益"]
        summary_by_ticker[t]["取引回数"] += 1
        if r["実現損益"] > 0:
            summary_by_ticker[t]["勝ち"] += 1
        else:
            summary_by_ticker[t]["負け"] += 1

    for t, s in summary_by_ticker.items():
        total = s["勝ち"] + s["負け"]
        s["勝率(%)"] = round(s["勝ち"] / total * 100, 1) if total else 0

    # 月別損益
    monthly: dict[str, float] = {}
    for r in realized:
        month = r["日付"][:7]   # YYYY-MM
        monthly[month] = monthly.get(month, 0) + r["実現損益"]

    return {
        "realized": realized,
        "positions": positions,
        "summary_by_ticker": summary_by_ticker,
        "monthly": monthly,
    }


def calc_unrealized(positions: dict, current_prices: dict[str, float]) -> list[dict]:
    """保有ポジションの含み損益を計算"""
    result = []
    for ticker, lots in positions.items():
        current = current_prices.get(ticker)
        for lot_date, lot_price, lot_qty in lots:
            cost = lot_price * lot_qty
            if current:
                value = current * lot_qty
                pnl = value - cost
                pnl_pct = pnl / cost * 100
            else:
                value = pnl = pnl_pct = None
            result.append({
                "銘柄": ticker,
                "取得日": lot_date,
                "取得価格": lot_price,
                "株数": lot_qty,
                "現在値": current,
                "評価額": round(value, 0) if value else "取得不可",
                "含み損益": round(pnl, 0) if pnl is not None else "取得不可",
                "含み損益率(%)": round(pnl_pct, 2) if pnl_pct is not None else "取得不可",
            })
    return result
