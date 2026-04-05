"""
リクルートダイレクトスカウト（企業向けポータル）アダプター。

【RDSの仕様】
- URLが変わらないSPA構成（候補者を選択しても同じURLのまま）
- 候補者は左ペインのリスト、プロフィールは右ペインに表示される
- タグ機能なし。代わりに「リスト機能」（検討中リスト等）を利用する

【このアダプターの動作】
  get_tagged_candidates(list_name):
    → リスト名で絞り込んだ候補者一覧ページへ遷移
    → 左ペインのカードを順番に処理
    → candidate_id は各カードの DOM 属性から取得

  get_candidate_profile(candidate_id):
    → 既に右ペインが開いていると想定（get_tagged_candidates 内で click 済み）
    → 右ペインからプロフィール情報を読み取る

  send_scout(candidate_id, message):
    → 右ペインの「スカウトを送る」ボタンを押下
    → モーダルに文面を入力して送信

【セレクターの確認方法】
  .env で HEADLESS=false に設定して
  python main.py run --platform recruit_direct --dry-run
  を実行しながら、ブラウザの開発者ツール（F12）で要素を確認してください。
  スクリーンショットは data/screenshots/ に保存されます。
"""
import logging
from typing import List

from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from .base import BasePlatform
from ..models import Candidate, CandidateProfile

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ #
# URL定数（実際のポータルURLに合わせて修正してください）
# ------------------------------------------------------------------ #
LOGIN_URL = "https://directscout.recruit.co.jp/login"

# リスト一覧ページのURL
# リスト名をクエリパラメータ等で絞り込む場合は実際の仕様に合わせて変更
LIST_BASE_URL = "https://directscout.recruit.co.jp/scout/list"


class RecruitDirectPlatform(BasePlatform):
    PLATFORM_NAME = "recruit_direct"

    # ------------------------------------------------------------------
    # ログイン
    # ------------------------------------------------------------------

    async def login(self) -> None:
        logger.info("RDS: ログイン中...")
        await self.page.goto(LOGIN_URL)

        # TODO: 実際のセレクターに変更
        await self._safe_fill('input[type="email"]', self.config.email)
        await self._safe_fill('input[type="password"]', self.config.password)
        await self._safe_click('button[type="submit"]')

        try:
            # TODO: ログイン後に遷移するURLパターンに変更
            await self.page.wait_for_url("**/scout/**", timeout=20000)
        except PlaywrightTimeoutError:
            await self._take_screenshot("login_failed")
            raise RuntimeError("RDS: ログインに失敗しました。スクリーンショットを確認してください。")

        logger.info("RDS: ログイン成功")

    # ------------------------------------------------------------------
    # 候補者リスト取得（リスト名 = タグの代替）
    # ------------------------------------------------------------------

    async def get_tagged_candidates(self, list_name: str) -> List[Candidate]:
        """
        指定リストに入っている候補者を取得する。

        RDSはSPAのため URL は変わらず、左ペインのカードが候補者一覧となる。
        candidate_id は各カードの DOM 属性（data-id 等）から取得する。
        """
        position = self.resolve_position(list_name)
        if not position:
            logger.warning("RDS: リスト '%s' に対応するポジションが未設定です。", list_name)
            return []

        logger.info("RDS: リスト='%s' の候補者を取得中...", list_name)

        # TODO: 実際のリスト絞り込み遷移に変更
        # リスト名でフィルタする場合はクエリパラメータやサイドメニューのクリックを使う
        await self.page.goto(LIST_BASE_URL)
        await self.page.wait_for_load_state("networkidle")

        # TODO: 左ペインのリスト選択（リスト名のメニュー項目をクリック）
        # 例: await self._safe_click(f'[data-list-name="{list_name}"]')
        await self._select_list(list_name)

        candidates: List[Candidate] = []

        # 左ペインの候補者カード一覧を全件処理
        # TODO: 実際の候補者カードのセレクターに変更
        card_selector = ".candidate-card"  # TODO
        await self.page.wait_for_selector(card_selector, timeout=10000)
        cards = await self.page.query_selector_all(card_selector)

        logger.info("RDS: %d 枚のカードを検出", len(cards))

        for card in cards:
            try:
                # TODO: candidate_id の取得方法（data属性 or テキスト等）
                cid = await card.get_attribute("data-candidate-id") or ""  # TODO

                # TODO: 候補者名の取得
                name_el = await card.query_selector(".candidate-name")  # TODO
                name = (await name_el.inner_text()).strip() if name_el else ""

                if not cid:
                    logger.warning("RDS: candidate_id が取得できないカードをスキップ")
                    continue

                candidates.append(
                    Candidate(
                        platform=self.PLATFORM_NAME,
                        candidate_id=cid,
                        name=name,
                        tag=list_name,
                        position=position,
                        profile_url="",  # SPA のため URL なし
                    )
                )
            except Exception as e:
                logger.warning("RDS: カードの解析中にエラー: %s", e)

        logger.info("RDS: %d 名の候補者を取得", len(candidates))
        return candidates

    async def _select_list(self, list_name: str) -> None:
        """
        左ペインでリスト名を選択する。
        TODO: 実際のリスト切替UIに合わせて実装する。

        例1: サイドメニューのリスト名をクリック
          await self._safe_click(f'nav a:has-text("{list_name}")')

        例2: ドロップダウンで選択
          await self._safe_click('.list-filter-dropdown')
          await self._safe_click(f'.list-option:has-text("{list_name}")')
        """
        # TODO: 実際のリスト選択UIに変更
        logger.debug("RDS: リスト '%s' を選択中...", list_name)
        await self.page.wait_for_load_state("networkidle")

    # ------------------------------------------------------------------
    # プロフィール取得（右ペインから読み取る）
    # ------------------------------------------------------------------

    async def get_candidate_profile(self, candidate_id: str) -> CandidateProfile:
        """
        右ペインに表示されているプロフィールを読み取る。

        get_tagged_candidates() でカードを特定した後、
        このメソッドを呼ぶ前にカードをクリックして右ペインに表示させること。
        （runner から呼ばれる際は _click_candidate_card() を事前に実行する）
        """
        # TODO: 右ペインのセレクターに変更
        async def _t(selector: str) -> str:
            el = await self.page.query_selector(selector)
            return (await el.inner_text()).strip() if el else ""

        name = await _t(".profile-pane .name")              # TODO
        job_title = await _t(".profile-pane .job-title")    # TODO
        company = await _t(".profile-pane .company")        # TODO
        career_summary = await _t(".profile-pane .career")  # TODO

        skill_els = await self.page.query_selector_all(".profile-pane .skill-tag")  # TODO
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
        左ペインで指定IDの候補者カードをクリックして右ペインに表示させる。
        TODO: 実際のセレクターに変更
        """
        # TODO: candidate_id を使ってカードを特定しクリック
        card = await self.page.query_selector(
            f'.candidate-card[data-candidate-id="{candidate_id}"]'  # TODO
        )
        if card:
            await card.click()
            # 右ペインのロード待ち
            await self.page.wait_for_load_state("networkidle")
            # TODO: 右ペインに候補者情報が表示されたことを確認するセレクター
            await self.page.wait_for_selector(".profile-pane .name", timeout=8000)  # TODO
        else:
            raise RuntimeError(f"RDS: candidate_id={candidate_id} のカードが見つかりません")

    # ------------------------------------------------------------------
    # スカウト送信
    # ------------------------------------------------------------------

    async def send_scout(self, candidate_id: str, message: str) -> None:
        """
        右ペインの「スカウトを送る」ボタンを押してモーダルに文面を入力・送信する。
        事前に _click_candidate_card() でカードを選択しておくこと。
        """
        # カードをクリックして右ペインに表示
        await self._click_candidate_card(candidate_id)

        # TODO: スカウト送信ボタンのセレクターに変更
        await self._safe_click(".profile-pane .scout-btn")  # TODO

        # モーダルが開くのを待つ
        # TODO: モーダルのセレクターに変更
        await self.page.wait_for_selector(".scout-modal", timeout=8000)  # TODO

        # 文面入力
        # TODO: テキストエリアのセレクターに変更
        await self._safe_fill(".scout-modal textarea", message)  # TODO

        # 送信ボタン
        # TODO: 送信ボタンのセレクターに変更
        await self._safe_click(".scout-modal .submit-btn")  # TODO

        # 送信完了確認
        try:
            # TODO: 送信完了を示す要素のセレクターに変更
            await self.page.wait_for_selector(".scout-modal .complete-msg", timeout=15000)  # TODO
        except PlaywrightTimeoutError:
            await self._take_screenshot(f"send_failed_{candidate_id}")
            raise RuntimeError(
                f"RDS: 候補者 {candidate_id} への送信完了が確認できませんでした。"
                "スクリーンショットを確認してください。"
            )

        logger.info("RDS: 候補者 %s へスカウト送信完了", candidate_id)
