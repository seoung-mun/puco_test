from __future__ import annotations

from common import (
    build_parser,
    bullet_list,
    coverage_badge,
    field_coverage,
    load_context,
    markdown_table,
    write_output,
)


def _count_game_logs_with_model_info(game_logs) -> int:
    return sum(1 for log in game_logs if isinstance(log.action_data, dict) and log.action_data.get("model_info"))


def build_audit_markdown(ctx, lang: str = "en") -> str:
    is_ko = lang == "ko"
    transition_fields = field_coverage(
        ctx.transitions,
        [
            "info.step",
            "action_mask_before",
            "phase_id_before",
            "model_info",
        ],
    )
    transition_map = {field_name: (count, total) for field_name, count, total in transition_fields}

    if is_ko:
        audit_rows = [
            [
                "1. 데이터 계보 및 스텝 정렬",
                "game_logs + transitions + serializer 기반 rich state",
                "; ".join(
                    [
                        f"db rows={len(ctx.game_logs)}",
                        f"jsonl rows={len(ctx.transitions)}",
                        f"jsonl step={coverage_badge(*transition_map.get('info.step', (0, 0)), lang)}",
                    ]
                ),
                "canonical step_id 또는 state_hash가 없음",
                "vis/render_lineage_report.py",
            ],
            [
                "2. 결정론 및 재현성",
                "backend/tests/test_governor_assignment.py 에 seeded governor 테스트가 있음",
                "state/DB에 room model_versions 스냅샷이 존재함" if ctx.room and ctx.room.model_versions else "seed/governor 근거가 대부분 테스트에 치우쳐 있음",
                "runtime game_logs/JSONL에 seed가 각인되지 않음",
                "vis/render_audit_requirements.py",
            ],
            [
                "3. 행동 추적 가능성",
                "action, phase_id_before, action_mask_before, model_info",
                "; ".join(
                    [
                        f"phase={coverage_badge(*transition_map.get('phase_id_before', (0, 0)), lang)}",
                        f"mask={coverage_badge(*transition_map.get('action_mask_before', (0, 0)), lang)}",
                        f"model_info={coverage_badge(*transition_map.get('model_info', (0, 0)), lang)}",
                        f"db model_info={_count_game_logs_with_model_info(ctx.game_logs)}/{len(ctx.game_logs)}",
                    ]
                ),
                "action probability / logits 로깅이 없음",
                "vis/render_behavior_report.py",
            ],
            [
                "4. 저장 무결성",
                "games + game_logs + 게임별 JSONL + state_summary",
                "; ".join(
                    [
                        f"game_logs={len(ctx.game_logs)}",
                        f"transitions={len(ctx.transitions)}",
                        f"state_summary={sum(1 for log in ctx.game_logs if log.state_summary)}/{len(ctx.game_logs)}",
                    ]
                ),
                "DB/JSONL/replay를 가로지르는 자동 reconciliation key가 없음",
                "vis/render_storage_report.py",
            ],
            [
                "5. 온라인 모니터링",
                "timestamps + 코드상의 WS disconnect/game-ended 이벤트",
                "WS 이벤트는 있으나 runtime revision/latency metric이 없음",
                "state_revision, end-to-screen latency, inference latency metric이 없음",
                "vis/render_lineage_report.py",
            ],
        ]
    else:
        audit_rows = [
            [
                "1. Data Lineage & Step Alignment",
                "game_logs + transitions + serializer-backed rich state",
                "; ".join(
                    [
                        f"db rows={len(ctx.game_logs)}",
                        f"jsonl rows={len(ctx.transitions)}",
                        f"jsonl step={coverage_badge(*transition_map.get('info.step', (0, 0)), lang)}",
                    ]
                ),
                "No canonical step_id or state_hash",
                "vis/render_lineage_report.py",
            ],
            [
                "2. Determinism & Reproducibility",
                "seeded governor tests exist in backend/tests/test_governor_assignment.py",
                "room model_versions snapshot available in state/DB" if ctx.room and ctx.room.model_versions else "seed/governor evidence mostly test-only",
                "seed is not stamped into runtime game_logs/JSONL",
                "vis/render_audit_requirements.py",
            ],
            [
                "3. Behavioral Traceability",
                "action, phase_id_before, action_mask_before, model_info",
                "; ".join(
                    [
                        f"phase={coverage_badge(*transition_map.get('phase_id_before', (0, 0)), lang)}",
                        f"mask={coverage_badge(*transition_map.get('action_mask_before', (0, 0)), lang)}",
                        f"model_info={coverage_badge(*transition_map.get('model_info', (0, 0)), lang)}",
                        f"db model_info={_count_game_logs_with_model_info(ctx.game_logs)}/{len(ctx.game_logs)}",
                    ]
                ),
                "No action probability / logits logging",
                "vis/render_behavior_report.py",
            ],
            [
                "4. Storage Integrity",
                "games + game_logs + per-game JSONL + state_summary",
                "; ".join(
                    [
                        f"game_logs={len(ctx.game_logs)}",
                        f"transitions={len(ctx.transitions)}",
                        f"state_summary={sum(1 for log in ctx.game_logs if log.state_summary)}/{len(ctx.game_logs)}",
                    ]
                ),
                "No automated reconciliation key across DB/JSONL/replay",
                "vis/render_storage_report.py",
            ],
            [
                "5. Online Monitoring",
                "timestamps + WS disconnect/game-ended events in code",
                "WS events exist, but runtime revision/latency metrics are absent",
                "No state_revision, no end-to-screen latency metric, no inference latency metric",
                "vis/render_lineage_report.py",
            ],
        ]

    flow = """```mermaid
flowchart TD
    A["audit.md requirement"] --> B["lineage report"]
    A --> C["storage report"]
    A --> D["behavior report"]
    B --> E["step alignment evidence"]
    C --> F["DB / JSONL integrity evidence"]
    D --> G["phase / model provenance evidence"]
```"""
    if is_ko:
        flow = """```mermaid
flowchart TD
    A["audit.md 요구사항"] --> B["계보 리포트"]
    A --> C["저장소 리포트"]
    A --> D["행동 리포트"]
    B --> E["step 정렬 근거"]
    C --> F["DB / JSONL 무결성 근거"]
    D --> G["phase / 모델 계보 근거"]
```"""

    sections = [
        f"# {'감사 커버리지' if is_ko else 'Audit Coverage'}: {ctx.game_id or 'unknown-game'}",
        "",
        f"## {'경고' if is_ko else 'Warnings'}",
        bullet_list(ctx.warnings, empty_label="없음" if is_ko else "none"),
        "",
        f"## {'감사 시각화 맵' if is_ko else 'Audit Visualization Map'}",
        flow,
        "",
        f"## {'요구사항 커버리지' if is_ko else 'Requirement Coverage'}",
        markdown_table(
            ["감사 항목", "현재 근거", "커버리지", "주요 공백", "스크립트"]
            if is_ko else
            ["audit item", "current evidence", "coverage", "main gap", "script"],
            audit_rows,
        ),
        "",
        f"## {'실전 읽기 순서' if is_ko else 'Practical Reading'}",
        bullet_list(
            [
                "상태 이동을 end-to-end로 증명해야 하면 vis/render_lineage_report.py부터 보세요."
                if is_ko else
                "If you need to prove state movement end-to-end, start with vis/render_lineage_report.py.",
                "DB와 로컬 로그를 대조해야 하면 vis/render_storage_report.py부터 보세요."
                if is_ko else
                "If you need to reconcile DB and local logs, start with vis/render_storage_report.py.",
                "봇 행동을 설명해야 하면 vis/render_behavior_report.py부터 보세요."
                if is_ko else
                "If you need to explain how a bot behaved, start with vis/render_behavior_report.py.",
            ],
            empty_label="없음" if is_ko else "none",
        ),
    ]
    return "\n".join(sections).strip() + "\n"


def main() -> None:
    parser = build_parser("Render a markdown map from audit.md requirements to available evidence.")
    args = parser.parse_args()
    ctx = load_context(
        game_id=args.game_id,
        db_url=args.db_url,
        jsonl_paths=args.jsonl_paths,
    )
    markdown = build_audit_markdown(ctx, args.lang)
    write_output(args.output, markdown)


if __name__ == "__main__":
    main()
