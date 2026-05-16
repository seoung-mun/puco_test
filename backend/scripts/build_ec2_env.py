#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TEMPLATE = ROOT / ".env.ec2.example"
DEFAULT_SOURCE = ROOT / ".env"
DEFAULT_OUTPUT = ROOT / ".env.ec2"
ENV_ASSIGNMENT_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$")


def parse_env_mapping(content: str) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = ENV_ASSIGNMENT_RE.match(raw_line)
        if match is None:
            continue
        key, value = match.groups()
        mapping[key] = value
    return mapping


def render_ec2_env(template_text: str, source_mapping: dict[str, str]) -> str:
    rendered_lines: list[str] = []
    for raw_line in template_text.splitlines():
        match = ENV_ASSIGNMENT_RE.match(raw_line)
        if match is None:
            rendered_lines.append(raw_line)
            continue
        key, _default_value = match.groups()
        if key in source_mapping and source_mapping[key] != "":
            rendered_lines.append(f"{key}={source_mapping[key]}")
        else:
            rendered_lines.append(raw_line)
    return "\n".join(rendered_lines).rstrip() + "\n"


def build_ec2_env(
    *,
    source_path: Path,
    template_path: Path,
    output_path: Path,
) -> list[str]:
    source_mapping = parse_env_mapping(source_path.read_text(encoding="utf-8"))
    template_text = template_path.read_text(encoding="utf-8")
    rendered = render_ec2_env(template_text, source_mapping)
    output_path.write_text(rendered, encoding="utf-8")

    placeholders = []
    for key, value in parse_env_mapping(rendered).items():
        if "change-me" in value or value == "your-google-client-id.apps.googleusercontent.com":
            placeholders.append(key)
    return placeholders


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a slim EC2 env file from an existing local .env.",
    )
    parser.add_argument(
        "--source",
        default=str(DEFAULT_SOURCE),
        help="Source env file. Defaults to repo-root .env.",
    )
    parser.add_argument(
        "--template",
        default=str(DEFAULT_TEMPLATE),
        help="EC2 template file. Defaults to repo-root .env.ec2.example.",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="Output env file path. Defaults to repo-root .env.ec2.",
    )
    args = parser.parse_args()

    placeholders = build_ec2_env(
        source_path=Path(args.source),
        template_path=Path(args.template),
        output_path=Path(args.output),
    )

    print(f"Wrote {args.output}")
    if placeholders:
        joined = ", ".join(placeholders)
        print(f"Review placeholder values before upload: {joined}")
    else:
        print("No placeholder values remain in the generated file.")
    print(
        "Deployment-specific keys to review: "
        "PUBLIC_BACKEND_HOST, ALLOWED_ORIGINS, BACKEND_IMAGE_TAG, GOOGLE_CLIENT_ID"
    )
    print(
        "Remember to set Vercel env vars separately: "
        "VITE_BACKEND_ORIGIN, VITE_GOOGLE_CLIENT_ID, VITE_INTERNAL_API_KEY"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
