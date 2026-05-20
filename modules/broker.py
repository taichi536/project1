"""
証券会社API連携モジュール

対応ブローカー:
  - PaperBroker  : ペーパートレード（デフォルト。API不要）
  - KabuStation  : auカブコム証券 kabu STATION（国内株）
  - AlpacaBroker : Alpaca Markets（米国株）

環境変数による切り替え:
  BROKER=paper          → ペーパートレード（デフォルト）
  BROKER=kabu           → kabu STATION
  BROKER=alpaca         → Alpaca

kabu STATION 設定:
  KABU_API_PASSWORD=xxx  （kabu STATION アプリ内のAPIパスワード）
  KABU_API_URL=http://localhost:18080  （デフォルト。変更不要）

Alpaca 設定:
  ALPACA_API_KEY=xxx
  ALPACA_SECRET_KEY=xxx
  ALPACA_PAPER=true  （true=ペーパー口座, false=本番）
"""

import os
import json
import requests
from datetime import datetime
from pathlib import Path


# ── 共通インターフェース ────────────────────────────────────────────────────────

class BrokerBase:
    """全ブローカー共通の基底クラス"""

    def get_balance(self) -> dict:
        """現金残高を返す: {"cash": float, "buying_power": float}"""
        raise NotImplementedError

    def get_positions(self) -> list[dict]:
        """保有ポジション一覧: [{"ticker", "qty", "avg_price", "market_value", "unrealized_pnl"}]"""
        raise NotImplementedError

    def get_orders(self) -> list[dict]:
        """未約定注文一覧"""
        raise NotImplementedError

    def place_order(
        self,
        ticker: str,
        side: str,          # "buy" or "sell"
        qty: int,
        order_type: str = "market",   # "market" or "limit"
        price: float | None = None,
        stop_price: float | None = None,
    ) -> dict:
        """注文発注: {"order_id", "status", "message"}"""
        raise NotImplementedError

    def cancel_order(self, order_id: str) -> bool:
        raise NotImplementedError

    def is_connected(self) -> bool:
        return False

    def broker_name(self) -> str:
        return "Unknown"


# ── ペーパートレード ────────────────────────────────────────────────────────────

_PAPER_STATE_FILE = Path(__file__).parent.parent / ".paper_trade_state.json"


class PaperBroker(BrokerBase):
    """
    ペーパートレード（仮想売買）。
    APIなしで動作し、.paper_trade_state.jsonに状態を保存する。
    実際のお金は動かない。動作確認・戦略テストに使う。
    """

    def __init__(self, initial_cash: float = 1_000_000.0):
        self._state = self._load()
        if not self._state:
            self._state = {
                "cash": initial_cash,
                "positions": {},   # ticker → {qty, avg_price}
                "orders": [],
                "trade_log": [],
            }
            self._save()

    def _load(self) -> dict:
        if _PAPER_STATE_FILE.exists():
            try:
                return json.loads(_PAPER_STATE_FILE.read_text())
            except Exception:
                pass
        return {}

    def _save(self):
        _PAPER_STATE_FILE.write_text(json.dumps(self._state, ensure_ascii=False, indent=2))

    def broker_name(self) -> str:
        return "ペーパートレード"

    def is_connected(self) -> bool:
        return True

    def get_balance(self) -> dict:
        return {
            "cash": self._state["cash"],
            "buying_power": self._state["cash"],
        }

    def get_positions(self) -> list[dict]:
        result = []
        for ticker, pos in self._state["positions"].items():
            result.append({
                "ticker": ticker,
                "qty": pos["qty"],
                "avg_price": pos["avg_price"],
                "market_value": pos["qty"] * pos.get("last_price", pos["avg_price"]),
                "unrealized_pnl": pos["qty"] * (pos.get("last_price", pos["avg_price"]) - pos["avg_price"]),
            })
        return result

    def get_orders(self) -> list[dict]:
        return self._state.get("orders", [])

    def update_prices(self, price_map: dict[str, float]):
        """ポジションの時価を更新（UI表示用）"""
        for ticker, price in price_map.items():
            if ticker in self._state["positions"]:
                self._state["positions"][ticker]["last_price"] = price
        self._save()

    def place_order(
        self,
        ticker: str,
        side: str,
        qty: int,
        order_type: str = "market",
        price: float | None = None,
        stop_price: float | None = None,
    ) -> dict:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        order_id = f"PAPER-{datetime.now().strftime('%Y%m%d%H%M%S')}-{ticker}"

        exec_price = price if (order_type == "limit" and price) else price or 0.0

        if side == "buy":
            cost = qty * exec_price
            if self._state["cash"] < cost:
                return {"order_id": None, "status": "rejected", "message": "現金不足"}
            self._state["cash"] -= cost
            pos = self._state["positions"].get(ticker, {"qty": 0, "avg_price": 0.0})
            total_qty = pos["qty"] + qty
            total_cost = pos["qty"] * pos["avg_price"] + cost
            self._state["positions"][ticker] = {
                "qty": total_qty,
                "avg_price": total_cost / total_qty if total_qty > 0 else 0,
                "last_price": exec_price,
            }

        elif side == "sell":
            pos = self._state["positions"].get(ticker)
            if not pos or pos["qty"] < qty:
                return {"order_id": None, "status": "rejected", "message": "保有株数不足"}
            proceeds = qty * exec_price
            self._state["cash"] += proceeds
            new_qty = pos["qty"] - qty
            if new_qty == 0:
                del self._state["positions"][ticker]
            else:
                self._state["positions"][ticker]["qty"] = new_qty

        self._state["trade_log"].append({
            "order_id": order_id,
            "ticker": ticker,
            "side": side,
            "qty": qty,
            "price": exec_price,
            "order_type": order_type,
            "timestamp": now,
            "status": "filled",
        })
        self._save()

        return {"order_id": order_id, "status": "filled", "message": f"約定: {side} {ticker} {qty}株 @ {exec_price}"}

    def cancel_order(self, order_id: str) -> bool:
        return False

    def reset(self, initial_cash: float = 1_000_000.0):
        """ペーパートレードをリセット"""
        self._state = {
            "cash": initial_cash,
            "positions": {},
            "orders": [],
            "trade_log": [],
        }
        self._save()

    def get_trade_log(self) -> list[dict]:
        return self._state.get("trade_log", [])


# ── kabu STATION（auカブコム証券） ─────────────────────────────────────────────

class KabuStationBroker(BrokerBase):
    """
    kabu STATION REST API。
    auカブコム証券の口座 + kabu STATIONアプリが必要。
    アプリが起動している間だけ localhost:18080 で受け付ける。

    設定: KABU_API_PASSWORD 環境変数にAPIパスワードを設定する。
    """

    def __init__(self):
        self._base = os.getenv("KABU_API_URL", "http://localhost:18080").rstrip("/")
        self._password = os.getenv("KABU_API_PASSWORD", "")
        self._token: str | None = None

    def broker_name(self) -> str:
        return "kabu STATION（auカブコム証券）"

    def _get_token(self) -> str | None:
        if self._token:
            return self._token
        if not self._password:
            return None
        try:
            resp = requests.post(
                f"{self._base}/kabusapi/token",
                json={"APIPassword": self._password},
                timeout=5,
            )
            if resp.status_code == 200:
                self._token = resp.json().get("Token")
                return self._token
        except Exception:
            pass
        return None

    def _headers(self) -> dict:
        token = self._get_token()
        return {"X-API-KEY": token} if token else {}

    def is_connected(self) -> bool:
        try:
            token = self._get_token()
            return token is not None
        except Exception:
            return False

    def get_balance(self) -> dict:
        try:
            resp = requests.get(
                f"{self._base}/kabusapi/wallet/cash",
                headers=self._headers(), timeout=5,
            )
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "cash": data.get("StockAccountWallet", 0),
                    "buying_power": data.get("StockAccountWallet", 0),
                }
        except Exception:
            pass
        return {"cash": 0, "buying_power": 0}

    def get_positions(self) -> list[dict]:
        try:
            resp = requests.get(
                f"{self._base}/kabusapi/positions",
                headers=self._headers(), timeout=5,
            )
            if resp.status_code == 200:
                result = []
                for pos in resp.json():
                    ticker = str(pos.get("Symbol", ""))
                    qty = pos.get("LeavesQty", 0)
                    avg = pos.get("Price", 0)
                    last = pos.get("CurrentPrice", avg)
                    result.append({
                        "ticker": ticker,
                        "qty": qty,
                        "avg_price": avg,
                        "market_value": qty * last,
                        "unrealized_pnl": qty * (last - avg),
                    })
                return result
        except Exception:
            pass
        return []

    def get_orders(self) -> list[dict]:
        try:
            resp = requests.get(
                f"{self._base}/kabusapi/orders",
                headers=self._headers(), timeout=5,
            )
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        return []

    def place_order(
        self,
        ticker: str,
        side: str,
        qty: int,
        order_type: str = "market",
        price: float | None = None,
        stop_price: float | None = None,
    ) -> dict:
        # kabu STATION の注文パラメータ
        # Side: 1=買い, 2=売り
        # FrontOrderType: 10=成行, 20=指値
        side_code = 1 if side == "buy" else 2
        order_code = 20 if order_type == "limit" else 10
        payload = {
            "Password": self._password,
            "Symbol": ticker,
            "Exchange": 1,          # 1=東証
            "SecurityType": 1,      # 1=株式
            "Side": str(side_code),
            "CashMargin": 1,        # 1=現物
            "DelivType": 2,         # 2=お預かり
            "FundType": "  ",
            "AccountType": 4,       # 4=特定口座
            "Qty": qty,
            "FrontOrderType": order_code,
            "Price": price or 0,
            "ExpireDay": 0,         # 0=当日
        }
        try:
            resp = requests.post(
                f"{self._base}/kabusapi/sendorder",
                headers={**self._headers(), "Content-Type": "application/json"},
                json=payload,
                timeout=10,
            )
            data = resp.json()
            if resp.status_code == 200:
                return {
                    "order_id": data.get("OrderId", ""),
                    "status": "accepted",
                    "message": "注文受付完了",
                }
            else:
                return {
                    "order_id": None,
                    "status": "error",
                    "message": data.get("Message", "注文失敗"),
                }
        except Exception as e:
            return {"order_id": None, "status": "error", "message": str(e)}

    def cancel_order(self, order_id: str) -> bool:
        try:
            resp = requests.put(
                f"{self._base}/kabusapi/cancelorder",
                headers={**self._headers(), "Content-Type": "application/json"},
                json={"OrderId": order_id, "Password": self._password},
                timeout=5,
            )
            return resp.status_code == 200
        except Exception:
            return False


# ── Alpaca Markets（米国株） ────────────────────────────────────────────────────

class AlpacaBroker(BrokerBase):
    """
    Alpaca Markets REST API（米国株専用）。
    ALPACA_API_KEY / ALPACA_SECRET_KEY 環境変数が必要。
    ALPACA_PAPER=true でペーパー口座を使用（デフォルト: true）。
    """

    def __init__(self):
        self._api_key = os.getenv("ALPACA_API_KEY", "")
        self._secret = os.getenv("ALPACA_SECRET_KEY", "")
        paper = os.getenv("ALPACA_PAPER", "true").lower() != "false"
        if paper:
            self._base = "https://paper-api.alpaca.markets/v2"
        else:
            self._base = "https://api.alpaca.markets/v2"

    def broker_name(self) -> str:
        return "Alpaca Markets（米国株）"

    def _headers(self) -> dict:
        return {
            "APCA-API-KEY-ID": self._api_key,
            "APCA-API-SECRET-KEY": self._secret,
        }

    def is_connected(self) -> bool:
        if not self._api_key or not self._secret:
            return False
        try:
            resp = requests.get(
                f"{self._base}/account",
                headers=self._headers(), timeout=5,
            )
            return resp.status_code == 200
        except Exception:
            return False

    def get_balance(self) -> dict:
        try:
            resp = requests.get(
                f"{self._base}/account",
                headers=self._headers(), timeout=5,
            )
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "cash": float(data.get("cash", 0)),
                    "buying_power": float(data.get("buying_power", 0)),
                }
        except Exception:
            pass
        return {"cash": 0, "buying_power": 0}

    def get_positions(self) -> list[dict]:
        try:
            resp = requests.get(
                f"{self._base}/positions",
                headers=self._headers(), timeout=5,
            )
            if resp.status_code == 200:
                result = []
                for pos in resp.json():
                    result.append({
                        "ticker": pos.get("symbol", ""),
                        "qty": float(pos.get("qty", 0)),
                        "avg_price": float(pos.get("avg_entry_price", 0)),
                        "market_value": float(pos.get("market_value", 0)),
                        "unrealized_pnl": float(pos.get("unrealized_pl", 0)),
                    })
                return result
        except Exception:
            pass
        return []

    def get_orders(self) -> list[dict]:
        try:
            resp = requests.get(
                f"{self._base}/orders",
                headers=self._headers(), timeout=5,
                params={"status": "open"},
            )
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        return []

    def place_order(
        self,
        ticker: str,
        side: str,
        qty: int,
        order_type: str = "market",
        price: float | None = None,
        stop_price: float | None = None,
    ) -> dict:
        payload: dict = {
            "symbol": ticker,
            "qty": str(qty),
            "side": side,
            "type": order_type,
            "time_in_force": "gtc" if order_type == "limit" else "day",
        }
        if order_type == "limit" and price:
            payload["limit_price"] = str(round(price, 2))
        if stop_price:
            payload["stop_price"] = str(round(stop_price, 2))
            payload["type"] = "stop_limit" if price else "stop"

        try:
            resp = requests.post(
                f"{self._base}/orders",
                headers={**self._headers(), "Content-Type": "application/json"},
                json=payload,
                timeout=10,
            )
            data = resp.json()
            if resp.status_code in (200, 201):
                return {
                    "order_id": data.get("id", ""),
                    "status": data.get("status", "accepted"),
                    "message": f"注文受付: {side} {ticker} {qty}株",
                }
            else:
                return {
                    "order_id": None,
                    "status": "error",
                    "message": data.get("message", "注文失敗"),
                }
        except Exception as e:
            return {"order_id": None, "status": "error", "message": str(e)}

    def cancel_order(self, order_id: str) -> bool:
        try:
            resp = requests.delete(
                f"{self._base}/orders/{order_id}",
                headers=self._headers(), timeout=5,
            )
            return resp.status_code in (200, 204)
        except Exception:
            return False


# ── ファクトリ関数 ─────────────────────────────────────────────────────────────

def get_broker() -> BrokerBase:
    """
    環境変数 BROKER に応じてブローカーインスタンスを返す。
    デフォルトはペーパートレード。
    """
    broker_type = os.getenv("BROKER", "paper").lower()
    if broker_type == "kabu":
        return KabuStationBroker()
    elif broker_type == "alpaca":
        return AlpacaBroker()
    else:
        return PaperBroker()


def calc_order_qty(
    cash: float,
    price: float,
    risk_pct: float = 2.0,
    stop_loss_price: float | None = None,
    max_position_pct: float = 10.0,
    total_assets: float | None = None,
    existing_value: float = 0.0,
) -> int:
    """
    ポジションサイズ計算（固定リスク法）。

    total_assets: 現金＋全ポジション時価の合計（総資産ベースでmax_position_pctを適用）
    existing_value: 対象銘柄の既存保有額（買い増し上限チェックに使用）
    """
    if price <= 0:
        return 0

    base = total_assets if total_assets and total_assets > 0 else cash
    max_total_value = base * max_position_pct / 100
    remaining_value = max(max_total_value - existing_value, 0)
    max_by_position = int(remaining_value / price)

    if stop_loss_price and stop_loss_price < price:
        loss_per_share = price - stop_loss_price
        risk_amount = base * risk_pct / 100
        max_by_risk = int(risk_amount / loss_per_share)
        qty = min(max_by_position, max_by_risk)
    else:
        qty = max_by_position

    # 手持ち現金を超えないようキャップ
    qty = min(qty, int(cash / price))
    return max(qty, 0)
