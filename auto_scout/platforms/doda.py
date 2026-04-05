"""
doda（パーソルキャリア）プラットフォームアダプター。

対象サービス: https://recruiter.doda.jp/

【確認済みの仕様（スカウト送信ページ）】
- 通常 / プラチナ / ダイヤモンドスカウトをラジオボタンで選択
- ラベルテキスト: "通常スカウト" / "プラチナスカウト" / "ダイヤモンドスカウト"
- テキストエリアには再送元の文章が事前入力済み（クリアして上書きする）
- 文字数制限: 500字
- 送信ボタン: "送信する"

【TODO が残っている箇所】
- ログイン後のURL確認 (wait_for_url のパターン)
- 候補者一覧ページのURL・セレクター
- プロフィールページのURL・セレクター
- スカウト送信ページへの遷移方法（プロフィールページの「スカウトを送る」ボタン）
- 送信完了確認のセレクター

これらは HEADLESS=false でドライランしながら F12 で確認してください。
スクリーンショットは data/screenshots/ に保存されます。
"""
import logging
from typing import List, Optional

from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from .base import BasePlatform
from ..models import Candidate, CandidateProfile

logger = logging.getLogger(__name__)

DODA_MAX_MESSAGE_LENGTH = 500  # doda の文字数制限

# スカウト種別 → ラジオボタンのラベルテキスト
SCOUT_TYPE_LABELS = {
    "normal": "通常スカウト",
    "platinum": "プラチナスカウト",
    "diamond": "ダイヤモンドスカウト",
}

LOGIN_URL = "https://recruiter.doda.jp/login"
CANDIDATE_LIST_URL = "https://recruiter.doda.jp/scout/candidates"  # TODO: 要確認


class DodaPlatform(BasePlatform):
    PLATFORM_NAME = "doda"

    # ------------------------------------------------------------------
    # ログイン
    # ------------------------------------------------------------------

    async def login(self) -> None:
        logger.info("doda: ログイン中...")
        await self.page.goto(LOGIN_URL)
        await self._safe_fill('input[name="email"]', self.config.email)
        await self._safe_fill('input[name="password"]', self.config.password)
        await self._safe_click('button[type="submit"]')
        try:
            # TODO: ログイン後の遷移先 URL パターンに変更
            await self.page.wait_for_url("**/scout/**", timeout=15000)
        except PlaywrightTimeoutError:
            await self._take_screenshot("login_failed")
            raise RuntimeError("doda: ログインに失敗しました。スクリーンショットを確認してください。")
        logger.info("doda: ログイン成功")

    # ------------------------------------------------------------------
    # 候補者一覧取得（タグ絞り込み）
    # ------------------------------------------------------------------

    async def get_tagged_candidates(self, tag: str) -> List[Candidate]:
        """
        指定タグが付いた候補者をリストアップする。

        TODO: 実際のタグ絞り込み URL・セレクターに変更してください。
        """
        position = self.resolve_position(tag)
        if not position:
            logger.warning("doda: タグ '%s' に対応するポジションが未設定です。", tag)
            return []

        logger.info("doda: タグ='%s' の候補者を取得中...", tag)
        # TODO: 実際のタグ絞り込み URL に変更
        await self.page.goto(f"{CANDIDATE_LIST_URL}?label={tag}")
        await self.page.wait_for_load_state("networkidle")

        candidates: List[Candidate] = []
        # TODO: 実際の候補者カードのセレクターに変更
        candidate_elements = await self.page.query_selector_all(".candidate-item")
        for el in candidate_elements:
            try:
                cid = await el.get_attribute("data-candidate-id") or ""  # TODO
                name_el = await el.query_selector(".candidate-name")       # TODO
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

    # ------------------------------------------------------------------
    # プロフィール取得
    # ------------------------------------------------------------------

    async def get_candidate_profile(self, candidate_id: str) -> CandidateProfile:
        """
        候補者の詳細プロフィールページを取得してパースする。

        スクリーンショットで確認できたフィールド:
          - 在籍企業、学歴、経験職種、経験業種、マネジメント経験、言語

        TODO: 実際のプロフィール URL・セレクターに変更してください。
        """
        url = f"https://recruiter.doda.jp/scout/candidates/{candidate_id}"  # TODO
        await self.page.goto(url)
        await self.page.wait_for_load_state("networkidle")

        async def _get_text(selector: str) -> str:
            el = await self.page.query_selector(selector)
            return (await el.inner_text()).strip() if el else ""

        # TODO: 実際のセレクターに変更
        # ヒント: doda のプロフィールページは定義リスト（dt/dd）形式の可能性が高い
        name = await _get_text(".profile-name")           # TODO
        company = await _get_text("dd.current-company")   # TODO (在籍企業)
        job_title = await _get_text("dd.job-category")    # TODO (経験職種)

        # 学歴・経験・言語などをまとめて career_summary として取得
        # Claude がパーソナライズ文を生成するための素材になる
        career_parts = []

        company_text = await _get_text("dd.current-company")   # TODO
        if company_text:
            career_parts.append(f"在籍企業: {company_text}")

        edu_text = await _get_text("dd.education")  # TODO (学歴)
        if edu_text:
            career_parts.append(f"学歴: {edu_text}")

        exp_text = await _get_text("dd.job-experience")  # TODO (経験職種・年数)
        if exp_text:
            career_parts.append(f"経験職種: {exp_text}")

        mgmt_text = await _get_text("dd.management-experience")  # TODO (マネジメント経験)
        if mgmt_text:
            career_parts.append(f"マネジメント経験: {mgmt_text}")

        lang_text = await _get_text("dd.language")  # TODO (言語)
        if lang_text:
            career_parts.append(f"言語: {lang_text}")

        return CandidateProfile(
            candidate_id=candidate_id,
            platform=self.PLATFORM_NAME,
            name=name,
            current_company=company,
            current_job_title=job_title,
            career_summary="\n".join(career_parts),
        )

    # ------------------------------------------------------------------
    # スカウト送信
    # ------------------------------------------------------------------

    async def send_scout(self, candidate_id: str, message: str,
                         scout_type: str = "normal") -> None:
        """
        スカウト送信ページでラジオボタンを選択し、文面を入力して送信する。

        【確認済みの UI 仕様】
        - 通常 / プラチナ / ダイヤモンドスカウトをラジオボタンで選択
        - テキストエリアに再送元の文章が事前入力されている → クリアして上書き
        - 500字制限 → 超えた場合は自動で切り詰め
        - 「送信する」ボタンで送信
        """
        # スカウト送信ページへ遷移
        # TODO: 実際の送信ページへの遷移方法を確認してください。
        #       候補者プロフィールページから「スカウトを送る」ボタンを押す場合:
        #         await self._safe_click("button:has-text('スカウトを送る')")
        #         await self.page.wait_for_url("**/scout/send**", timeout=10000)
        #       直接 URL で遷移できる場合:
        #         await self.page.goto(f"https://recruiter.doda.jp/scout/send/{candidate_id}")
        #
        # 現状は直接遷移を仮実装
        await self.page.goto(
            f"https://recruiter.doda.jp/scout/send/{candidate_id}"  # TODO: 要確認
        )
        await self.page.wait_for_load_state("networkidle")

        # --- スカウト残数チェック ---
        remaining = await self._get_scout_remaining(scout_type)
        if remaining is not None and remaining == 0:
            raise RuntimeError(
                f"doda: {SCOUT_TYPE_LABELS.get(scout_type, scout_type)} の残数が 0 です。"
                "送信をスキップします。"
            )

        # --- ラジオボタンでスカウト種別を選択 ---
        label_text = SCOUT_TYPE_LABELS.get(scout_type, "通常スカウト")
        try:
            # Playwright の get_by_label でラジオボタンを選択
            await self.page.get_by_label(label_text).check(timeout=8000)
            logger.debug("doda: '%s' を選択しました", label_text)
        except Exception:
            # フォールバック: ラベルテキストを含む要素をクリック
            await self._safe_click(f'label:has-text("{label_text}")')

        # --- テキストエリアをクリアして文面を入力 ---
        # 事前入力済みの文章があるため、まず全選択して上書き
        message_to_send = self._truncate_message(message)

        textarea = await self.page.query_selector("textarea")  # TODO: セレクター要確認
        if textarea is None:
            await self._take_screenshot(f"textarea_not_found_{candidate_id}")
            raise RuntimeError("doda: テキストエリアが見つかりません。")

        await textarea.click()
        await textarea.press("Control+a")  # 全選択
        await textarea.fill(message_to_send)

        logger.debug(
            "doda: 文面入力完了 (%d字 / %d字制限)",
            len(message_to_send), DODA_MAX_MESSAGE_LENGTH,
        )

        # --- 送信 ---
        await self._safe_click("button:has-text('送信する')")

        # --- 送信完了確認 ---
        try:
            # TODO: 送信後に遷移するページ or 完了メッセージのセレクターに変更
            # 例1: モーダルが出る場合 → ".modal:has-text('送信しました')"
            # 例2: 別ページに遷移する場合 → wait_for_url("**/complete**")
            await self.page.wait_for_selector(
                "text=送信しました", timeout=15000  # TODO: 要確認
            )
        except PlaywrightTimeoutError:
            await self._take_screenshot(f"send_failed_{scout_type}_{candidate_id}")
            raise RuntimeError(
                f"doda: 候補者 {candidate_id} ({label_text}) への送信完了が確認できませんでした。"
                "スクリーンショットを確認してください。"
            )

        logger.info("doda: 候補者 %s へ %s 送信完了", candidate_id, label_text)

    async def _get_scout_remaining(self, scout_type: str) -> Optional[int]:
        """
        スカウト送信ページの残数表示をパースして返す。
        取得できない場合は None を返す（ガードをスキップ）。

        スクリーンショットで確認できた表示:
          "プラチナスカウト  残り 106 / 128"
          "ダイヤモンドスカウト  残り 79 / 85"
        """
        if scout_type == "normal":
            return None  # 通常スカウトは無制限

        label_text = SCOUT_TYPE_LABELS.get(scout_type, "")
        try:
            # "残り XX / YY" のテキストを含む要素を探す
            # TODO: 実際のセレクターに変更
            row = await self.page.query_selector(
                f'label:has-text("{label_text}")'
            )
            if row is None:
                return None
            row_text = await row.inner_text()
            # "残り 106 / 128" → 106 をパース
            if "残り" in row_text:
                parts = row_text.split("残り")[-1].strip().split("/")
                return int(parts[0].strip())
        except Exception as e:
            logger.debug("doda: 残数パース失敗（無視）: %s", e)
        return None

    @staticmethod
    def _truncate_message(message: str) -> str:
        """500字を超える場合は切り詰める。"""
        if len(message) <= DODA_MAX_MESSAGE_LENGTH:
            return message
        truncated = message[:DODA_MAX_MESSAGE_LENGTH]
        logger.warning(
            "doda: 文面が %d字で上限を超えているため %d字に切り詰めました。",
            len(message), DODA_MAX_MESSAGE_LENGTH,
        )
        return truncated
