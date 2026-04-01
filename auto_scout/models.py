from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime


@dataclass
class Candidate:
    platform: str
    candidate_id: str
    name: str
    tag: str           # プラットフォーム上のタグ名
    position: str      # タグから解決したポジション名（テンプレート選択に使用）
    profile_url: str


@dataclass
class CandidateProfile:
    candidate_id: str
    platform: str
    name: str
    current_job_title: str = ""
    current_company: str = ""
    skills: List[str] = field(default_factory=list)
    career_summary: str = ""   # Claude に渡すための自由記述テキスト


@dataclass
class ScoutResult:
    candidate: Candidate
    success: bool
    sent_message: Optional[str] = None
    error: Optional[str] = None
    sent_at: datetime = field(default_factory=datetime.now)
