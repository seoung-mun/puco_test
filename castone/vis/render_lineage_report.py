from __future__ import annotations

from common import (
    build_parser,
    build_step_join,
    bullet_list,
    coverage_badge,
    field_coverage,
    load_context,
    markdown_table,
    model_snapshot_rows,
    write_output,
)


def build_lineage_markdown(ctx, max_steps: int) -> str:
    joined = build_step_join(ctx.game_logs, ctx.transitions)
    transition_coverage = field_coverage(
        ctx.transitions,
        [
            "info.round",
            "info.step",
            "action",
            "action_mask_before",
            "phase_id_before",
            "model_info",
        ],
    )

    summary_rows = [
        ["game_id", ctx.game_id or ""],
        ["db_url", ctx.db_url or "(not set)"],
        ["db_game_logs", len(ctx.game_logs)],
        ["jsonl_rows", len(ctx.transitions)],
        ["transition_files", len(ctx.transition_files)],
        ["room_status", ctx.room.status if ctx.room else ""],
        ["players", ", ".join(ctx.room.players) if ctx.room else ""],
    ]

    step_rows = []
    for row in joined[:max_steps]:
        db_log = row["db"]
        jsonl = row["jsonl"]
        step_rows.append(
            [
                row["round"],
                row["step"],
                row["actor_id"],
                db_log.action if db_log else "",
                jsonl.get("action") if jsonl else "",
                "yes" if db_log and db_log.state_summary else "",
                "yes" if jsonl and jsonl.get("model_info") else "",
                "yes" if jsonl and jsonl.get("action_mask_before") is not None else "",
            ]
        )

    coverage_rows = [
        [field_name, coverage_badge(count, total)]
        for field_name, count, total in transition_coverage
    ]

    model_rows = model_snapshot_rows(ctx.room)

    sequence_lines = [
        "sequenceDiagram",
        '    participant Actor as "Human/Bot"',
        '    participant Service as "GameService"',
        '    participant Engine as "EngineWrapper"',
        '    participant DB as "game_logs"',
        '    participant JSONL as "per-game JSONL"',
        '    participant WS as "Redis / WebSocket"',
    ]
    for row in joined[: min(max_steps, 8)]:
        db_log = row["db"]
        jsonl = row["jsonl"]
        action = ""
        if jsonl:
            action = str(jsonl.get("action", ""))
        elif db_log:
            action = str(db_log.action if db_log.action is not None else "")
        actor = row["actor_id"] or "unknown"
        step_label = row["step"] if row["step"] is not None else "?"
        sequence_lines.extend(
            [
                f'    Actor->>Service: action={action} actor={actor} step={step_label}',
                "    Service->>Engine: step(action)",
                f'    Service->>DB: round={row["round"]} step={step_label}',
                f'    Service->>JSONL: transition step={step_label}',
                "    Service->>WS: STATE_UPDATE",
            ]
        )

    mermaid_flow = f"""```mermaid
flowchart LR
    A["PuertoRicoEnv / EngineWrapper"] --> B["BotInputSnapshot\\nobs + mask + phase"]
    A --> C["serialize_game_state_from_engine\\nrich GameState"]
    B --> D["BotService.get_action()"]
    D --> E["GameService.process_action()"]
    E --> F["game_logs\\nrows={len(ctx.game_logs)}"]
    E --> G["per-game JSONL\\nrows={len(ctx.transitions)}"]
    E --> H["Redis + WebSocket\\nSTATE_UPDATE"]
    C --> H
```"""

    mermaid_sequence = "```mermaid\n" + "\n".join(sequence_lines) + "\n```"

    sections = [
        f"# Lineage Report: {ctx.game_id or 'unknown-game'}",
        "",
        "## Data Sources",
        markdown_table(["item", "value"], summary_rows),
        "",
        "## Warnings",
        bullet_list(ctx.warnings),
        "",
        "## Runtime Flow",
        mermaid_flow,
        "",
        "## Step Sequence",
        mermaid_sequence,
        "",
        "## Step Alignment",
        markdown_table(
            ["round", "step", "actor_id", "db_action", "jsonl_action", "db_summary", "jsonl_model", "jsonl_mask"],
            step_rows or [["", "", "", "", "", "", "", ""]],
        ),
        "",
        "## Transition Field Coverage",
        markdown_table(["field", "coverage"], coverage_rows or [["(no jsonl rows)", "0/0"]]),
        "",
        "## Model Snapshot",
        markdown_table(
            ["player", "actor_type", "bot_type", "artifact_name", "checkpoint", "metadata_source"],
            model_rows or [["(not available)", "", "", "", "", ""]],
        ),
        "",
        "## Notes",
        bullet_list(
            [
                "This report joins DB and JSONL rows by (round, step, actor_id). A canonical step_id does not exist yet.",
                "STATE_UPDATE delivery is visible in runtime code, but state_revision/state_hash are not instrumented.",
                "When model_info is present in JSONL, a human can follow which artifact produced a decision.",
            ]
        ),
    ]
    return "\n".join(sections).strip() + "\n"


def main() -> None:
    parser = build_parser("Render a lineage-focused markdown report for one game.")
    args = parser.parse_args()
    ctx = load_context(
        game_id=args.game_id,
        db_url=args.db_url,
        jsonl_paths=args.jsonl_paths,
    )
    markdown = build_lineage_markdown(ctx, args.max_steps)
    write_output(args.output, markdown)


if __name__ == "__main__":
    main()
