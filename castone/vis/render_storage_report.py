from __future__ import annotations

from common import (
    build_parser,
    build_step_join,
    bullet_list,
    count_chain_breaks,
    load_context,
    markdown_table,
    write_output,
)


def build_storage_markdown(ctx, max_steps: int, lang: str = "en") -> str:
    is_ko = lang == "ko"
    present_label = "있음" if is_ko else "present"
    missing_label = "누락" if is_ko else "missing"
    joined = build_step_join(ctx.game_logs, ctx.transitions)
    missing_db = [row for row in joined if row["jsonl"] and not row["db"]]
    missing_jsonl = [row for row in joined if row["db"] and not row["jsonl"]]

    db_break_count, db_breaks = count_chain_breaks(
        ctx.game_logs,
        get_before=lambda item: item.state_before,
        get_after=lambda item: item.state_after,
    )
    jsonl_break_count, jsonl_breaks = count_chain_breaks(
        ctx.transitions,
        get_before=lambda item: item.get("state_before"),
        get_after=lambda item: item.get("state_after"),
    )

    flow = f"""```mermaid
flowchart TD
    A["GameService.process_action"] --> B["PostgreSQL game_logs\\nrows={len(ctx.game_logs)}"]
    A --> C["per-game JSONL transitions\\nrows={len(ctx.transitions)}"]
    A --> D["Redis state/events"]
    B --> E["Admin / audit queries"]
    C --> F["ML / replay analysis"]
    D --> G["WebSocket delivery"]
```"""
    if is_ko:
        flow = f"""```mermaid
flowchart TD
    A["GameService.process_action"] --> B["PostgreSQL game_logs\\n행 수={len(ctx.game_logs)}"]
    A --> C["게임별 JSONL 전이\\n행 수={len(ctx.transitions)}"]
    A --> D["Redis 상태/이벤트"]
    B --> E["관리 / 감사 조회"]
    C --> F["ML / 리플레이 분석"]
    D --> G["WebSocket 전달"]
```"""

    mismatch_rows = []
    for row in (missing_db[:max_steps] + missing_jsonl[:max_steps]):
        mismatch_rows.append(
            [
                row["round"],
                row["step"],
                row["actor_id"],
                missing_label if row["db"] is None else present_label,
                missing_label if row["jsonl"] is None else present_label,
            ]
        )

    summary_rows = [
        ["game_id", ctx.game_id or ""],
        ["db_game_logs", len(ctx.game_logs)],
        ["jsonl_rows", len(ctx.transitions)],
        ["joined_rows", len(joined)],
        ["db_chain_breaks", db_break_count],
        ["jsonl_chain_breaks", jsonl_break_count],
        ["db_only_rows", len(missing_jsonl)],
        ["jsonl_only_rows", len(missing_db)],
    ]

    chain_rows = [
        ["game_logs", db_break_count, ", ".join(f"{a}->{b}" for a, b in db_breaks[:8]) or "-"],
        ["per-game JSONL", jsonl_break_count, ", ".join(f"{a}->{b}" for a, b in jsonl_breaks[:8]) or "-"],
    ]

    sections = [
        f"# {'저장소 리포트' if is_ko else 'Storage Report'}: {ctx.game_id or 'unknown-game'}",
        "",
        f"## {'요약' if is_ko else 'Summary'}",
        markdown_table(["항목", "값"] if is_ko else ["item", "value"], summary_rows),
        "",
        f"## {'저장 토폴로지' if is_ko else 'Storage Topology'}",
        flow,
        "",
        f"## {'경고' if is_ko else 'Warnings'}",
        bullet_list(ctx.warnings, empty_label="없음" if is_ko else "none"),
        "",
        f"## {'체인 무결성' if is_ko else 'Chain Integrity'}",
        markdown_table(["소스", "끊김 수", "예시"] if is_ko else ["source", "break_count", "sample_breaks"], chain_rows),
        "",
        f"## {'대조 누락 구간' if is_ko else 'Reconciliation Gaps'}",
        markdown_table(
            ["round", "step", "actor_id", "DB", "JSONL"] if is_ko else ["round", "step", "actor_id", "db", "jsonl"],
            mismatch_rows or [[("(없음)" if is_ko else "(none)"), "", "", "", ""]],
        ),
        "",
        f"## {'메모' if is_ko else 'Notes'}",
        bullet_list(
            [
                "현재 저장 계층은 DB game_logs, 게임별 JSONL 전이, Redis 전달/캐시입니다."
                if is_ko else
                "Current storage layers are DB game_logs, per-game JSONL transitions, and Redis for delivery/cache.",
                "step_id/state_hash 같은 canonical reconciliation key는 아직 구현되지 않았습니다."
                if is_ko else
                "A canonical reconciliation key such as step_id/state_hash is not implemented yet.",
                "DB와 JSONL 연속성 검사는 state_before/state_after 직렬화 JSON을 비교하는 best-effort 방식입니다."
                if is_ko else
                "DB and JSONL continuity checks are best-effort because state_before/state_after are compared as serialized JSON blobs.",
            ],
            empty_label="없음" if is_ko else "none",
        ),
    ]
    return "\n".join(sections).strip() + "\n"


def main() -> None:
    parser = build_parser("Render a storage-integrity markdown report for one game.")
    args = parser.parse_args()
    ctx = load_context(
        game_id=args.game_id,
        db_url=args.db_url,
        jsonl_paths=args.jsonl_paths,
    )
    markdown = build_storage_markdown(ctx, args.max_steps, args.lang)
    write_output(args.output, markdown)


if __name__ == "__main__":
    main()
