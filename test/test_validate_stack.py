"""Tests for scripts/validate_stack.py.

Most tests build a small stack inside a tmp_path directory and run the
validator as a subprocess so exit codes are exercised for real. A few
unit tests import the module directly to check parser helpers.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
VALIDATOR = SCRIPTS_DIR / "validate_stack.py"

sys.dont_write_bytecode = True
sys.path.insert(0, str(SCRIPTS_DIR))

import validate_stack as vs  # noqa: E402

REAL_REPO = Path(os.environ.get("REPO", str(Path(__file__).resolve().parents[1])))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

BASE_COMPOSE = """\
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-n8n}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    ports:
      - "127.0.0.1:5433:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-n8n}"]
  n8n:
    image: n8nio/n8n:1.64.0
    environment:
      - N8N_HOST=${N8N_HOST:-localhost}
      - N8N_ENCRYPTION_KEY=${N8N_ENCRYPTION_KEY}
    ports:
      - "127.0.0.1:5678:5678"
"""

BASE_ENV = """\
# example environment file
POSTGRES_USER=n8n
POSTGRES_PASSWORD=changeme
N8N_HOST=localhost
N8N_ENCRYPTION_KEY=changeme
"""


def build_stack(tmp_path, compose=BASE_COMPOSE, env=BASE_ENV):
    """Write a stack fixture and return the repo directory."""
    (tmp_path / "docker-compose.yml").write_text(compose, encoding="utf-8")
    (tmp_path / ".env.example").write_text(env, encoding="utf-8")
    return tmp_path


def run_validator(repo, *flags):
    """Run the validator as a subprocess and return the completed process."""
    return subprocess.run(
        [sys.executable, "-I", "-B", str(VALIDATOR), "--repo", str(repo), *flags],
        capture_output=True,
        text=True,
    )


def add_workflow(repo, name, payload=None):
    wf_dir = repo / "workflows"
    wf_dir.mkdir(exist_ok=True)
    if payload is None:
        payload = {"name": name, "nodes": []}
    target = wf_dir / f"{name}.json"
    target.write_text(json.dumps(payload), encoding="utf-8")
    return target


# ---------------------------------------------------------------------------
# End to end: clean stacks
# ---------------------------------------------------------------------------


def test_valid_stack_passes(tmp_path):
    repo = build_stack(tmp_path)
    proc = run_validator(repo)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "STACK OK" in proc.stdout


def test_valid_stack_reports_zero_errors_and_zero_warnings(tmp_path):
    repo = build_stack(tmp_path)
    proc = run_validator(repo)
    assert "result: 0 errors, 0 warnings" in proc.stdout


def test_valid_stack_notes_which_parser_was_used(tmp_path):
    repo = build_stack(tmp_path)
    proc = run_validator(repo)
    assert "docker-compose.yml parsed with" in proc.stdout


# ---------------------------------------------------------------------------
# End to end: environment variables
# ---------------------------------------------------------------------------


def test_missing_required_env_var_fails(tmp_path):
    env = BASE_ENV.replace("POSTGRES_PASSWORD=changeme\n", "")
    repo = build_stack(tmp_path, env=env)
    proc = run_validator(repo)
    assert proc.returncode == 1
    assert "POSTGRES_PASSWORD" in proc.stdout
    assert "not defined in .env.example" in proc.stdout
    assert "STACK FAILED" in proc.stdout


def test_missing_env_var_with_default_warns_but_passes(tmp_path):
    env = BASE_ENV.replace("POSTGRES_USER=n8n\n", "")
    repo = build_stack(tmp_path, env=env)
    proc = run_validator(repo)
    assert proc.returncode == 0
    assert "WARN" in proc.stdout
    assert "POSTGRES_USER" in proc.stdout


def test_missing_defaulted_env_var_fails_under_strict(tmp_path):
    env = BASE_ENV.replace("POSTGRES_USER=n8n\n", "")
    repo = build_stack(tmp_path, env=env)
    proc = run_validator(repo, "--strict")
    assert proc.returncode == 1


def test_env_reference_inside_healthcheck_is_checked(tmp_path):
    compose = BASE_COMPOSE.replace(
        '["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-n8n}"]',
        '["CMD-SHELL", "check --token ${HEALTHCHECK_TOKEN}"]',
    )
    repo = build_stack(tmp_path, compose=compose)
    proc = run_validator(repo)
    assert proc.returncode == 1
    assert "HEALTHCHECK_TOKEN" in proc.stdout


def test_env_reference_inside_port_binding_is_checked(tmp_path):
    compose = BASE_COMPOSE.replace('"127.0.0.1:5678:5678"', '"127.0.0.1:${N8N_PORT}:5678"')
    repo = build_stack(tmp_path, compose=compose)
    proc = run_validator(repo)
    assert proc.returncode == 1
    assert "N8N_PORT" in proc.stdout


def test_missing_env_example_file_fails(tmp_path):
    repo = build_stack(tmp_path)
    (repo / ".env.example").unlink()
    proc = run_validator(repo)
    assert proc.returncode == 1
    assert ".env.example not found" in proc.stdout


def test_unused_env_example_var_is_a_note_not_an_issue(tmp_path):
    env = BASE_ENV + "TOTALLY_UNUSED_VAR=1\n"
    repo = build_stack(tmp_path, env=env)
    proc = run_validator(repo)
    assert proc.returncode == 0
    assert "NOTE" in proc.stdout
    assert "TOTALLY_UNUSED_VAR" in proc.stdout


# ---------------------------------------------------------------------------
# End to end: image pins
# ---------------------------------------------------------------------------


def test_latest_tag_image_is_flagged(tmp_path):
    compose = BASE_COMPOSE.replace("n8nio/n8n:1.64.0", "n8nio/n8n:latest")
    repo = build_stack(tmp_path, compose=compose)
    proc = run_validator(repo)
    assert proc.returncode == 0
    assert "WARN" in proc.stdout
    assert "n8nio/n8n:latest" in proc.stdout
    assert "latest" in proc.stdout


def test_untagged_image_is_flagged(tmp_path):
    compose = BASE_COMPOSE.replace("postgres:16-alpine", "postgres")
    repo = build_stack(tmp_path, compose=compose)
    proc = run_validator(repo)
    assert proc.returncode == 0
    assert "postgres has no version tag" in proc.stdout


def test_digest_pinned_image_is_accepted(tmp_path):
    compose = BASE_COMPOSE.replace(
        "postgres:16-alpine", "postgres@sha256:0123456789abcdef0123456789abcdef0123456789abcdef"
    )
    repo = build_stack(tmp_path, compose=compose)
    proc = run_validator(repo)
    assert proc.returncode == 0
    assert "result: 0 errors, 0 warnings" in proc.stdout


def test_image_with_variable_reference_is_not_flagged(tmp_path):
    compose = BASE_COMPOSE.replace("postgres:16-alpine", "${POSTGRES_IMAGE}")
    env = BASE_ENV + "POSTGRES_IMAGE=postgres:16-alpine\n"
    repo = build_stack(tmp_path, compose=compose, env=env)
    proc = run_validator(repo)
    assert proc.returncode == 0
    assert "result: 0 errors, 0 warnings" in proc.stdout


# ---------------------------------------------------------------------------
# End to end: port conflicts
# ---------------------------------------------------------------------------


def test_duplicate_host_port_is_flagged(tmp_path):
    compose = BASE_COMPOSE.replace('"127.0.0.1:5678:5678"', '"127.0.0.1:5433:5678"')
    repo = build_stack(tmp_path, compose=compose)
    proc = run_validator(repo)
    assert proc.returncode == 0
    assert "WARN" in proc.stdout
    assert "host port 5433 is bound more than once" in proc.stdout
    assert "postgres" in proc.stdout
    assert "n8n" in proc.stdout


def test_duplicate_host_port_exits_zero_without_strict(tmp_path):
    compose = BASE_COMPOSE.replace('"127.0.0.1:5678:5678"', '"127.0.0.1:5433:5678"')
    repo = build_stack(tmp_path, compose=compose)
    proc = run_validator(repo)
    assert proc.returncode == 0
    assert "STACK OK (with warnings)" in proc.stdout


def test_duplicate_host_port_exits_one_with_strict(tmp_path):
    compose = BASE_COMPOSE.replace('"127.0.0.1:5678:5678"', '"127.0.0.1:5433:5678"')
    repo = build_stack(tmp_path, compose=compose)
    proc = run_validator(repo, "--strict")
    assert proc.returncode == 1


def test_port_conflict_through_default_values_is_detected(tmp_path):
    compose = BASE_COMPOSE.replace(
        '"127.0.0.1:5433:5432"', '"127.0.0.1:${PG_PORT:-9000}:5432"'
    ).replace('"127.0.0.1:5678:5678"', '"127.0.0.1:${N8N_PORT_DUP:-9000}:5678"')
    repo = build_stack(tmp_path, compose=compose)
    proc = run_validator(repo)
    assert "host port 9000 is bound more than once" in proc.stdout


def test_port_conflict_through_env_file_values_is_detected(tmp_path):
    compose = BASE_COMPOSE.replace(
        '"127.0.0.1:5433:5432"', '"127.0.0.1:${PG_PORT}:5432"'
    ).replace('"127.0.0.1:5678:5678"', '"127.0.0.1:${N8N_PORT_DUP}:5678"')
    env = BASE_ENV + "PG_PORT=9100\nN8N_PORT_DUP=9100\n"
    repo = build_stack(tmp_path, compose=compose, env=env)
    proc = run_validator(repo)
    assert "host port 9100 is bound more than once" in proc.stdout


def test_duplicate_binding_inside_one_service_is_flagged(tmp_path):
    compose = BASE_COMPOSE.replace(
        '      - "127.0.0.1:5678:5678"\n',
        '      - "127.0.0.1:5678:5678"\n      - "5678:5678"\n',
    )
    repo = build_stack(tmp_path, compose=compose)
    proc = run_validator(repo)
    assert "host port 5678 is bound more than once" in proc.stdout


def test_distinct_ports_produce_no_port_warning(tmp_path):
    repo = build_stack(tmp_path)
    proc = run_validator(repo)
    assert "host port" not in proc.stdout


# ---------------------------------------------------------------------------
# End to end: workflow files
# ---------------------------------------------------------------------------


def test_missing_workflow_path_reference_fails(tmp_path):
    repo = build_stack(tmp_path)
    (repo / "README.md").write_text(
        "Import the bundled workflow: workflows/does-not-exist.json\n", encoding="utf-8"
    )
    proc = run_validator(repo)
    assert proc.returncode == 1
    assert "workflows/does-not-exist.json" in proc.stdout
    assert "README.md" in proc.stdout


def test_bare_workflow_filename_reference_resolves(tmp_path):
    repo = build_stack(tmp_path)
    add_workflow(repo, "crm-contact-lookup")
    (repo / "README.md").write_text(
        "See `crm-contact-lookup.json` for the lookup flow.\n", encoding="utf-8"
    )
    proc = run_validator(repo)
    assert proc.returncode == 0, proc.stdout


def test_missing_bare_workflow_filename_reference_fails(tmp_path):
    repo = build_stack(tmp_path)
    (repo / "README.md").write_text("See `ghost.json` for the flow.\n", encoding="utf-8")
    proc = run_validator(repo)
    assert proc.returncode == 1
    assert "ghost.json" in proc.stdout


def test_non_workflow_json_reference_resolves_against_repo_root(tmp_path):
    repo = build_stack(tmp_path)
    (repo / "config").mkdir()
    (repo / "config" / "openclaw.json").write_text("{}", encoding="utf-8")
    (repo / "README.md").write_text("Edit `config/openclaw.json`.\n", encoding="utf-8")
    proc = run_validator(repo)
    assert proc.returncode == 0, proc.stdout


def test_invalid_workflow_json_is_flagged(tmp_path):
    repo = build_stack(tmp_path)
    wf_dir = repo / "workflows"
    wf_dir.mkdir()
    (wf_dir / "broken.json").write_text("{not valid json", encoding="utf-8")
    proc = run_validator(repo)
    assert proc.returncode == 1
    assert "workflows/broken.json" in proc.stdout
    assert "not valid JSON" in proc.stdout


def test_workflow_without_nodes_field_is_flagged(tmp_path):
    repo = build_stack(tmp_path)
    add_workflow(repo, "no-nodes", payload={"name": "no-nodes"})
    proc = run_validator(repo)
    assert proc.returncode == 1
    assert "missing the required field nodes" in proc.stdout


def test_workflow_without_name_field_is_flagged(tmp_path):
    repo = build_stack(tmp_path)
    add_workflow(repo, "no-name", payload={"nodes": []})
    proc = run_validator(repo)
    assert proc.returncode == 1
    assert "missing the required field name" in proc.stdout


def test_valid_workflow_directory_passes(tmp_path):
    repo = build_stack(tmp_path)
    add_workflow(repo, "service-health-check", payload={"name": "check", "nodes": [{"id": "1"}]})
    proc = run_validator(repo)
    assert proc.returncode == 0, proc.stdout


# ---------------------------------------------------------------------------
# End to end: usage errors and broken inputs
# ---------------------------------------------------------------------------


def test_repo_pointing_at_nonexistent_dir_exits_two(tmp_path):
    proc = run_validator(tmp_path / "nope")
    assert proc.returncode == 2
    assert "not a directory" in proc.stderr


def test_missing_repo_flag_exits_two(tmp_path):
    proc = subprocess.run(
        [sys.executable, "-I", "-B", str(VALIDATOR)],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 2


def test_unknown_flag_exits_two(tmp_path):
    proc = subprocess.run(
        [sys.executable, "-I", "-B", str(VALIDATOR), "--repo", str(tmp_path), "--bogus"],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 2


def test_repo_without_compose_file_exits_one(tmp_path):
    repo = tmp_path
    (repo / ".env.example").write_text(BASE_ENV, encoding="utf-8")
    proc = run_validator(repo)
    assert proc.returncode == 1
    assert "docker-compose.yml not found" in proc.stdout


def test_malformed_compose_file_exits_one(tmp_path):
    compose = "services:\n  web: [1, 2\n"
    repo = build_stack(tmp_path, compose=compose)
    proc = run_validator(repo)
    assert proc.returncode == 1
    assert "could not be parsed" in proc.stdout


def test_compose_without_services_exits_one(tmp_path):
    compose = "volumes:\n  data:\n"
    repo = build_stack(tmp_path, compose=compose)
    proc = run_validator(repo)
    assert proc.returncode == 1
    assert "does not define any services" in proc.stdout


def test_missing_workflows_directory_is_only_a_note(tmp_path):
    repo = build_stack(tmp_path)
    proc = run_validator(repo)
    assert proc.returncode == 0
    assert "workflow file checks skipped" in proc.stdout


# ---------------------------------------------------------------------------
# Unit tests: helpers and the built-in YAML reader
# ---------------------------------------------------------------------------


def test_parse_env_example_strips_quotes_and_comments():
    text = (
        "# header comment\n"
        "PLAIN=value\n"
        'QUOTED="hello world"\n'
        "SINGLE='single'\n"
        "\n"
        "export EXPORTED=yes\n"
    )
    values = vs.parse_env_example(text)
    assert values == {"PLAIN": "value", "QUOTED": "hello world", "SINGLE": "single", "EXPORTED": "yes"}


def test_parse_env_example_ignores_malformed_lines():
    text = "GOOD=1\nnot a assignment\n1BAD=2\n-no-dash=3\nGOOD2=4\n"
    values = vs.parse_env_example(text)
    assert values == {"GOOD": "1", "GOOD2": "4"}


def test_host_port_of_variants():
    assert vs.host_port_of("127.0.0.1:8080:80") == "8080"
    assert vs.host_port_of("8080:80") == "8080"
    assert vs.host_port_of("8080") == "8080"


def test_resolve_token_prefers_env_file_value():
    assert vs.resolve_token("${PORT:-1}", {"PORT": "2"}) == "2"
    assert vs.resolve_token("${PORT:-1}", {}) == "1"
    assert vs.resolve_token("${PORT}", {"PORT": "3"}) == "3"
    assert vs.resolve_token("${PORT}", {}) == "${PORT}"


def test_ref_has_default_variants():
    assert vs.ref_has_default(":-x")
    assert vs.ref_has_default("-x")
    assert vs.ref_has_default(":=x")
    assert not vs.ref_has_default("")
    assert not vs.ref_has_default(":?required")


def test_image_pin_problem_variants():
    assert vs.image_pin_problem("postgres:16-alpine") is None
    assert vs.image_pin_problem("ghcr.io/org/tool:v1") is None
    assert "latest" in vs.image_pin_problem("ghcr.io/org/tool:latest")
    assert "no version tag" in vs.image_pin_problem("postgres")


def test_fallback_parser_handles_compose_shapes():
    text = BASE_COMPOSE
    data = vs.parse_yaml_minimal(text)
    services = data["services"]
    assert set(services) == {"postgres", "n8n"}
    pg = services["postgres"]
    assert pg["image"] == "postgres:16-alpine"
    assert pg["environment"]["POSTGRES_USER"] == "${POSTGRES_USER:-n8n}"
    assert pg["ports"] == ["127.0.0.1:5433:5432"]
    assert pg["healthcheck"]["test"] == ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-n8n}"]
    n8n = services["n8n"]
    assert n8n["environment"] == [
        "N8N_HOST=${N8N_HOST:-localhost}",
        "N8N_ENCRYPTION_KEY=${N8N_ENCRYPTION_KEY}",
    ]


def test_fallback_parser_handles_toplevel_volumes_networks_and_depends_on():
    text = (
        "volumes:\n"
        "  data:\n"
        "networks:\n"
        "  stack:\n"
        "    driver: bridge\n"
        "services:\n"
        "  web:\n"
        "    image: web:1\n"
        "    depends_on:\n"
        "      db:\n"
        "        condition: service_healthy\n"
    )
    data = vs.parse_yaml_minimal(text)
    assert data["volumes"] == {"data": None}
    assert data["networks"] == {"stack": {"driver": "bridge"}}
    assert data["services"]["web"]["depends_on"] == {"db": {"condition": "service_healthy"}}


def test_fallback_parser_rejects_unterminated_flow_sequence():
    with pytest.raises(vs.YamlParseError):
        vs.parse_yaml_minimal("services:\n  web: [1, 2\n")


def test_fallback_parser_rejects_tab_indentation():
    with pytest.raises(vs.YamlParseError):
        vs.parse_yaml_minimal("services:\n\tweb:\n")


def test_fallback_parser_rejects_unexpected_indentation():
    with pytest.raises(vs.YamlParseError):
        vs.parse_yaml_minimal("services:\n  web:\n      image: a:1\n    oops: 1\n")


def _normalize_scalars(node):
    if isinstance(node, dict):
        return {k: _normalize_scalars(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_normalize_scalars(v) for v in node]
    if isinstance(node, (int, float)) and not isinstance(node, bool):
        return str(node)
    return node


def test_fallback_parser_agrees_with_pyyaml_when_installed():
    pytest.importorskip("yaml")
    import yaml

    text = BASE_COMPOSE + "    restart: unless-stopped\n"
    assert _normalize_scalars(vs.parse_yaml_minimal(text)) == _normalize_scalars(yaml.safe_load(text))


# ---------------------------------------------------------------------------
# Against the real repository (read only reference)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not (REAL_REPO / "docker-compose.yml").is_file(),
    reason="run from a repository checkout or set REPO",
)
def test_real_repository_validates_with_expected_warnings():
    proc = run_validator(REAL_REPO)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "result: 0 errors, 2 warnings" in proc.stdout
