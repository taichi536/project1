"""
スカウト文面生成モジュール。

流れ:
1. ポジション別テンプレートを読み込む
2. 候補者プロフィールを Claude に渡し、1文のパーソナライズ文を生成
3. テンプレートの {{personalized_sentence}} プレースホルダーに挿入して返す
"""
import os
from pathlib import Path

import anthropic

from .models import CandidateProfile


SYSTEM_PROMPT = """あなたは転職エージェントのアシスタントです。
候補者のプロフィール情報を読み取り、スカウト文面に挿入する1文を生成してください。

要件:
- 候補者のキャリアや強みの具体的な部分に触れた、自然で誠実な1文にする
- 馴れ馴れしい表現や過度な称賛は避ける
- 40〜80文字程度で簡潔にまとめる
- 文末は「〜と感じております。」「〜と拝察しております。」など丁寧な表現にする
- 文面全体の流れを損なわない自然な接続を意識する

1文のみを出力してください。前置きや説明は不要です。"""


class MessageGenerator:
    def __init__(self, api_key: str, model: str, templates_dir: str):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.templates_dir = Path(templates_dir)
        self._template_cache: dict[str, str] = {}

    def _load_template(self, position: str) -> str:
        if position in self._template_cache:
            return self._template_cache[position]

        path = self.templates_dir / f"{position}.txt"
        if not path.exists():
            raise FileNotFoundError(
                f"テンプレートが見つかりません: {path}\n"
                f"templates/{position}.txt を作成してください。"
            )
        template = path.read_text(encoding="utf-8")
        self._template_cache[position] = template
        return template

    def _build_profile_text(self, profile: CandidateProfile) -> str:
        parts = [f"氏名: {profile.name}"]
        if profile.current_job_title:
            parts.append(f"現在の職種: {profile.current_job_title}")
        if profile.current_company:
            parts.append(f"現在の会社: {profile.current_company}")
        if profile.skills:
            parts.append(f"スキル: {', '.join(profile.skills)}")
        if profile.career_summary:
            parts.append(f"経歴概要:\n{profile.career_summary}")
        return "\n".join(parts)

    def _generate_personalized_sentence(self, profile: CandidateProfile) -> str:
        profile_text = self._build_profile_text(profile)
        message = self.client.messages.create(
            model=self.model,
            max_tokens=200,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": f"以下の候補者プロフィールに基づいて、スカウト文面に挿入する1文を生成してください。\n\n{profile_text}",
                }
            ],
        )
        sentence = message.content[0].text.strip()
        # 複数文が返ってきた場合は最初の1文だけ使う
        if "。" in sentence:
            sentence = sentence.split("。")[0] + "。"
        return sentence

    def generate(self, profile: CandidateProfile, position: str) -> str:
        """
        テンプレートを読み込み、パーソナライズ文を生成して挿入した完成文面を返す。

        テンプレートには {{personalized_sentence}} プレースホルダーを含めること。
        例:
            〇〇様のご経歴を拝見し、ぜひご連絡させていただきました。
            {{personalized_sentence}}
            つきましては、弊社の〜ポジションをご紹介させていただきたく...
        """
        template = self._load_template(position)
        if "{{personalized_sentence}}" not in template:
            raise ValueError(
                f"テンプレート '{position}.txt' に {{{{personalized_sentence}}}} が含まれていません。"
            )

        personalized = self._generate_personalized_sentence(profile)
        message = template.replace("{{personalized_sentence}}", personalized)
        # 候補者名の差し込み
        message = message.replace("{{candidate_name}}", profile.name)
        return message
