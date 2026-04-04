"""
スカウト送信のコアオーケストレーションロジック。

1プラットフォーム × 1タグ の処理単位で動作し、
候補者の重複チェック → プロフィール取得 → 文面生成 → 送信 → 記録 を行う。
"""
import asyncio
import logging
from typing import List, Optional

from .config import Config
from .database import Database
from .message_generator import MessageGenerator
from .models import Candidate, ScoutResult
from .platforms import PLATFORM_CLASSES, BasePlatform

logger = logging.getLogger(__name__)


class ScoutRunner:
    def __init__(self, config: Config, dry_run: bool = False):
        self.config = config
        self.dry_run = dry_run
        self.db = Database(config.db_path)
        self.generator = MessageGenerator(
            api_key=config.claude_api_key,
            model=config.claude_model,
            templates_dir=config.templates_dir,
        )

    async def run_all(self) -> List[ScoutResult]:
        """有効な全プラットフォームを順次処理する。"""
        all_results: List[ScoutResult] = []
        for platform_name, platform_config in self.config.platforms.items():
            if not platform_config.enabled:
                logger.debug("%s: 無効のためスキップ", platform_name)
                continue
            results = await self.run_platform(platform_name)
            all_results.extend(results)
        return all_results

    def _resolve_tag_mappings(self, platform_name: str) -> dict:
        """
        タグ→テンプレートのマッピングを解決する。
        DBに登録があればDBを優先し、なければ .env の設定を使う。
        """
        db_mappings = self.db.get_tag_to_position(platform_name)
        if db_mappings:
            logger.debug("%s: DBのマッピングを使用 (%d件)", platform_name, len(db_mappings))
            return db_mappings
        # DB未登録の場合は .env のマッピングにフォールバック
        env_mappings = self.config.platforms[platform_name].tag_to_position
        if env_mappings:
            logger.debug("%s: .envのマッピングを使用 (%d件)", platform_name, len(env_mappings))
        return env_mappings

    async def run_platform(self, platform_name: str) -> List[ScoutResult]:
        """指定プラットフォームのスカウト処理を実行する。"""
        platform_config = self.config.platforms[platform_name]
        platform_cls = PLATFORM_CLASSES.get(platform_name)
        if not platform_cls:
            logger.error("未知のプラットフォーム: %s", platform_name)
            return []

        # DBまたは.envからマッピングを取得してplatform_configに反映
        merged_mappings = self._resolve_tag_mappings(platform_name)
        if not merged_mappings:
            logger.warning(
                "%s: タグマッピングが設定されていません。"
                "ダッシュボードの「マッピング設定」から登録してください。",
                platform_name,
            )
            return []
        platform_config.tag_to_position = merged_mappings

        results: List[ScoutResult] = []
        sent_count = 0

        async with platform_cls(
            platform_config,
            headless=self.config.headless,
            slow_mo_ms=self.config.slow_mo_ms,
        ) as platform:
            try:
                await platform.login()
            except Exception as e:
                logger.error("%s: ログイン失敗 - %s", platform_name, e)
                return []

            for tag in platform.get_all_tags():
                if sent_count >= platform_config.max_scouts_per_run:
                    logger.info(
                        "%s: 上限 %d 件に達しました。残りタグはスキップします。",
                        platform_name,
                        platform_config.max_scouts_per_run,
                    )
                    break

                tag_results = await self._process_tag(
                    platform=platform,
                    tag=tag,
                    remaining_quota=platform_config.max_scouts_per_run - sent_count,
                )
                results.extend(tag_results)
                sent_count += sum(1 for r in tag_results if r.success)

        self._log_summary(platform_name, results)
        return results

    async def _process_tag(
        self,
        platform: BasePlatform,
        tag: str,
        remaining_quota: int,
    ) -> List[ScoutResult]:
        results: List[ScoutResult] = []

        try:
            candidates = await platform.get_tagged_candidates(tag)
        except Exception as e:
            logger.error(
                "%s: タグ '%s' の候補者取得に失敗 - %s", platform.PLATFORM_NAME, tag, e
            )
            return results

        logger.info(
            "%s: タグ '%s' の候補者 %d 名を処理開始",
            platform.PLATFORM_NAME, tag, len(candidates),
        )

        for candidate in candidates:
            if len(results) >= remaining_quota:
                break

            result = await self._process_candidate(platform, candidate)
            if result:
                results.append(result)
                if result.success:
                    await platform._random_delay()

        return results

    async def _process_candidate(
        self, platform: BasePlatform, candidate: Candidate
    ) -> Optional[ScoutResult]:
        # 重複チェック
        if self.db.already_sent(candidate.platform, candidate.candidate_id):
            logger.debug(
                "%s: 候補者 %s (%s) は送信済みのためスキップ",
                candidate.platform, candidate.candidate_id, candidate.name,
            )
            return None

        logger.info(
            "%s: 候補者 %s (%s) を処理中...",
            candidate.platform, candidate.name, candidate.candidate_id,
        )

        # プロフィール取得
        try:
            profile = await platform.get_candidate_profile(candidate.candidate_id)
        except Exception as e:
            logger.warning(
                "%s: 候補者 %s のプロフィール取得失敗 - %s",
                candidate.platform, candidate.candidate_id, e,
            )
            result = ScoutResult(candidate=candidate, success=False, error=str(e))
            self.db.record(result)
            return result

        # 文面生成
        try:
            message = self.generator.generate(profile, candidate.position)
        except Exception as e:
            logger.warning(
                "%s: 候補者 %s の文面生成失敗 - %s",
                candidate.platform, candidate.candidate_id, e,
            )
            result = ScoutResult(candidate=candidate, success=False, error=str(e))
            self.db.record(result)
            return result

        # ドライランモード（送信しない）
        if self.dry_run:
            logger.info(
                "[DRY RUN] %s: 候補者 %s へのスカウト文面:\n%s",
                candidate.platform, candidate.name, message,
            )
            return ScoutResult(candidate=candidate, success=True, sent_message=message)

        # スカウト送信
        try:
            await platform.send_scout(candidate.candidate_id, message)
            result = ScoutResult(candidate=candidate, success=True, sent_message=message)
        except Exception as e:
            logger.error(
                "%s: 候補者 %s へのスカウト送信失敗 - %s",
                candidate.platform, candidate.candidate_id, e,
            )
            result = ScoutResult(candidate=candidate, success=False, error=str(e))

        self.db.record(result)
        return result

    @staticmethod
    def _log_summary(platform_name: str, results: List[ScoutResult]) -> None:
        succeeded = sum(1 for r in results if r.success)
        failed = len(results) - succeeded
        logger.info(
            "%s: 処理完了 - 成功: %d 件, 失敗: %d 件",
            platform_name, succeeded, failed,
        )
