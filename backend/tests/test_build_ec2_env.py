from pathlib import Path

from scripts.build_ec2_env import build_ec2_env, parse_env_mapping, render_ec2_env


def test_render_ec2_env_prefills_server_values_from_source():
    template = """
# comment
POSTGRES_PASSWORD=change-me-strong-db-password
REDIS_PASSWORD=change-me-strong-redis-password
PUBLIC_BACKEND_HOST=3.38.63.58.sslip.io
INTERNAL_API_KEY=change-me-generate-a-random-64-char-hex-string
GOOGLE_CLIENT_ID=your-google-client-id.apps.googleusercontent.com
""".strip()
    source_mapping = {
        "POSTGRES_PASSWORD": "db-secret",
        "REDIS_PASSWORD": "redis-secret",
        "INTERNAL_API_KEY": "internal-secret",
    }

    rendered = render_ec2_env(template, source_mapping)
    parsed = parse_env_mapping(rendered)

    assert parsed["POSTGRES_PASSWORD"] == "db-secret"
    assert parsed["REDIS_PASSWORD"] == "redis-secret"
    assert parsed["INTERNAL_API_KEY"] == "internal-secret"
    assert parsed["PUBLIC_BACKEND_HOST"] == "3.38.63.58.sslip.io"
    assert parsed["GOOGLE_CLIENT_ID"] == "your-google-client-id.apps.googleusercontent.com"


def test_build_ec2_env_reports_remaining_placeholders(tmp_path: Path):
    source_path = tmp_path / "source.env"
    template_path = tmp_path / "template.env"
    output_path = tmp_path / "output.env"

    source_path.write_text(
        "POSTGRES_PASSWORD=db-secret\nINTERNAL_API_KEY=internal-secret\n",
        encoding="utf-8",
    )
    template_path.write_text(
        "\n".join(
            [
                "POSTGRES_PASSWORD=change-me-strong-db-password",
                "REDIS_PASSWORD=change-me-strong-redis-password",
                "INTERNAL_API_KEY=change-me-generate-a-random-64-char-hex-string",
                "GOOGLE_CLIENT_ID=your-google-client-id.apps.googleusercontent.com",
            ]
        ),
        encoding="utf-8",
    )

    placeholders = build_ec2_env(
        source_path=source_path,
        template_path=template_path,
        output_path=output_path,
    )
    parsed = parse_env_mapping(output_path.read_text(encoding="utf-8"))

    assert parsed["POSTGRES_PASSWORD"] == "db-secret"
    assert parsed["INTERNAL_API_KEY"] == "internal-secret"
    assert placeholders == ["REDIS_PASSWORD", "GOOGLE_CLIENT_ID"]
