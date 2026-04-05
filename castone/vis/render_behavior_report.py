from __future__ import annotations

from collections import Counter, defaultdict

from common import (
    build_parser,
    bullet_list,
    extract_transition_model_info,
    extract_transition_phase,
    extract_transition_step,
    infer_bot_type,
    load_context,
    markdown_table,
    model_snapshot_rows,
    write_output,
)


PASS_ACTION = 15
TRADER_PHASE = 4
CAPTAIN_PHASE = 5


def build_behavior_markdown(ctx, max_steps: int) -> str:
    by_bot = Counter()
    by_phase = Counter()
    trader = Counter()
    captain = Counter()
    trace_rows = []
    valid_widths = defaultdict(list)

    for record in ctx.transitions:
        actor_id = str(record.get("actor_id") or "")
        model_info = extract_transition_model_info(record)
        bot_type = infer_bot_type(actor_id, model_info)
        phase_id = extract_transition_phase(record)
        action = record.get("action")
        action_mask = record.get("action_mask_before") or []
        valid_count = sum(1 for flag in action_mask if flag)

        by_bot[bot_type] += 1
        by_phase[(bot_type, phase_id)] += 1
        valid_widths[(bot_type, phase_id)].append(valid_count)

        if phase_id == TRADER_PHASE:
            trader[(bot_type, "pass" if action == PASS_ACTION else "sell")] += 1
        if phase_id == CAPTAIN_PHASE:
            captain[(bot_type, "pass" if action == PASS_ACTION else "load")] += 1

        if len(trace_rows) < max_steps:
            trace_rows.append(
                [
                    extract_transition_step(record),
                    actor_id,
                    bot_type,
                    phase_id,
                    action,
                    valid_count if action_mask else "",
                    model_info.get("artifact_name", "") if model_info else "",
                ]
            )

    summary_rows = [[bot_type, count] for bot_type, count in sorted(by_bot.items())]
    phase_rows = []
    for (bot_type, phase_id), count in sorted(by_phase.items()):
        widths = valid_widths[(bot_type, phase_id)]
        avg_width = round(sum(widths) / len(widths), 2) if widths else ""
        phase_rows.append([bot_type, phase_id, count, avg_width])

    trader_rows = [[bot_type, action_kind, count] for (bot_type, action_kind), count in sorted(trader.items())]
    captain_rows = [[bot_type, action_kind, count] for (bot_type, action_kind), count in sorted(captain.items())]

    model_rows = model_snapshot_rows(ctx.room)

    flow = """```mermaid
flowchart LR
    A["state_before"] --> B["action_mask_before"]
    B --> C["BotService.get_action()"]
    C --> D["selected action"]
    D --> E["state_after"]
    C --> F["model_info / artifact provenance"]
```"""

    sections = [
        f"# Behavior Report: {ctx.game_id or 'unknown-game'}",
        "",
        "## Warnings",
        bullet_list(ctx.warnings),
        "",
        "## Decision Flow",
        flow,
        "",
        "## Actions by Bot Type",
        markdown_table(["bot_type", "actions"], summary_rows or [["(no transition rows)", "0"]]),
        "",
        "## Phase Distribution",
        markdown_table(["bot_type", "phase_id", "rows", "avg_valid_actions"], phase_rows or [["", "", "", ""]]),
        "",
        "## Trader Behavior",
        markdown_table(["bot_type", "action_kind", "count"], trader_rows or [["(no trader rows)", "", "0"]]),
        "",
        "## Captain Behavior",
        markdown_table(["bot_type", "action_kind", "count"], captain_rows or [["(no captain rows)", "", "0"]]),
        "",
        "## Chronological Trace",
        markdown_table(
            ["step", "actor_id", "bot_type", "phase_id", "action", "valid_action_count", "artifact_name"],
            trace_rows or [["", "", "", "", "", "", ""]],
        ),
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
                "This report can explain selected actions, phase context, and model provenance when JSONL contains model_info/action_mask_before.",
                "Action probabilities/logits are not logged today, so the audit heatmap in audit.md cannot be reproduced exactly yet.",
                "When transition rows come from tests rather than live games, behavior counts will look synthetic.",
            ]
        ),
    ]
    return "\n".join(sections).strip() + "\n"


def main() -> None:
    parser = build_parser("Render a behavior/provenance markdown report for one game.")
    args = parser.parse_args()
    ctx = load_context(
        game_id=args.game_id,
        db_url=args.db_url,
        jsonl_paths=args.jsonl_paths,
    )
    markdown = build_behavior_markdown(ctx, args.max_steps)
    write_output(args.output, markdown)


if __name__ == "__main__":
    main()
