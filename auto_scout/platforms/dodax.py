"""
dodaX（パーソルキャリア・ハイクラス向け）プラットフォームアダプター。

対象サービス: https://search.doda-x.jp/member_search/result/

【確認済みの仕様】
- タグで絞り込んでもURLは変わらない（SPA構成）
- 候補者一覧ページで候補者カードをクリックしてプロフィールを表示
- 「スカウトを送る」ボタン → テキストエリアに文面を入力して送信

【TODO が残っている箇所】
- ログイン後の URL パターン (wait_for_url のパターン)
- タグ絞り込みのUI操作方法（サイドメニュー or ドロップダウン）
- 候補者カードのセレクター
- プロフィールエリアのセレクター
- 「スカウトを送る」ボタン・テキストエリア・送信ボタンのセレクター
- 送信完了確認のセレクター

これらは HEADLESS=false でドライランしながら F12 で確認してください。
スクリーンショットは data/screenshots/ に保存されます。
"""
import logging
from typing import List

from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from .base import BasePlatform
from ..models import Candidate, CandidateProfile

logger = logging.getLogger(__name__)

LOGIN_URL = "https://doda-x.jp/login"  # TODO: 要確認
CANDIDATE_LIST_URL = "https://search.doda-x.jp/member_search/result/"


class DodaxPlatform(BasePlatform):
    PLATFORM_NAME = "dodax"

    # ------------------------------------------------------------------
    # ログイン
    # ------------------------------------------------------------------

    async def login(self) -> None:
        logger.info("dodaX: ログイン中...")
        await self.page.goto(LOGIN_URL)
        await self._safe_fill('input[name="email"]', self.config.email)      # TODO
        await self._safe_fill('input[name="password"]', self.config.password)  # TODO
        await self._safe_click('button[type="submit"]')  # TODO
        try:
            # TODO: ログイン後の遷移先 URL パターンに変更
            await self.page.wait_for_url("**/member_search/**", timeout=15000)
        except PlaywrightTimeoutError:
            await self._take_screenshot("login_failed")
            raise RuntimeError("dodaX: ログインに失敗しました。スクリーンショットを確認してください。")
        logger.info("dodaX: ログイン成功")

    # ------------------------------------------------------------------
    # 候補者一覧取得（タグ絞り込み）
    # タグで絞り込んでもURLは変わらないSPA構成
    # ------------------------------------------------------------------

    async def get_tagged_candidates(self, tag: str) -> List[Candidate]:
        """
        指定タグで絞り込んだ候補者をリストアップする。

        dodaX はタグ絞り込みをしても URL が変わらない SPA 構成のため、
        UIを操作してタグを選択する。
        """
        position = self.resolve_position(tag)
        if not position:
            logger.warning("dodaX: タグ '%s' に対応するポジションが未設定です。", tag)
            return []

        logger.info("dodaX: タグ='%s' の候補者を取得中...", tag)
        await self.page.goto(CANDIDATE_LIST_URL)
        await self.page.wait_for_load_state("networkidle")

        # タグ（ラベル）で絞り込む
        await self._select_tag(tag)

        candidates: List[Candidate] = []

        # TODO: 実際の候補者カードのセレクターに変更
        card_selector = ".candidate-card"  # TODO
        try:
            await self.page.wait_for_selector(card_selector, timeout=10000)
        except PlaywrightTimeoutError:
            logger.warning("dodaX: タグ '%s' の候補者カードが見つかりません。", tag)
            await self._take_screenshot(f"no_candidates_{tag}")
            return []

        cards = await self.page.query_selector_all(card_selector)
        logger.info("dodaX: %d 枚のカードを検出", len(cards))

        for card in cards:
            try:
                # TODO: candidate_id の取得方法（data属性 等）
                cid = await card.get_attribute("data-candidate-id") or ""  # TODO
                if not cid:
                    logger.warning("dodaX: candidate_id が取得できないカードをスキップ")
                    continue

                # TODO: 候補者名の取得
                name_el = await card.query_selector(".candidate-name")  # TODO
                name = (await name_el.inner_text()).strip() if name_el else ""

                candidates.append(
                    Candidate(
                        platform=self.PLATFORM_NAME,
                        candidate_id=cid,
                        name=name,
                        tag=tag,
                        position=position,
                        profile_url="",  # SPA のため URL なし
                    )
                )
            except Exception as e:
                logger.warning("dodaX: カードの解析中にエラー: %s", e)

        logger.info("dodaX: %d 名の候補者を取得", len(candidates))
        return candidates

    async def _select_tag(self, tag: str) -> None:
        """
        タグ（ラベル）で候補者を絞り込む。
        TODO: 実際のタグ選択UIに合わせて実装する。

        例1: サイドメニューのタグ名をクリック
          await self._safe_click(f'[data-tag-name="{tag}"]')

        例2: フィルタードロップダウンで選択
          await self._safe_click('.tag-filter-dropdown')
          await self._safe_click(f'.tag-option:has-text("{tag}")')
        """
        # TODO: 実際のタグ選択UIに変更
        logger.debug("dodaX: タグ '%s' を選択中...", tag)
        await self.page.wait_for_load_state("networkidle")

    # ------------------------------------------------------------------
    # プロフィール取得
    # ------------------------------------------------------------------

    async def get_candidate_profile(self, candidate_id: str) -> CandidateProfile:
        """
        候補者カードをクリックして表示されたプロフィールを読み取る。

        get_tagged_candidates() → _click_candidate_card() の後に呼ばれる想定。
        """
        # TODO: プロフィールエリアのセレクターに変更
        async def _t(selector: str) -> str:
            el = await self.page.query_selector(selector)
            return (await el.inner_text()).strip() if el else ""

        name = await _t(".profile-area .name")           # TODO
        job_title = await _t(".profile-area .position")  # TODO
        company = await _t(".profile-area .company")     # TODO
        career_summary = await _t(".profile-area .career")  # TODO

        skill_els = await self.page.query_selector_all(".profile-area .skill-tag")  # TODO
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

    async def _click_candidate_card(self, candidate_id: str) -> None:
        """
        指定IDの候補者カードをクリックしてプロフィールを表示させる。
        TODO: 実際のセレクターに変更
        """
        card = await self.page.query_selector(
            f'.candidate-card[data-candidate-id="{candidate_id}"]'  # TODO
        )
        if card:
            await card.click()
            await self.page.wait_for_load_state("networkidle")
            # TODO: プロフィールエリアに情報が表示されたことを確認するセレクター
            await self.page.wait_for_selector(".profile-area .name", timeout=8000)  # TODO
        else:
            raise RuntimeError(f"dodaX: candidate_id={candidate_id} のカードが見つかりません")

    # ------------------------------------------------------------------
    # スカウト送信
    # ------------------------------------------------------------------

    async def send_scout(self, candidate_id: str, message: str,
                         scout_type: str = "normal") -> None:
        """
        候補者カードをクリックしてプロフィールを表示し、
        「スカウトを送る」ボタンからテキストエリアに文面を入力して送信する。

        【確認済みの UI 仕様】
        - 「スカウトを送る」ボタンでスカウト送信フォームが表示される
        - テキストエリアに文面を入力して送信
        """
        # カードをクリックしてプロフィールを表示
        await self._click_candidate_card(candidate_id)

        # 「スカウトを送る」ボタンをクリック
        # TODO: 実際のボタンセレクターに変更
        await self._safe_click("button:has-text('スカウトを送る')")  # TODO

        # スカウト送信フォーム／モーダルが開くのを待つ
        # TODO: フォームのセレクターに変更
        await self.page.wait_for_selector(".scout-form", timeout=8000)  # TODO

        # テキストエリアに文面を入力
        # TODO: テキストエリアのセレクターに変更
        textarea = await self.page.query_selector(".scout-form textarea")  # TODO
        if textarea is None:
            await self._take_screenshot(f"textarea_not_found_{candidate_id}")
            raise RuntimeError("dodaX: テキストエリアが見つかりません。")

        await textarea.click()
        await textarea.press("Control+a")  # 事前入力がある場合に備えて全選択
        await textarea.fill(message)

        # 送信ボタンをクリック
        # TODO: 送信ボタンのセレクターに変更
        await self._safe_click(".scout-form button[type='submit']")  # TODO

        # 送信完了確認
        try:
            # TODO: 送信完了を示す要素のセレクターに変更
            # 例: モーダルが閉じる場合 → wait_for_selector(".scout-form", state="hidden")
            # 例: 完了メッセージが出る場合 → wait_for_selector("text=送信しました")
            await self.page.wait_for_selector(
                "text=送信しました", timeout=15000  # TODO: 要確認
            )
        except PlaywrightTimeoutError:
            await self._take_screenshot(f"send_failed_{candidate_id}")
            raise RuntimeError(
                f"dodaX: 候補者 {candidate_id} への送信完了が確認できませんでした。"
                "スクリーンショットを確認してください。"
            )

        logger.info("dodaX: 候補者 %s へスカウト送信完了", candidate_id)
