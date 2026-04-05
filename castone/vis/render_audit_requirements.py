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


def build_audit_markdown(ctx) -> str:
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

    audit_rows = [
        [
            "1. Data Lineage & Step Alignment",
            "game_logs + transitions + serializer-backed rich state",
            "; ".join(
                [
                    f"db rows={len(ctx.game_logs)}",
                    f"jsonl rows={len(ctx.transitions)}",
                    f"jsonl step={coverage_badge(*transition_map.get('info.step', (0, 0)))}",
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
                    f"phase={coverage_badge(*transition_map.get('phase_id_before', (0, 0)))}",
                    f"mask={coverage_badge(*transition_map.get('action_mask_before', (0, 0)))}",
                    f"model_info={coverage_badge(*transition_map.get('model_info', (0, 0)))}",
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

    sections = [
        f"# Audit Coverage: {ctx.game_id or 'unknown-game'}",
        "",
        "## Warnings",
        bullet_list(ctx.warnings),
        "",
        "## Audit Visualization Map",
        flow,
        "",
        "## Requirement Coverage",
        markdown_table(
            ["audit item", "current evidence", "coverage", "main gap", "script"],
            audit_rows,
        ),
        "",
        "## Practical Reading",
        bullet_list(
            [
                "If you need to prove state movement end-to-end, start with vis/render_lineage_report.py.",
                "If you need to reconcile DB and local logs, start with vis/render_storage_report.py.",
                "If you need to explain how a bot behaved, start with vis/render_behavior_report.py.",
            ]
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
    markdown = build_audit_markdown(ctx)
    write_output(args.output, markdown)


if __name__ == "__main__":
    main()
