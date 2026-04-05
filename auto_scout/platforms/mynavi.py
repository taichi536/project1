"""
マイナビ転職プラットフォームアダプター。

対象サービス: https://tenshoku.mynavi.jp/ (企業向け管理画面)
※ セレクターは実際の画面を確認して調整してください。
"""
import logging
from typing import List

from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from .base import BasePlatform
from ..models import Candidate, CandidateProfile

logger = logging.getLogger(__name__)

LOGIN_URL = "https://tenshoku.mynavi.jp/scout/login"  # TODO: 実際のログインURLに変更


class MynaviPlatform(BasePlatform):
    PLATFORM_NAME = "mynavi"

    async def login(self) -> None:
        logger.info("マイナビ転職: ログイン中...")
        await self.page.goto(LOGIN_URL)
        await self._safe_fill('input[name="email"]', self.config.email)   # TODO
        await self._safe_fill('input[name="password"]', self.config.password)  # TODO
        await self._safe_click('button[type="submit"]')  # TODO
        try:
            await self.page.wait_for_url("**/mypage**", timeout=15000)  # TODO
        except PlaywrightTimeoutError:
            await self._take_screenshot("login_failed")
            raise RuntimeError("マイナビ転職: ログインに失敗しました。")
        logger.info("マイナビ転職: ログイン成功")

    async def get_tagged_candidates(self, tag: str) -> List[Candidate]:
        position = self.resolve_position(tag)
        if not position:
            logger.warning("マイナビ転職: タグ '%s' に対応するポジションが未設定です。", tag)
            return []

        logger.info("マイナビ転職: タグ='%s' の候補者を取得中...", tag)
        # TODO: マイナビのタグ/ラベル絞り込みページに変更
        await self.page.goto(f"https://tenshoku.mynavi.jp/scout/search?tag={tag}")
        await self.page.wait_for_load_state("networkidle")

        candidates: List[Candidate] = []
        # TODO: 実際のセレクターに変更
        elements = await self.page.query_selector_all(".scout-candidate-item")
        for el in elements:
            try:
                cid = await el.get_attribute("data-id") or ""
                name_el = await el.query_selector(".name")
                name = (await name_el.inner_text()).strip() if name_el else ""
                link_el = await el.query_selector("a")
                href = await link_el.get_attribute("href") if link_el else ""
                candidates.append(
                    Candidate(
                        platform=self.PLATFORM_NAME,
                        candidate_id=cid,
                        name=name,
                        tag=tag,
                        position=position,
                        profile_url=href or "",
                    )
                )
            except Exception as e:
                logger.warning("マイナビ転職: 候補者情報取得エラー: %s", e)

        logger.info("マイナビ転職: %d 名の候補者を取得", len(candidates))
        return candidates

    async def get_candidate_profile(self, candidate_id: str) -> CandidateProfile:
        url = f"https://tenshoku.mynavi.jp/scout/candidates/{candidate_id}"  # TODO
        await self.page.goto(url)
        await self.page.wait_for_load_state("networkidle")

        async def _t(sel: str) -> str:
            el = await self.page.query_selector(sel)
            return (await el.inner_text()).strip() if el else ""

        return CandidateProfile(
            candidate_id=candidate_id,
            platform=self.PLATFORM_NAME,
            name=await _t(".profile-name"),          # TODO
            current_job_title=await _t(".job-title"), # TODO
            current_company=await _t(".company"),     # TODO
            career_summary=await _t(".career-summary"),  # TODO
        )

    async def send_scout(self, candidate_id: str, message: str, scout_type: str = "normal") -> None:
        url = f"https://tenshoku.mynavi.jp/scout/send/{candidate_id}"  # TODO
        await self.page.goto(url)
        await self.page.wait_for_load_state("networkidle")

        await self._safe_fill("textarea.message-input", message)   # TODO
        await self._safe_click("button.send-btn")                   # TODO

        try:
            await self.page.wait_for_selector(".sent-confirm", timeout=10000)  # TODO
        except PlaywrightTimeoutError:
            await self._take_screenshot(f"send_failed_{candidate_id}")
            raise RuntimeError(f"マイナビ転職: 候補者 {candidate_id} へのスカウト送信確認ができませんでした。")

        logger.info("マイナビ転職: 候補者 %s へスカウト送信完了", candidate_id)
