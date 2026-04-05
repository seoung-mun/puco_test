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


def build_behavior_markdown(ctx, max_steps: int, lang: str = "en") -> str:
    is_ko = lang == "ko"
    action_label = {
        "pass": "패스" if is_ko else "pass",
        "sell": "판매" if is_ko else "sell",
        "load": "적재" if is_ko else "load",
    }
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
            trader[(bot_type, action_label["pass"] if action == PASS_ACTION else action_label["sell"])] += 1
        if phase_id == CAPTAIN_PHASE:
            captain[(bot_type, action_label["pass"] if action == PASS_ACTION else action_label["load"])] += 1

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
    if is_ko:
        flow = """```mermaid
flowchart LR
    A["행동 전 상태"] --> B["행동 전 액션 마스크"]
    B --> C["BotService.get_action()"]
    C --> D["선택된 액션"]
    D --> E["행동 후 상태"]
    C --> F["model_info / 모델 계보"]
```"""

    sections = [
        f"# {'행동 리포트' if is_ko else 'Behavior Report'}: {ctx.game_id or 'unknown-game'}",
        "",
        f"## {'경고' if is_ko else 'Warnings'}",
        bullet_list(ctx.warnings, empty_label="없음" if is_ko else "none"),
        "",
        f"## {'의사결정 흐름' if is_ko else 'Decision Flow'}",
        flow,
        "",
        f"## {'봇 타입별 액션 수' if is_ko else 'Actions by Bot Type'}",
        markdown_table(
            ["봇 타입", "액션 수"] if is_ko else ["bot_type", "actions"],
            summary_rows or [[("(전이 행 없음)" if is_ko else "(no transition rows)"), "0"]],
        ),
        "",
        f"## {'페이즈 분포' if is_ko else 'Phase Distribution'}",
        markdown_table(
            ["봇 타입", "phase_id", "행 수", "평균 유효 액션 수"] if is_ko else ["bot_type", "phase_id", "rows", "avg_valid_actions"],
            phase_rows or [["", "", "", ""]],
        ),
        "",
        f"## {'상인 행동' if is_ko else 'Trader Behavior'}",
        markdown_table(
            ["봇 타입", "행동 종류", "횟수"] if is_ko else ["bot_type", "action_kind", "count"],
            trader_rows or [[("(상인 행 없음)" if is_ko else "(no trader rows)"), "", "0"]],
        ),
        "",
        f"## {'선장 행동' if is_ko else 'Captain Behavior'}",
        markdown_table(
            ["봇 타입", "행동 종류", "횟수"] if is_ko else ["bot_type", "action_kind", "count"],
            captain_rows or [[("(선장 행 없음)" if is_ko else "(no captain rows)"), "", "0"]],
        ),
        "",
        f"## {'시간순 추적' if is_ko else 'Chronological Trace'}",
        markdown_table(
            ["step", "actor_id", "bot_type", "phase_id", "action", "valid_action_count", "artifact_name"]
            if not is_ko else
            ["step", "actor_id", "봇 타입", "phase_id", "action", "유효 액션 수", "artifact_name"],
            trace_rows or [["", "", "", "", "", "", ""]],
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
                "이 리포트는 JSONL에 model_info/action_mask_before가 있으면 선택 액션, 페이즈 맥락, 모델 계보를 같이 설명할 수 있습니다."
                if is_ko else
                "This report can explain selected actions, phase context, and model provenance when JSONL contains model_info/action_mask_before.",
                "현재는 action probability/logits를 기록하지 않아서 audit.md의 히트맵을 정확히 재현할 수는 없습니다."
                if is_ko else
                "Action probabilities/logits are not logged today, so the audit heatmap in audit.md cannot be reproduced exactly yet.",
                "전이 행이 실제 게임이 아니라 테스트에서 생성된 경우, 행동 카운트는 인공적으로 보일 수 있습니다."
                if is_ko else
                "When transition rows come from tests rather than live games, behavior counts will look synthetic.",
            ],
            empty_label="없음" if is_ko else "none",
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
    markdown = build_behavior_markdown(ctx, args.max_steps, args.lang)
    write_output(args.output, markdown)


if __name__ == "__main__":
    main()
