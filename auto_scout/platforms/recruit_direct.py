"""
リクルートダイレクトスカウト（旧リクナビNEXTダイレクトスカウト）アダプター。

対象サービス: https://directscout.recruit.co.jp/ (企業向け管理画面)
※ セレクターは実際の画面を確認して調整してください。
"""
import logging
from typing import List

from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from .base import BasePlatform
from ..models import Candidate, CandidateProfile

logger = logging.getLogger(__name__)

LOGIN_URL = "https://directscout.recruit.co.jp/company/login"  # TODO: 要確認


class RecruitDirectPlatform(BasePlatform):
    PLATFORM_NAME = "recruit_direct"

    async def login(self) -> None:
        logger.info("リクルートダイレクトスカウト: ログイン中...")
        await self.page.goto(LOGIN_URL)
        await self._safe_fill('input[name="email"]', self.config.email)      # TODO
        await self._safe_fill('input[name="password"]', self.config.password)  # TODO
        await self._safe_click('button[type="submit"]')  # TODO
        try:
            await self.page.wait_for_url("**/top**", timeout=15000)  # TODO
        except PlaywrightTimeoutError:
            await self._take_screenshot("login_failed")
            raise RuntimeError("リクルートダイレクトスカウト: ログインに失敗しました。")
        logger.info("リクルートダイレクトスカウト: ログイン成功")

    async def get_tagged_candidates(self, tag: str) -> List[Candidate]:
        position = self.resolve_position(tag)
        if not position:
            logger.warning(
                "リクルートダイレクトスカウト: タグ '%s' に対応するポジションが未設定です。", tag
            )
            return []

        logger.info("リクルートダイレクトスカウト: タグ='%s' の候補者を取得中...", tag)
        # TODO: リクルートダイレクトスカウトのタグ絞り込みURLに変更
        await self.page.goto(
            f"https://directscout.recruit.co.jp/company/scout/list?tag={tag}"
        )
        await self.page.wait_for_load_state("networkidle")

        candidates: List[Candidate] = []
        elements = await self.page.query_selector_all(".scout-target-item")  # TODO
        for el in elements:
            try:
                cid = await el.get_attribute("data-id") or ""
                name_el = await el.query_selector(".name")  # TODO
                name = (await name_el.inner_text()).strip() if name_el else ""
                link_el = await el.query_selector("a")  # TODO
                href = await link_el.get_attribute("href") if link_el else ""
                candidates.append(
                    Candidate(
                        platform=self.PLATFORM_NAME,
                        candidate_id=cid,
                        name=name,
                        tag=tag,
                        position=position,
                        profile_url=f"https://directscout.recruit.co.jp{href}" if href else "",
                    )
                )
            except Exception as e:
                logger.warning("リクルートダイレクトスカウト: 候補者情報取得エラー: %s", e)

        logger.info("リクルートダイレクトスカウト: %d 名の候補者を取得", len(candidates))
        return candidates

    async def get_candidate_profile(self, candidate_id: str) -> CandidateProfile:
        url = f"https://directscout.recruit.co.jp/company/members/{candidate_id}"  # TODO
        await self.page.goto(url)
        await self.page.wait_for_load_state("networkidle")

        async def _t(sel: str) -> str:
            el = await self.page.query_selector(sel)
            return (await el.inner_text()).strip() if el else ""

        return CandidateProfile(
            candidate_id=candidate_id,
            platform=self.PLATFORM_NAME,
            name=await _t(".member-name"),            # TODO
            current_job_title=await _t(".job-title"), # TODO
            current_company=await _t(".company"),     # TODO
            career_summary=await _t(".career"),       # TODO
        )

    async def send_scout(self, candidate_id: str, message: str) -> None:
        url = f"https://directscout.recruit.co.jp/company/scout/send?memberId={candidate_id}"  # TODO
        await self.page.goto(url)
        await self.page.wait_for_load_state("networkidle")

        await self._safe_fill("textarea.message-area", message)  # TODO
        await self._safe_click("button.send-btn")                 # TODO

        try:
            await self.page.wait_for_selector(".complete-notice", timeout=10000)  # TODO
        except PlaywrightTimeoutError:
            await self._take_screenshot(f"send_failed_{candidate_id}")
            raise RuntimeError(
                f"リクルートダイレクトスカウト: 候補者 {candidate_id} へのスカウト送信確認ができませんでした。"
            )

        logger.info("リクルートダイレクトスカウト: 候補者 %s へスカウト送信完了", candidate_id)
