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


def build_lineage_markdown(ctx, max_steps: int, lang: str = "en") -> str:
    is_ko = lang == "ko"
    yes_label = "예" if is_ko else "yes"
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
        ["db_url", ctx.db_url or ("(설정되지 않음)" if is_ko else "(not set)")],
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
                yes_label if db_log and db_log.state_summary else "",
                yes_label if jsonl and jsonl.get("model_info") else "",
                yes_label if jsonl and jsonl.get("action_mask_before") is not None else "",
            ]
        )

    coverage_rows = [
        [field_name, coverage_badge(count, total, lang)]
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
    if is_ko:
        mermaid_flow = f"""```mermaid
flowchart LR
    A["PuertoRicoEnv / EngineWrapper"] --> B["BotInputSnapshot\\nobs + mask + phase"]
    A --> C["serialize_game_state_from_engine\\nrich GameState"]
    B --> D["BotService.get_action()"]
    D --> E["GameService.process_action()"]
    E --> F["game_logs\\n행 수={len(ctx.game_logs)}"]
    E --> G["게임별 JSONL\\n행 수={len(ctx.transitions)}"]
    E --> H["Redis + WebSocket\\nSTATE_UPDATE"]
    C --> H
```"""

    mermaid_sequence = "```mermaid\n" + "\n".join(sequence_lines) + "\n```"

    sections = [
        f"# {'계보 리포트' if is_ko else 'Lineage Report'}: {ctx.game_id or 'unknown-game'}",
        "",
        f"## {'데이터 소스' if is_ko else 'Data Sources'}",
        markdown_table(["항목", "값"] if is_ko else ["item", "value"], summary_rows),
        "",
        f"## {'경고' if is_ko else 'Warnings'}",
        bullet_list(ctx.warnings, empty_label="없음" if is_ko else "none"),
        "",
        f"## {'런타임 흐름' if is_ko else 'Runtime Flow'}",
        mermaid_flow,
        "",
        f"## {'스텝 시퀀스' if is_ko else 'Step Sequence'}",
        mermaid_sequence,
        "",
        f"## {'스텝 정렬' if is_ko else 'Step Alignment'}",
        markdown_table(
            ["round", "step", "actor_id", "db_action", "jsonl_action", "db_summary", "jsonl_model", "jsonl_mask"]
            if not is_ko else
            ["round", "step", "actor_id", "DB 액션", "JSONL 액션", "DB 요약", "JSONL 모델", "JSONL 마스크"],
            step_rows or [["", "", "", "", "", "", "", ""]],
        ),
        "",
        f"## {'전이 필드 커버리지' if is_ko else 'Transition Field Coverage'}",
        markdown_table(
            ["필드", "커버리지"] if is_ko else ["field", "coverage"],
            coverage_rows or [[("(JSONL 행 없음)" if is_ko else "(no jsonl rows)"), "0/0"]],
        ),
        "",
        f"## {'모델 스냅샷' if is_ko else 'Model Snapshot'}",
        markdown_table(
            ["player", "actor_type", "bot_type", "artifact_name", "checkpoint", "metadata_source"]
            if not is_ko else
            ["player", "행위자 유형", "봇 타입", "artifact_name", "체크포인트", "metadata_source"],
            model_rows or [[("(사용 불가)" if is_ko else "(not available)"), "", "", "", "", ""]],
        ),
        "",
        f"## {'메모' if is_ko else 'Notes'}",
        bullet_list(
            [
                "이 리포트는 DB와 JSONL 행을 (round, step, actor_id)로 조인합니다. canonical step_id는 아직 없습니다."
                if is_ko else
                "This report joins DB and JSONL rows by (round, step, actor_id). A canonical step_id does not exist yet.",
                "STATE_UPDATE 전달은 런타임 코드에서 보이지만 state_revision/state_hash는 아직 계측되지 않았습니다."
                if is_ko else
                "STATE_UPDATE delivery is visible in runtime code, but state_revision/state_hash are not instrumented.",
                "JSONL에 model_info가 있으면 어떤 artifact가 결정을 만들었는지 사람이 추적할 수 있습니다."
                if is_ko else
                "When model_info is present in JSONL, a human can follow which artifact produced a decision.",
            ],
            empty_label="없음" if is_ko else "none",
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
    markdown = build_lineage_markdown(ctx, args.max_steps, args.lang)
    write_output(args.output, markdown)


if __name__ == "__main__":
    main()
