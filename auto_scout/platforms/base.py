"""
プラットフォームアダプターの抽象基底クラス。
各転職サービスはこのクラスを継承して実装する。
"""
import asyncio
import logging
import random
from abc import ABC, abstractmethod
from typing import List, Optional

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from ..models import Candidate, CandidateProfile
from ..config import PlatformConfig

logger = logging.getLogger(__name__)


class BasePlatform(ABC):
    PLATFORM_NAME: str = ""

    def __init__(self, config: PlatformConfig, headless: bool, slow_mo_ms: int):
        self.config = config
        self.headless = headless
        self.slow_mo_ms = slow_mo_ms
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

    # ------------------------------------------------------------------
    # ブラウザライフサイクル
    # ------------------------------------------------------------------

    async def __aenter__(self):
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self.headless,
            slow_mo=self.slow_mo_ms,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
        )
        self._context = await self._browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        self._page = await self._context.new_page()
        return self

    async def __aexit__(self, *_):
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    @property
    def page(self) -> Page:
        if self._page is None:
            raise RuntimeError("ブラウザが初期化されていません。async with で使用してください。")
        return self._page

    # ------------------------------------------------------------------
    # ユーティリティ
    # ------------------------------------------------------------------

    async def _random_delay(self) -> None:
        """スカウト送信間のランダム待機（レート制限対策）。"""
        seconds = random.uniform(
            self.config.min_delay_seconds, self.config.max_delay_seconds
        )
        logger.debug("%s: %.1f 秒待機中...", self.PLATFORM_NAME, seconds)
        await asyncio.sleep(seconds)

    async def _safe_click(self, selector: str, timeout: int = 10000) -> None:
        await self.page.wait_for_selector(selector, timeout=timeout)
        await self.page.click(selector)

    async def _safe_fill(self, selector: str, value: str, timeout: int = 10000) -> None:
        await self.page.wait_for_selector(selector, timeout=timeout)
        await self.page.fill(selector, value)

    async def _take_screenshot(self, name: str) -> None:
        path = f"data/screenshots/{self.PLATFORM_NAME}_{name}.png"
        import os; os.makedirs("data/screenshots", exist_ok=True)
        await self.page.screenshot(path=path)
        logger.debug("スクリーンショット保存: %s", path)

    # ------------------------------------------------------------------
    # 抽象メソッド（各プラットフォームで実装）
    # ------------------------------------------------------------------

    @abstractmethod
    async def login(self) -> None:
        """ログイン処理。"""

    @abstractmethod
    async def get_tagged_candidates(self, tag: str) -> List[Candidate]:
        """
        指定タグが付いた候補者リストを返す。
        ポジション名は config.tag_to_position[tag] から解決する。
        """

    @abstractmethod
    async def get_candidate_profile(self, candidate_id: str) -> CandidateProfile:
        """候補者の詳細プロフィールを取得して返す。"""

    @abstractmethod
    async def send_scout(self, candidate_id: str, message: str) -> None:
        """スカウトメッセージを送信する。失敗時は例外を raise する。"""

    async def get_profile_from_url(self, profile_url: str) -> CandidateProfile:
        """
        プロフィールURLに直接アクセスしてプロフィールを取得する。
        タグ機能のないプラットフォーム（RDS等）でキュー処理に使用。
        デフォルト実装: URLからcandidate_idを末尾パスとして抽出して
        get_candidate_profile() を呼ぶ。プラットフォームごとにオーバーライド可。
        """
        candidate_id = profile_url.rstrip("/").split("/")[-1]
        await self.page.goto(profile_url)
        await self.page.wait_for_load_state("networkidle")
        return await self.get_candidate_profile(candidate_id)

    # ------------------------------------------------------------------
    # 共通ロジック（オーバーライド可）
    # ------------------------------------------------------------------

    def resolve_position(self, tag: str) -> Optional[str]:
        """タグ名からポジション名（テンプレートファイル名）を解決する。"""
        return self.config.tag_to_position.get(tag)

    def get_all_tags(self) -> List[str]:
        """スカウト対象のタグ一覧を返す。"""
        return list(self.config.tag_to_position.keys())
