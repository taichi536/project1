"""
ビズリーチ（HR Manager）プラットフォームアダプター。

対象サービス: https://br-navi.bizreach.co.jp/
※ セレクターは実際の画面を確認して調整してください。
"""
import logging
from typing import List

from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from .base import BasePlatform
from ..config import PlatformConfig
from ..models import Candidate, CandidateProfile

logger = logging.getLogger(__name__)

LOGIN_URL = "https://br-navi.bizreach.co.jp/login"
CANDIDATE_LIST_URL = "https://br-navi.bizreach.co.jp/scout/search"


class BizreachPlatform(BasePlatform):
    PLATFORM_NAME = "bizreach"

    async def login(self) -> None:
        logger.info("ビズリーチ: ログイン中...")
        await self.page.goto(LOGIN_URL)
        await self._safe_fill('input[name="loginId"]', self.config.email)
        await self._safe_fill('input[name="password"]', self.config.password)
        await self._safe_click('button[type="submit"]')
        try:
            await self.page.wait_for_url("**/dashboard**", timeout=15000)
        except PlaywrightTimeoutError:
            await self._take_screenshot("login_failed")
            raise RuntimeError("ビズリーチ: ログインに失敗しました。")
        logger.info("ビズリーチ: ログイン成功")

    async def get_tagged_candidates(self, tag: str) -> List[Candidate]:
        position = self.resolve_position(tag)
        if not position:
            logger.warning("ビズリーチ: タグ '%s' に対応するポジションが未設定です。", tag)
            return []

        logger.info("ビズリーチ: タグ='%s' の候補者を取得中...", tag)
        # TODO: ビズリーチのラベル・タグ絞り込みパラメータに変更
        await self.page.goto(f"{CANDIDATE_LIST_URL}?tag={tag}")
        await self.page.wait_for_load_state("networkidle")

        candidates: List[Candidate] = []
        # TODO: 実際のセレクターに変更
        candidate_elements = await self.page.query_selector_all(".candidate-list-item")
        for el in candidate_elements:
            try:
                cid = await el.get_attribute("data-member-id") or ""
                name_el = await el.query_selector(".member-name")
                name = (await name_el.inner_text()).strip() if name_el else ""
                url_el = await el.query_selector("a.profile-link")
                href = await url_el.get_attribute("href") if url_el else ""
                profile_url = f"https://br-navi.bizreach.co.jp{href}" if href else ""

                candidates.append(
                    Candidate(
                        platform=self.PLATFORM_NAME,
                        candidate_id=cid,
                        name=name,
                        tag=tag,
                        position=position,
                        profile_url=profile_url,
                    )
                )
            except Exception as e:
                logger.warning("ビズリーチ: 候補者情報の取得中にエラー: %s", e)

        logger.info("ビズリーチ: %d 名の候補者を取得", len(candidates))
        return candidates

    async def get_candidate_profile(self, candidate_id: str) -> CandidateProfile:
        url = f"https://br-navi.bizreach.co.jp/scout/member/{candidate_id}"
        await self.page.goto(url)
        await self.page.wait_for_load_state("networkidle")

        async def _get_text(selector: str) -> str:
            el = await self.page.query_selector(selector)
            return (await el.inner_text()).strip() if el else ""

        name = await _get_text(".member-name")           # TODO
        job_title = await _get_text(".current-position") # TODO
        company = await _get_text(".current-company")    # TODO
        career_summary = await _get_text(".career-history-text")  # TODO

        skill_els = await self.page.query_selector_all(".skill-tag")  # TODO
        skills = [(await el.inner_text()).strip() for el in skill_els]

        return CandidateProfile(
            candidate_id=candidate_id,
            platform=self.PLATFORM_NAME,
            name=name,
            current_job_title=job_title,
            current_company=company,
            skills=skills,
            career_summary=career_summary,
        )

    async def send_scout(self, candidate_id: str, message: str, scout_type: str = "normal") -> None:
        # TODO: ビズリーチのスカウト送信フローに変更
        url = f"https://br-navi.bizreach.co.jp/scout/send/{candidate_id}"
        await self.page.goto(url)
        await self.page.wait_for_load_state("networkidle")

        await self._safe_fill("textarea#scoutMessage", message)  # TODO
        await self._safe_click("button#sendScoutBtn")             # TODO

        try:
            await self.page.wait_for_selector(".send-complete-message", timeout=10000)  # TODO
        except PlaywrightTimeoutError:
            await self._take_screenshot(f"send_failed_{candidate_id}")
            raise RuntimeError(f"ビズリーチ: 候補者 {candidate_id} へのスカウト送信確認ができませんでした。")

        logger.info("ビズリーチ: 候補者 %s へスカウト送信完了", candidate_id)
