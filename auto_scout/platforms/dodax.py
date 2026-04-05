"""
dodaX（パーソルキャリア・ハイクラス向け）プラットフォームアダプター。

対象サービス: https://x.doda.jp/ (企業向け管理画面)
※ セレクターは実際の画面を確認して調整してください。
"""
import logging
from typing import List

from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from .base import BasePlatform
from ..models import Candidate, CandidateProfile

logger = logging.getLogger(__name__)

LOGIN_URL = "https://x.doda.jp/company/login"  # TODO: 要確認


class DodaxPlatform(BasePlatform):
    PLATFORM_NAME = "dodax"

    async def login(self) -> None:
        logger.info("dodaX: ログイン中...")
        await self.page.goto(LOGIN_URL)
        await self._safe_fill('input[name="email"]', self.config.email)      # TODO
        await self._safe_fill('input[name="password"]', self.config.password)  # TODO
        await self._safe_click('button[type="submit"]')  # TODO
        try:
            await self.page.wait_for_url("**/mypage**", timeout=15000)  # TODO
        except PlaywrightTimeoutError:
            await self._take_screenshot("login_failed")
            raise RuntimeError("dodaX: ログインに失敗しました。")
        logger.info("dodaX: ログイン成功")

    async def get_tagged_candidates(self, tag: str) -> List[Candidate]:
        position = self.resolve_position(tag)
        if not position:
            logger.warning("dodaX: タグ '%s' に対応するポジションが未設定です。", tag)
            return []

        logger.info("dodaX: タグ='%s' の候補者を取得中...", tag)
        # TODO: dodaX のタグ絞り込みURLに変更
        await self.page.goto(f"https://x.doda.jp/company/scout/candidates?tag={tag}")
        await self.page.wait_for_load_state("networkidle")

        candidates: List[Candidate] = []
        elements = await self.page.query_selector_all(".candidate-card")  # TODO
        for el in elements:
            try:
                cid = await el.get_attribute("data-candidate-id") or ""
                name_el = await el.query_selector(".candidate-name")  # TODO
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
                        profile_url=f"https://x.doda.jp{href}" if href else "",
                    )
                )
            except Exception as e:
                logger.warning("dodaX: 候補者情報取得エラー: %s", e)

        logger.info("dodaX: %d 名の候補者を取得", len(candidates))
        return candidates

    async def get_candidate_profile(self, candidate_id: str) -> CandidateProfile:
        url = f"https://x.doda.jp/company/candidates/{candidate_id}"  # TODO
        await self.page.goto(url)
        await self.page.wait_for_load_state("networkidle")

        async def _t(sel: str) -> str:
            el = await self.page.query_selector(sel)
            return (await el.inner_text()).strip() if el else ""

        return CandidateProfile(
            candidate_id=candidate_id,
            platform=self.PLATFORM_NAME,
            name=await _t(".name"),                  # TODO
            current_job_title=await _t(".position"), # TODO
            current_company=await _t(".company"),    # TODO
            career_summary=await _t(".career"),      # TODO
        )

    async def send_scout(self, candidate_id: str, message: str, scout_type: str = "normal") -> None:
        url = f"https://x.doda.jp/company/scout/send/{candidate_id}"  # TODO
        await self.page.goto(url)
        await self.page.wait_for_load_state("networkidle")

        await self._safe_fill("textarea.scout-body", message)  # TODO
        await self._safe_click("button.send-scout")             # TODO

        try:
            await self.page.wait_for_selector(".sent-complete", timeout=10000)  # TODO
        except PlaywrightTimeoutError:
            await self._take_screenshot(f"send_failed_{candidate_id}")
            raise RuntimeError(f"dodaX: 候補者 {candidate_id} へのスカウト送信確認ができませんでした。")

        logger.info("dodaX: 候補者 %s へスカウト送信完了", candidate_id)
