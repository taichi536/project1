"""
Green（アトラエ）プラットフォームアダプター。

対象サービス: https://green-japan.com/ (企業向けスカウト管理画面)
※ セレクターは実際の画面を確認して調整してください。
"""
import logging
from typing import List

from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from .base import BasePlatform
from ..models import Candidate, CandidateProfile

logger = logging.getLogger(__name__)

LOGIN_URL = "https://green-japan.com/companies/sign_in"  # TODO: 要確認


class GreenPlatform(BasePlatform):
    PLATFORM_NAME = "green"

    async def login(self) -> None:
        logger.info("Green: ログイン中...")
        await self.page.goto(LOGIN_URL)
        await self._safe_fill('input[name="email"]', self.config.email)      # TODO
        await self._safe_fill('input[name="password"]', self.config.password)  # TODO
        await self._safe_click('input[type="submit"]')  # TODO
        try:
            await self.page.wait_for_url("**/dashboard**", timeout=15000)  # TODO
        except PlaywrightTimeoutError:
            await self._take_screenshot("login_failed")
            raise RuntimeError("Green: ログインに失敗しました。")
        logger.info("Green: ログイン成功")

    async def get_tagged_candidates(self, tag: str) -> List[Candidate]:
        position = self.resolve_position(tag)
        if not position:
            logger.warning("Green: タグ '%s' に対応するポジションが未設定です。", tag)
            return []

        logger.info("Green: タグ='%s' の候補者を取得中...", tag)
        # TODO: Green のタグ/ブックマーク絞り込みURLに変更
        await self.page.goto(f"https://green-japan.com/companies/scout?tag={tag}")
        await self.page.wait_for_load_state("networkidle")

        candidates: List[Candidate] = []
        elements = await self.page.query_selector_all(".user-card")  # TODO
        for el in elements:
            try:
                cid = await el.get_attribute("data-user-id") or ""
                name_el = await el.query_selector(".user-name")  # TODO
                name = (await name_el.inner_text()).strip() if name_el else ""
                link_el = await el.query_selector("a.user-link")  # TODO
                href = await link_el.get_attribute("href") if link_el else ""
                candidates.append(
                    Candidate(
                        platform=self.PLATFORM_NAME,
                        candidate_id=cid,
                        name=name,
                        tag=tag,
                        position=position,
                        profile_url=f"https://green-japan.com{href}" if href else "",
                    )
                )
            except Exception as e:
                logger.warning("Green: 候補者情報取得エラー: %s", e)

        logger.info("Green: %d 名の候補者を取得", len(candidates))
        return candidates

    async def get_candidate_profile(self, candidate_id: str) -> CandidateProfile:
        url = f"https://green-japan.com/companies/users/{candidate_id}"  # TODO
        await self.page.goto(url)
        await self.page.wait_for_load_state("networkidle")

        async def _t(sel: str) -> str:
            el = await self.page.query_selector(sel)
            return (await el.inner_text()).strip() if el else ""

        return CandidateProfile(
            candidate_id=candidate_id,
            platform=self.PLATFORM_NAME,
            name=await _t(".profile-name"),              # TODO
            current_job_title=await _t(".current-job"),  # TODO
            current_company=await _t(".company-name"),   # TODO
            career_summary=await _t(".career-detail"),   # TODO
        )

    async def send_scout(self, candidate_id: str, message: str, scout_type: str = "normal") -> None:
        url = f"https://green-japan.com/companies/scouts/new?user_id={candidate_id}"  # TODO
        await self.page.goto(url)
        await self.page.wait_for_load_state("networkidle")

        await self._safe_fill("textarea#scout_message", message)  # TODO
        await self._safe_click("button.scout-submit")              # TODO

        try:
            await self.page.wait_for_selector(".scout-complete", timeout=10000)  # TODO
        except PlaywrightTimeoutError:
            await self._take_screenshot(f"send_failed_{candidate_id}")
            raise RuntimeError(f"Green: 候補者 {candidate_id} へのスカウト送信確認ができませんでした。")

        logger.info("Green: 候補者 %s へスカウト送信完了", candidate_id)
