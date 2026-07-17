"""
マルチユーザー対応データ保存層
================================
全モジュールのファイル保存をユーザーごとに分離する。

- Streamlit Community Cloud等でログイン済み → メールアドレスから生成した
  IDで data/users/<id>/ に分離保存（他人のデータは見えない・触れない）
- ローカル実行（ログイン情報なし） → "local" ユーザーとして従来同様に動作。
  初回アクセス時に既存の旧ファイルを自動移行するため、過去データは失われない。

使い方（各モジュール側）:
    from modules import userstore
    path = userstore.user_path("watchlist.json", legacy=旧パス)
"""

import hashlib
import shutil
from pathlib import Path

_ROOT = Path(__file__).parent.parent
_USERS_DIR = _ROOT / "data" / "users"


def user_email() -> str | None:
    """ログイン中ユーザーのメールアドレス。未ログイン・ローカルはNone。"""
    try:
        import streamlit as st
        user = getattr(st, "user", None)
        if user is None:
            return None
        # st.user は辞書ライク（バージョンにより属性アクセス）
        try:
            email = user.get("email") if hasattr(user, "get") else None
        except Exception:
            email = None
        if not email:
            email = getattr(user, "email", None)
        if email and isinstance(email, str) and "@" in email:
            return email.lower()
    except Exception:
        pass
    return None


def current_user_id() -> str:
    """ユーザー識別子。メールのハッシュ16桁、ローカルは 'local'。"""
    email = user_email()
    if email:
        return hashlib.sha256(email.encode()).hexdigest()[:16]
    return "local"


def user_dir() -> Path:
    d = _USERS_DIR / current_user_id()
    d.mkdir(parents=True, exist_ok=True)
    return d


def user_path(filename: str, legacy: Path | None = None) -> Path:
    """
    ユーザー専用のファイルパスを返す。

    legacy を渡すと、ローカルユーザーの初回アクセス時に旧配置のファイルを
    新しい場所へ自動コピーする（既存データの引き継ぎ）。
    ログインユーザーには旧ファイルを引き継がない（他人のデータだから）。
    """
    p = user_dir() / filename
    if (legacy is not None and not p.exists() and current_user_id() == "local"):
        try:
            legacy = Path(legacy)
            if legacy.exists():
                shutil.copy2(legacy, p)
        except Exception:
            pass
    return p
