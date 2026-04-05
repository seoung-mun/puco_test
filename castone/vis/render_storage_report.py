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


def build_storage_markdown(ctx, max_steps: int) -> str:
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

    mismatch_rows = []
    for row in (missing_db[:max_steps] + missing_jsonl[:max_steps]):
        mismatch_rows.append(
            [
                row["round"],
                row["step"],
                row["actor_id"],
                "missing" if row["db"] is None else "present",
                "missing" if row["jsonl"] is None else "present",
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
        f"# Storage Report: {ctx.game_id or 'unknown-game'}",
        "",
        "## Summary",
        markdown_table(["item", "value"], summary_rows),
        "",
        "## Storage Topology",
        flow,
        "",
        "## Warnings",
        bullet_list(ctx.warnings),
        "",
        "## Chain Integrity",
        markdown_table(["source", "break_count", "sample_breaks"], chain_rows),
        "",
        "## Reconciliation Gaps",
        markdown_table(
            ["round", "step", "actor_id", "db", "jsonl"],
            mismatch_rows or [["(none)", "", "", "", ""]],
        ),
        "",
        "## Notes",
        bullet_list(
            [
                "Current storage layers are DB game_logs, per-game JSONL transitions, and Redis for delivery/cache.",
                "A canonical reconciliation key such as step_id/state_hash is not implemented yet.",
                "DB and JSONL continuity checks are best-effort because state_before/state_after are compared as serialized JSON blobs.",
            ]
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
    markdown = build_storage_markdown(ctx, args.max_steps)
    write_output(args.output, markdown)


if __name__ == "__main__":
    main()
