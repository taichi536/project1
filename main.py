#!/usr/bin/env python3
"""
自動スカウト送信システム - エントリーポイント

使い方:
  # 一度だけ実行（全プラットフォーム）
  python main.py run

  # 特定プラットフォームのみ実行
  python main.py run --platform doda

  # 送信せずに文面を確認（ドライラン）
  python main.py run --dry-run

  # 定期実行モード（.env の SCHEDULE_INTERVAL_MINUTES ごとに実行）
  python main.py schedule

  # 送信統計を表示
  python main.py stats
"""
import asyncio
import logging
import sys

import click
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from auto_scout.config import load_config
from auto_scout.database import Database
from auto_scout.runner import ScoutRunner

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("data/auto_scout.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


@click.group()
def cli():
    """転職サービス 自動スカウト送信システム"""


@cli.command()
@click.option("--platform", default=None, help="対象プラットフォーム名（省略時は全プラットフォーム）")
@click.option("--dry-run", is_flag=True, default=False, help="スカウトを送信せず文面のみ確認する")
def run(platform: str, dry_run: bool):
    """スカウト送信を一度だけ実行する。"""
    config = load_config()
    runner = ScoutRunner(config, dry_run=dry_run)

    if dry_run:
        logger.info("=== ドライランモード：スカウトは送信されません ===")

    async def _run():
        if platform:
            if platform not in config.platforms:
                click.echo(f"エラー: 不明なプラットフォーム '{platform}'")
                click.echo(f"利用可能: {', '.join(config.platforms.keys())}")
                return
            results = await runner.run_platform(platform)
        else:
            results = await runner.run_all()

        succeeded = sum(1 for r in results if r.success)
        click.echo(f"\n完了: {succeeded}/{len(results)} 件のスカウトを送信しました。")

    asyncio.run(_run())


@cli.command()
def schedule():
    """定期実行モードで起動する。"""
    config = load_config()
    runner = ScoutRunner(config)

    async def _job():
        logger.info("スケジュール実行開始")
        await runner.run_all()

    async def _start():
        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            _job,
            "interval",
            minutes=config.interval_minutes,
            id="auto_scout",
        )
        scheduler.start()
        logger.info(
            "スケジューラー起動: %d 分ごとに実行します。Ctrl+C で停止。",
            config.interval_minutes,
        )
        # 初回はすぐに実行
        await _job()
        # 無限ループ
        try:
            while True:
                await asyncio.sleep(60)
        except (KeyboardInterrupt, SystemExit):
            scheduler.shutdown()

    asyncio.run(_start())


@cli.command()
def stats():
    """プラットフォームごとのスカウト送信統計を表示する。"""
    config = load_config()
    db = Database(config.db_path)
    data = db.get_stats()

    if not data:
        click.echo("まだスカウト送信履歴がありません。")
        return

    click.echo("\n=== スカウト送信統計 ===")
    for platform, stat in data.items():
        click.echo(
            f"  {platform:20s}  合計: {stat['total']:4d} 件  "
            f"成功: {stat['succeeded']:4d} 件  "
            f"最終送信: {stat['last_sent'] or 'なし'}"
        )


if __name__ == "__main__":
    cli()
