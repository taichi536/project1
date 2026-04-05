"""
Webダッシュボード（Flask）。

機能:
  /                  - サマリーダッシュボード
  /scouts            - 送信済みスカウト一覧
  /scouts/<id>       - スカウト詳細
  /export.csv        - CSV エクスポート
  /mappings          - タグ→テンプレート マッピング管理
  /mappings/add      - マッピング追加（POST）
  /mappings/<id>/delete - マッピング削除（POST）
"""
import csv
import io
import os
import sqlite3
from datetime import datetime, date
from pathlib import Path
from typing import Optional

from flask import Flask, render_template, request, Response, abort, redirect, url_for, flash

from .config import Config
from .database import Database


def create_app(config: Config) -> Flask:
    app = Flask(__name__, template_folder="web_templates")
    app.secret_key = os.urandom(24)
    db = Database(config.db_path)

    # ------------------------------------------------------------------
    # ヘルパー
    # ------------------------------------------------------------------

    def _query(
        platform: Optional[str] = None,
        position: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ):
        """フィルタ付きでスカウト一覧を取得する。"""
        conditions = []
        params: list = []

        if platform:
            conditions.append("platform = ?")
            params.append(platform)
        if position:
            conditions.append("position = ?")
            params.append(position)
        if date_from:
            conditions.append("sent_at >= ?")
            params.append(date_from)
        if date_to:
            conditions.append("sent_at <= ?")
            params.append(date_to + "T23:59:59")
        if search:
            conditions.append("candidate_name LIKE ?")
            params.append(f"%{search}%")

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        with sqlite3.connect(config.db_path) as conn:
            conn.row_factory = sqlite3.Row
            total = conn.execute(
                f"SELECT COUNT(*) FROM sent_scouts {where}", params
            ).fetchone()[0]
            rows = conn.execute(
                f"""
                SELECT id, platform, candidate_id, candidate_name, tag, position,
                       message, success, error, sent_at
                FROM sent_scouts {where}
                ORDER BY sent_at DESC
                LIMIT ? OFFSET ?
                """,
                params + [limit, offset],
            ).fetchall()
        return [dict(r) for r in rows], total

    def _choices(column: str):
        """フィルタ用のユニーク値一覧を返す。"""
        try:
            with sqlite3.connect(config.db_path) as conn:
                rows = conn.execute(
                    f"SELECT DISTINCT {column} FROM sent_scouts WHERE {column} IS NOT NULL ORDER BY {column}"
                ).fetchall()
            return [r[0] for r in rows]
        except Exception:
            return []

    def _today_counts():
        """今日の送信数（プラットフォーム別）。"""
        today = date.today().isoformat()
        try:
            with sqlite3.connect(config.db_path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    """
                    SELECT platform, COUNT(*) as cnt
                    FROM sent_scouts
                    WHERE sent_at LIKE ? AND success=1
                    GROUP BY platform
                    """,
                    (f"{today}%",),
                ).fetchall()
            return {r["platform"]: r["cnt"] for r in rows}
        except Exception:
            return {}

    # ------------------------------------------------------------------
    # ルート
    # ------------------------------------------------------------------

    def _schedule_info() -> dict:
        """スケジュール設定の表示用情報を返す。"""
        if config.allowed_hours:
            desc = f"{config.allowed_hours} 時台の {config.cron_minute} 分"
            mode = "時間帯指定"
        else:
            desc = f"{config.interval_minutes} 分ごと（終日）"
            mode = "インターバル"
        return {"mode": mode, "desc": desc, "allowed_hours": config.allowed_hours}

    @app.route("/")
    def index():
        stats = db.get_stats()
        today_counts = _today_counts()
        recent, _ = _query(limit=10)
        enabled_platforms = [
            name for name, pc in config.platforms.items() if pc.enabled
        ]
        return render_template(
            "index.html",
            stats=stats,
            today_counts=today_counts,
            recent=recent,
            now=datetime.now().strftime("%Y-%m-%d %H:%M"),
            schedule_info=_schedule_info(),
            enabled_platforms=enabled_platforms,
        )

    @app.route("/scouts")
    def scouts():
        platform = request.args.get("platform", "")
        position = request.args.get("position", "")
        date_from = request.args.get("date_from", "")
        date_to = request.args.get("date_to", "")
        search = request.args.get("search", "")
        page = max(1, int(request.args.get("page", 1)))
        per_page = 30

        rows, total = _query(
            platform=platform or None,
            position=position or None,
            date_from=date_from or None,
            date_to=date_to or None,
            search=search or None,
            limit=per_page,
            offset=(page - 1) * per_page,
        )
        total_pages = max(1, (total + per_page - 1) // per_page)

        return render_template(
            "scouts.html",
            rows=rows,
            total=total,
            page=page,
            total_pages=total_pages,
            platform_choices=_choices("platform"),
            position_choices=_choices("position"),
            filters={
                "platform": platform,
                "position": position,
                "date_from": date_from,
                "date_to": date_to,
                "search": search,
            },
        )

    @app.route("/scouts/<int:scout_id>")
    def scout_detail(scout_id: int):
        try:
            with sqlite3.connect(config.db_path) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    "SELECT * FROM sent_scouts WHERE id=?", (scout_id,)
                ).fetchone()
        except Exception:
            row = None

        if not row:
            abort(404)
        return render_template("detail.html", scout=dict(row))

    @app.route("/export.csv")
    def export_csv():
        platform = request.args.get("platform", "")
        position = request.args.get("position", "")
        date_from = request.args.get("date_from", "")
        date_to = request.args.get("date_to", "")

        rows, _ = _query(
            platform=platform or None,
            position=position or None,
            date_from=date_from or None,
            date_to=date_to or None,
            limit=10000,
        )

        output = io.StringIO()
        writer = csv.DictWriter(
            output,
            fieldnames=["id", "platform", "candidate_id", "candidate_name",
                        "tag", "position", "success", "error", "sent_at"],
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)

        filename = f"scouts_{date.today().isoformat()}.csv"
        return Response(
            "\ufeff" + output.getvalue(),  # BOM付き（Excel対応）
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    # ------------------------------------------------------------------
    # マッピング管理
    # ------------------------------------------------------------------

    def _available_templates() -> list[str]:
        """templates/ 以下の .txt ファイル名（拡張子なし）を返す。"""
        d = Path(config.templates_dir)
        if not d.exists():
            return []
        return sorted(p.stem for p in d.glob("*.txt"))

    @app.route("/mappings")
    def mappings():
        all_mappings = db.get_tag_mappings()
        templates = _available_templates()
        platforms = list(config.platforms.keys())
        return render_template(
            "mappings.html",
            mappings=all_mappings,
            templates=templates,
            platforms=platforms,
        )

    @app.route("/mappings/add", methods=["POST"])
    def mappings_add():
        platform = request.form.get("platform", "").strip()
        tag = request.form.get("tag", "").strip()
        position = request.form.get("position", "").strip()
        scout_type = request.form.get("scout_type", "normal").strip()
        note = request.form.get("note", "").strip()

        if not platform or not tag or not position:
            flash("プラットフォーム・タグ名・テンプレートはすべて必須です。", "danger")
            return redirect(url_for("mappings"))

        db.upsert_tag_mapping(platform, tag, position, scout_type, note)
        type_label = {"normal": "通常", "platinum": "プラチナ", "diamond": "ダイヤ"}.get(scout_type, scout_type)
        flash(f"「{platform} / {tag}」→「{position}」({type_label}スカウト) を登録しました。", "success")
        return redirect(url_for("mappings"))

    @app.route("/mappings/<int:mapping_id>/delete", methods=["POST"])
    def mappings_delete(mapping_id: int):
        db.delete_tag_mapping(mapping_id)
        flash("マッピングを削除しました。", "success")
        return redirect(url_for("mappings"))

    # ------------------------------------------------------------------
    # スカウトキュー（タグ機能のないプラットフォーム向け）
    # ------------------------------------------------------------------

    @app.route("/queue")
    def queue():
        items = db.queue_get_all()
        templates = _available_templates()
        platforms = list(config.platforms.keys())
        pending_count = sum(1 for i in items if i["status"] == "pending")
        return render_template(
            "queue.html",
            items=items,
            templates=templates,
            platforms=platforms,
            pending_count=pending_count,
        )

    @app.route("/queue/add", methods=["POST"])
    def queue_add():
        platform = request.form.get("platform", "").strip()
        profile_url = request.form.get("profile_url", "").strip()
        position = request.form.get("position", "").strip()
        candidate_name = request.form.get("candidate_name", "").strip()
        note = request.form.get("note", "").strip()

        if not platform or not profile_url or not position:
            flash("プラットフォーム・URL・ポジションはすべて必須です。", "danger")
            return redirect(url_for("queue"))

        db.queue_add(platform, profile_url, position, candidate_name, note)
        label = candidate_name or profile_url
        flash(f"「{label}」をキューに追加しました。", "success")
        return redirect(url_for("queue"))

    @app.route("/queue/bulk_add", methods=["POST"])
    def queue_bulk_add():
        """複数URLを一括登録する（改行区切り）。"""
        platform = request.form.get("platform", "").strip()
        urls_raw = request.form.get("profile_urls", "").strip()
        position = request.form.get("position", "").strip()

        if not platform or not urls_raw or not position:
            flash("プラットフォーム・URL・ポジションはすべて必須です。", "danger")
            return redirect(url_for("queue"))

        urls = [u.strip() for u in urls_raw.splitlines() if u.strip()]
        for url in urls:
            db.queue_add(platform, url, position)
        flash(f"{len(urls)} 件をキューに追加しました。", "success")
        return redirect(url_for("queue"))

    @app.route("/queue/<int:queue_id>/delete", methods=["POST"])
    def queue_delete(queue_id: int):
        db.queue_delete(queue_id)
        flash("キューから削除しました。", "success")
        return redirect(url_for("queue"))

    return app
