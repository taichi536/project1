"""
設定管理モジュール。
すべての設定は .env ファイル または環境変数から読み込まれます。
"""
from dataclasses import dataclass, field
from typing import Dict, List
import os
from dotenv import load_dotenv

load_dotenv()


@dataclass
class PlatformConfig:
    enabled: bool
    email: str
    password: str
    # タグ名 -> ポジション名（テンプレートファイル名に対応）のマッピング
    # 例: {"バックエンドエンジニア候補": "backend_engineer", "PMポジション": "product_manager"}
    tag_to_position: Dict[str, str]
    # 1回の実行あたりの最大スカウト送信数（アカウント保護のため）
    max_scouts_per_run: int = 30
    # スカウト間のランダム待機（最小秒）
    min_delay_seconds: int = 5
    # スカウト間のランダム待機（最大秒）
    max_delay_seconds: int = 15


@dataclass
class Config:
    # Claude API
    claude_api_key: str
    claude_model: str

    # データベース
    db_path: str

    # スケジュール（分）
    interval_minutes: int

    # テンプレートディレクトリ
    templates_dir: str

    # Playwright
    headless: bool
    slow_mo_ms: int  # ブラウザ操作間の待機（ms）

    # プラットフォーム設定
    platforms: Dict[str, PlatformConfig]


def _parse_tag_position_map(raw: str) -> Dict[str, str]:
    """
    "タグA:position_a,タグB:position_b" 形式の文字列をパースする。
    """
    result: Dict[str, str] = {}
    if not raw:
        return result
    for pair in raw.split(","):
        pair = pair.strip()
        if ":" in pair:
            tag, position = pair.split(":", 1)
            result[tag.strip()] = position.strip()
    return result


def load_config() -> Config:
    return Config(
        claude_api_key=os.environ["ANTHROPIC_API_KEY"],
        claude_model=os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001"),
        db_path=os.getenv("DB_PATH", "data/scouts.db"),
        interval_minutes=int(os.getenv("SCHEDULE_INTERVAL_MINUTES", "60")),
        templates_dir=os.getenv("TEMPLATES_DIR", "templates"),
        headless=os.getenv("HEADLESS", "true").lower() == "true",
        slow_mo_ms=int(os.getenv("SLOW_MO_MS", "800")),
        platforms={
            "doda": PlatformConfig(
                enabled=os.getenv("DODA_ENABLED", "false").lower() == "true",
                email=os.getenv("DODA_EMAIL", ""),
                password=os.getenv("DODA_PASSWORD", ""),
                tag_to_position=_parse_tag_position_map(
                    os.getenv("DODA_TAG_POSITION_MAP", "")
                ),
                max_scouts_per_run=int(os.getenv("DODA_MAX_SCOUTS_PER_RUN", "30")),
            ),
            "bizreach": PlatformConfig(
                enabled=os.getenv("BIZREACH_ENABLED", "false").lower() == "true",
                email=os.getenv("BIZREACH_EMAIL", ""),
                password=os.getenv("BIZREACH_PASSWORD", ""),
                tag_to_position=_parse_tag_position_map(
                    os.getenv("BIZREACH_TAG_POSITION_MAP", "")
                ),
                max_scouts_per_run=int(os.getenv("BIZREACH_MAX_SCOUTS_PER_RUN", "30")),
            ),
            "mynavi": PlatformConfig(
                enabled=os.getenv("MYNAVI_ENABLED", "false").lower() == "true",
                email=os.getenv("MYNAVI_EMAIL", ""),
                password=os.getenv("MYNAVI_PASSWORD", ""),
                tag_to_position=_parse_tag_position_map(
                    os.getenv("MYNAVI_TAG_POSITION_MAP", "")
                ),
                max_scouts_per_run=int(os.getenv("MYNAVI_MAX_SCOUTS_PER_RUN", "30")),
            ),
            "green": PlatformConfig(
                enabled=os.getenv("GREEN_ENABLED", "false").lower() == "true",
                email=os.getenv("GREEN_EMAIL", ""),
                password=os.getenv("GREEN_PASSWORD", ""),
                tag_to_position=_parse_tag_position_map(
                    os.getenv("GREEN_TAG_POSITION_MAP", "")
                ),
                max_scouts_per_run=int(os.getenv("GREEN_MAX_SCOUTS_PER_RUN", "30")),
            ),
            "ambi": PlatformConfig(
                enabled=os.getenv("AMBI_ENABLED", "false").lower() == "true",
                email=os.getenv("AMBI_EMAIL", ""),
                password=os.getenv("AMBI_PASSWORD", ""),
                tag_to_position=_parse_tag_position_map(
                    os.getenv("AMBI_TAG_POSITION_MAP", "")
                ),
                max_scouts_per_run=int(os.getenv("AMBI_MAX_SCOUTS_PER_RUN", "30")),
            ),
            "dodax": PlatformConfig(
                enabled=os.getenv("DODAX_ENABLED", "false").lower() == "true",
                email=os.getenv("DODAX_EMAIL", ""),
                password=os.getenv("DODAX_PASSWORD", ""),
                tag_to_position=_parse_tag_position_map(
                    os.getenv("DODAX_TAG_POSITION_MAP", "")
                ),
                max_scouts_per_run=int(os.getenv("DODAX_MAX_SCOUTS_PER_RUN", "30")),
            ),
            "recruit_direct": PlatformConfig(
                enabled=os.getenv("RECRUIT_DIRECT_ENABLED", "false").lower() == "true",
                email=os.getenv("RECRUIT_DIRECT_EMAIL", ""),
                password=os.getenv("RECRUIT_DIRECT_PASSWORD", ""),
                tag_to_position=_parse_tag_position_map(
                    os.getenv("RECRUIT_DIRECT_TAG_POSITION_MAP", "")
                ),
                max_scouts_per_run=int(
                    os.getenv("RECRUIT_DIRECT_MAX_SCOUTS_PER_RUN", "30")
                ),
            ),
        },
    )
