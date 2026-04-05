from common import DataContext
from render_audit_requirements import build_audit_markdown
from render_behavior_report import build_behavior_markdown
from render_lineage_report import build_lineage_markdown
from render_storage_report import build_storage_markdown


def _ctx() -> DataContext:
    return DataContext(
        game_id="game-123",
        db_url=None,
        room=None,
        game_logs=[],
        transitions=[],
        transition_files=[],
        warnings=[],
    )


def test_behavior_report_supports_korean():
    markdown = build_behavior_markdown(_ctx(), max_steps=3, lang="ko")

    assert "# 행동 리포트: game-123" in markdown
    assert "## 경고" in markdown
    assert "## 의사결정 흐름" in markdown


def test_storage_report_supports_korean():
    markdown = build_storage_markdown(_ctx(), max_steps=3, lang="ko")

    assert "# 저장소 리포트: game-123" in markdown
    assert "## 저장 토폴로지" in markdown
    assert "## 메모" in markdown


def test_lineage_report_supports_korean():
    markdown = build_lineage_markdown(_ctx(), max_steps=3, lang="ko")

    assert "# 계보 리포트: game-123" in markdown
    assert "## 데이터 소스" in markdown
    assert "## 전이 필드 커버리지" in markdown


def test_audit_report_supports_korean():
    markdown = build_audit_markdown(_ctx(), lang="ko")

    assert "# 감사 커버리지: game-123" in markdown
    assert "## 감사 시각화 맵" in markdown
    assert "## 실전 읽기 순서" in markdown
