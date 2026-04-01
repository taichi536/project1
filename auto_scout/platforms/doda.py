"""
doda（パーソルキャリア）プラットフォームアダプター。

対象サービス: https://recruiter.doda.jp/
※ セレクターは実際の画面を確認して調整してください。
"""
import logging
from typing import List

from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from .base import BasePlatform
from ..config import PlatformConfig
from ..models import Candidate, CandidateProfile

logger = logging.getLogger(__name__)

# --- URL 定数 -----------------------------------------------------------
LOGIN_URL = "https://recruiter.doda.jp/login"
CANDIDATE_LIST_URL = "https://recruiter.doda.jp/scout/candidates"


class DodaPlatform(BasePlatform):
    PLATFORM_NAME = "doda"

    async def login(self) -> None:
        logger.info("doda: ログイン中...")
        await self.page.goto(LOGIN_URL)
        await self._safe_fill('input[name="email"]', self.config.email)
        await self._safe_fill('input[name="password"]', self.config.password)
        await self._safe_click('button[type="submit"]')
        # ログイン完了を確認
        try:
            await self.page.wait_for_url("**/dashboard**", timeout=15000)
        except PlaywrightTimeoutError:
            await self._take_screenshot("login_failed")
            raise RuntimeError("doda: ログインに失敗しました。スクリーンショットを確認してください。")
        logger.info("doda: ログイン成功")

    async def get_tagged_candidates(self, tag: str) -> List[Candidate]:
        """
        指定タグが付いた候補者をリストアップする。

        doda のラベル/タグ機能でフィルタリングして候補者を取得する。
        ※ 実際の URL パラメータ・セレクターは画面確認後に調整してください。
        """
        position = self.resolve_position(tag)
        if not position:
            logger.warning("doda: タグ '%s' に対応するポジションが未設定です。", tag)
            return []

        logger.info("doda: タグ='%s' の候補者を取得中...", tag)
        # タグでフィルタした候補者リストページへ遷移
        # TODO: タグのIDや名前をクエリパラメータとして渡す実際の URL に変更
        await self.page.goto(f"{CANDIDATE_LIST_URL}?label={tag}")
        await self.page.wait_for_load_state("networkidle")

        candidates: List[Candidate] = []
        # TODO: 実際のセレクターに変更（候補者カードや行要素）
        candidate_elements = await self.page.query_selector_all(".candidate-item")
        for el in candidate_elements:
            try:
                # TODO: 実際の属性名・セレクターに変更
                cid = await el.get_attribute("data-candidate-id") or ""
                name_el = await el.query_selector(".candidate-name")
                name = (await name_el.inner_text()).strip() if name_el else ""
                url_el = await el.query_selector("a")
                href = await url_el.get_attribute("href") if url_el else ""
                profile_url = f"https://recruiter.doda.jp{href}" if href else ""

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
                logger.warning("doda: 候補者情報の取得中にエラー: %s", e)

        logger.info("doda: %d 名の候補者を取得", len(candidates))
        return candidates

    async def get_candidate_profile(self, candidate_id: str) -> CandidateProfile:
        """候補者の詳細プロフィールページを取得してパースする。"""
        # TODO: 実際のプロフィール URL に変更
        url = f"https://recruiter.doda.jp/scout/candidates/{candidate_id}"
        await self.page.goto(url)
        await self.page.wait_for_load_state("networkidle")

        async def _get_text(selector: str) -> str:
            el = await self.page.query_selector(selector)
            return (await el.inner_text()).strip() if el else ""

        name = await _get_text(".profile-name")                     # TODO
        job_title = await _get_text(".profile-job-title")            # TODO
        company = await _get_text(".profile-company")                # TODO
        career_summary = await _get_text(".profile-career-summary")  # TODO

        # スキルタグ
        skill_els = await self.page.query_selector_all(".profile-skill-tag")  # TODO
        skills = [
            (await el.inner_text()).strip()
            for el in skill_els
        ]

        return CandidateProfile(
            candidate_id=candidate_id,
            platform=self.PLATFORM_NAME,
            name=name,
            current_job_title=job_title,
            current_company=company,
            skills=skills,
            career_summary=career_summary,
        )

    async def send_scout(self, candidate_id: str, message: str) -> None:
        """スカウトメッセージを送信する。"""
        # TODO: 実際のスカウト送信 URL・フローに変更
        url = f"https://recruiter.doda.jp/scout/send/{candidate_id}"
        await self.page.goto(url)
        await self.page.wait_for_load_state("networkidle")

        # メッセージ入力
        await self._safe_fill("textarea.scout-message-body", message)  # TODO

        # 送信ボタンクリック
        await self._safe_click("button.scout-submit-btn")  # TODO

        # 送信完了確認
        try:
            await self.page.wait_for_selector(".scout-sent-confirmation", timeout=10000)  # TODO
        except PlaywrightTimeoutError:
            await self._take_screenshot(f"send_failed_{candidate_id}")
            raise RuntimeError(f"doda: 候補者 {candidate_id} へのスカウト送信確認ができませんでした。")

        logger.info("doda: 候補者 %s へスカウト送信完了", candidate_id)
