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
    """簡易パフォーマンス統計"""
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
