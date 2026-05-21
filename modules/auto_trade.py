"""
自動売買実行モジュール

シグナル判定結果を受け取り、証券会社APIに注文を送る。
ペーパートレード/実口座を切り替えて動作する。

使用例（alert_runner.py から呼び出す）:
    from modules.auto_trade import AutoTrader
    trader = AutoTrader()
    result = trader.execute_signal(ticker, verdict, score, price, atr, stop_loss)
"""

import os
import json
from pathlib import Path
from datetime import datetime
from modules.broker import get_broker, calc_order_qty, BrokerBase


_SETTINGS_FILE = Path(__file__).parent.parent / ".auto_trade_settings.json"

_DEFAULT_SETTINGS = {
    "enabled": False,           # 自動売買の有効/無効
    "risk_pct": 2.0,            # 1取引の許容損失（資金の%）
    "max_position_pct": 10.0,   # 1銘柄への最大投資比率（%）
    "max_positions": 5,         # 同時保有銘柄数の上限
    "max_invested_pct": 70.0,   # 総資産に対する最大投資比率（%）。残りはキャッシュ確保
    "min_score": 4,             # 自動買いに必要な最低スコア
    "sell_score": -4,           # 自動売りに必要な最大スコア
    "use_limit_order": False,   # True=指値, False=成行（ペーパーでは成行推奨）
    "limit_offset_pct": 0.3,   # 指値: 現在値+X%で買い注文
    "stop_loss_atr_mult": 2.0,  # ATR×倍数で損切りライン設定
    "take_profit_pct": 10.0,    # 利確ライン: 買値から+X%で自動売却（0=無効）
    "stop_loss_pct": 5.0,       # 固定損切り: 買値から-X%で自動売却（0=無効）
    "broker": "paper",          # "paper" / "kabu" / "alpaca"
}


class AutoTrader:
    """
    シグナルに基づいて自動的に注文を送るクラス。
    設定は .auto_trade_settings.json に永続化する。
    """

    def __init__(self):
        self.settings = self._load_settings()
        self.broker: BrokerBase = get_broker()

    def _load_settings(self) -> dict:
        if _SETTINGS_FILE.exists():
            try:
                saved = json.loads(_SETTINGS_FILE.read_text())
                return {**_DEFAULT_SETTINGS, **saved}
            except Exception:
                pass
        return _DEFAULT_SETTINGS.copy()

    def save_settings(self, updates: dict):
        self.settings.update(updates)
        _SETTINGS_FILE.write_text(
            json.dumps(self.settings, ensure_ascii=False, indent=2)
        )

    def is_enabled(self) -> bool:
        return self.settings.get("enabled", False)

    def get_status(self) -> dict:
        """接続状態・残高・ポジションを返す"""
        connected = self.broker.is_connected()
        balance = self.broker.get_balance() if connected else {"cash": 0, "buying_power": 0}
        positions = self.broker.get_positions() if connected else []
        return {
            "broker_name": self.broker.broker_name(),
            "connected": connected,
            "enabled": self.is_enabled(),
            "cash": balance["cash"],
            "buying_power": balance["buying_power"],
            "positions": positions,
            "settings": self.settings,
        }

    def execute_signal(
        self,
        ticker: str,
        verdict: str,
        score: int,
        price: float,
        atr: float | None = None,
        stop_loss: float | None = None,
    ) -> dict | None:
        """
        シグナルに基づいて注文を送る。
        自動売買が無効または条件を満たさない場合は None を返す。
        """
        if not self.is_enabled():
            return None

        if not self.broker.is_connected():
            return {"status": "error", "message": "ブローカーに接続できません"}

        s = self.settings
        positions = self.broker.get_positions()
        pos = next((p for p in positions if p["ticker"] == ticker), None)

        # 保有中なら利確・損切りチェックを優先
        if pos:
            avg = pos["avg_price"]
            tp_pct = s.get("take_profit_pct", 0)
            sl_pct = s.get("stop_loss_pct", 0)
            if tp_pct > 0 and price >= avg * (1 + tp_pct / 100):
                return self._execute_sell(ticker, price, reason=f"利確(+{tp_pct}%)")
            if sl_pct > 0 and price <= avg * (1 - sl_pct / 100):
                return self._execute_sell(ticker, price, reason=f"損切り(-{sl_pct}%)")

        # 買いシグナル（未保有 or 追加余地あり）
        if verdict == "買い" and score >= s["min_score"]:
            # 同時保有銘柄数チェック
            max_pos = s.get("max_positions", 5)
            if not pos and len(positions) >= max_pos:
                return {"status": "skipped", "message": f"同時保有上限({max_pos}銘柄)に達しています"}

            # 総投資比率チェック
            max_inv = s.get("max_invested_pct", 70.0)
            balance = self.broker.get_balance()
            cash = balance["buying_power"]
            total_assets = cash + sum(p.get("market_value", p["qty"] * p["avg_price"]) for p in positions)
            invested = total_assets - cash
            if total_assets > 0 and (invested / total_assets * 100) >= max_inv:
                return {"status": "skipped", "message": f"総投資比率({max_inv}%)上限に達しています"}

            return self._execute_buy(ticker, price, atr, stop_loss, positions)

        # 売りシグナル
        elif verdict == "売り" and score <= s["sell_score"] and pos:
            return self._execute_sell(ticker, price, reason=f"売りシグナル(score={score:+d})")

        return None

    def _execute_buy(
        self,
        ticker: str,
        price: float,
        atr: float | None,
        stop_loss: float | None,
        positions: list[dict],
    ) -> dict:
        s = self.settings
        balance = self.broker.get_balance()
        cash = balance["buying_power"]

        # 総資産と既存保有額を計算
        total_assets = cash + sum(p.get("market_value", p["qty"] * p["avg_price"]) for p in positions)
        existing = next((p for p in positions if p["ticker"] == ticker), None)
        existing_value = existing.get("market_value", existing["qty"] * existing["avg_price"]) if existing else 0.0

        # 既にmax_position_pct以上保有していればスキップ
        if existing_value >= total_assets * s["max_position_pct"] / 100:
            return {"status": "skipped", "message": f"{ticker}は既に上限({s['max_position_pct']}%)保有中"}

        # 損切りライン: ATRベース と 固定%の両方を計算し、より高い（損失が少ない）方を採用
        # 例: ATR損切り=950円, 固定5%損切り=975円 → 975円を採用（より早く損切り）
        sl_price = stop_loss
        if sl_price is None and atr:
            sl_price = price - atr * s["stop_loss_atr_mult"]
        sl_pct = s.get("stop_loss_pct", 0)
        if sl_pct > 0:
            sl_price_fixed = price * (1 - sl_pct / 100)
            sl_price = sl_price_fixed if sl_price is None else max(sl_price, sl_price_fixed)

        qty = calc_order_qty(
            cash=cash,
            price=price,
            risk_pct=s["risk_pct"],
            stop_loss_price=sl_price,
            max_position_pct=s["max_position_pct"],
            total_assets=total_assets,
            existing_value=existing_value,
        )

        if qty <= 0:
            return {"status": "skipped", "message": f"購入可能株数が0（現金: {cash:,.0f}円）"}

        order_type = "limit" if s["use_limit_order"] else "market"
        order_price = round(price * (1 + s["limit_offset_pct"] / 100), 1) if order_type == "limit" else price

        result = self.broker.place_order(
            ticker=ticker,
            side="buy",
            qty=qty,
            order_type=order_type,
            price=order_price,
            stop_price=None,
        )

        result.update({
            "ticker": ticker,
            "side": "buy",
            "qty": qty,
            "exec_price": order_price,
            "stop_loss": sl_price,
            "estimated_cost": qty * order_price,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })
        return result

    def _execute_sell(self, ticker: str, price: float, reason: str = "") -> dict:
        positions = self.broker.get_positions()
        pos = next((p for p in positions if p["ticker"] == ticker), None)
        if not pos or pos["qty"] <= 0:
            return {"status": "skipped", "message": f"{ticker}の保有ポジションなし"}

        qty = int(pos["qty"])
        s = self.settings
        order_type = "limit" if s["use_limit_order"] else "market"
        order_price = round(price * (1 - s["limit_offset_pct"] / 100), 1) if order_type == "limit" else price

        result = self.broker.place_order(
            ticker=ticker,
            side="sell",
            qty=qty,
            order_type=order_type,
            price=order_price,
        )

        result.update({
            "ticker": ticker,
            "side": "sell",
            "qty": qty,
            "exec_price": order_price,
            "reason": reason,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })
        return result
