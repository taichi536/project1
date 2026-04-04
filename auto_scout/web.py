"""
Webダッシュボード（Flask）。

機能:
  /            - サマリーダッシュボード（プラットフォーム別統計・直近のスカウト）
  /scouts      - 送信済みスカウト一覧（プラットフォーム・ポジション・日付でフィルタ可）
  /scouts/<id> - スカウト詳細（送信文面全文）
  /export.csv  - CSV エクスポート
"""
import csv
import io
import sqlite3
from datetime import datetime, date
from typing import Optional

from flask import Flask, render_template, request, Response, abort

from .config import Config
from .database import Database


def create_app(config: Config) -> Flask:
    app = Flask(__name__, template_folder="web_templates")
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

    return app
