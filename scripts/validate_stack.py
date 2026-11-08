#!/usr/bin/env python3
"""Offline validator for the openclaw-n8n-stack Docker Compose repository.

The validator never contacts a container registry, a Docker daemon, or the
network. It reads repository files and reports findings:

  1. Every environment variable interpolated by docker-compose.yml
     (written as ${VAR} or ${VAR:-default}) must be defined in .env.example.
     A variable referenced without a default is an error. A variable that is
     only ever referenced with a default is a warning.
  2. Every service image must carry an explicit version tag. The floating
     tag "latest" and images with no tag at all produce warnings.
  3. Host port bindings must not collide. The same host port published by
     two services (or twice by one service) produces a warning. Port values
     written as ${VAR} or ${VAR:-default} are resolved from .env.example
     before comparison.
  4. Workflow JSON files referenced by repository documentation must exist
     on disk, and every file in workflows/ must be a readable n8n workflow
     export with a "name" string and a "nodes" list.

The compose file is parsed with PyYAML when it is installed. Without PyYAML
a minimal indentation-aware reader handles the subset of YAML that this
repository uses: block mappings, block sequences, double-quoted and
single-quoted scalars, single-line flow sequences such as healthcheck test
entries, and comments. Anchors, tags, multi-line block scalars, flow
mappings, tab indentation, block sequence items that are themselves
mappings (common in GitHub Actions workflow files), and long-form port
syntax are not supported by the fallback reader.

Usage:
    python3 scripts/validate_stack.py --repo /path/to/openclaw-n8n-stack

Exit codes:
    0  clean, or warnings only without --strict
    1  issues found
    2  usage error
"""

import argparse
import json
import re
import sys
from pathlib import Path

COMPOSE_NAME = "docker-compose.yml"
ENV_EXAMPLE_NAME = ".env.example"
WORKFLOW_DIR_NAME = "workflows"

# ${VAR}, ${VAR:-default}, ${VAR-default}, ${VAR:=alt}, ${VAR:?err}, ${VAR?err}
# a preceding $ means Compose escaping ($$ is a literal dollar), so skip it
ENV_REF_RE = re.compile(r"(?<!\$)\$\{([A-Za-z_][A-Za-z0-9_]*)([^}]*)\}")
# explicit repository path references such as workflows/foo.json
WORKFLOW_PATH_RE = re.compile(r"workflows/([A-Za-z0-9._\-/]+\.json)")
# markdown and shell references in backticks such as `foo.json`
TICKED_JSON_RE = re.compile(r"`([^`\n]+\.json)`")
ENV_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")

SCAN_SUFFIXES = {".md", ".sh", ".yml", ".yaml", ".example"}
SCAN_FILENAMES = {"Makefile", "makefile", ".env.example", "docker-compose.yml"}
SCAN_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".pytest_cache", ".venv", "venv", WORKFLOW_DIR_NAME}

ERROR = "ERROR"
WARN = "WARN"
NOTE = "NOTE"


class ComposeError(Exception):
    """Raised when docker-compose.yml cannot be read or parsed."""


# ---------------------------------------------------------------------------
# Minimal YAML reader (used when PyYAML is not installed)
# ---------------------------------------------------------------------------


class YamlParseError(Exception):
    """Raised when the built-in reader cannot parse the input."""


def _strip_comment(line):
    in_single = in_double = False
    for i, ch in enumerate(line):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "#" and not in_single and not in_double:
            if i == 0 or line[i - 1] in " \t":
                return line[:i]
    return line


def _prepare_lines(text):
    lines = []
    for lineno, raw in enumerate(text.splitlines(), 1):
        leading = raw[: len(raw) - len(raw.lstrip(" \t"))]
        if "\t" in leading:
            raise YamlParseError(f"line {lineno}: tab indentation is not supported")
        stripped = _strip_comment(raw)
        content = stripped.strip()
        if not content:
            continue
        lines.append((len(stripped) - len(stripped.lstrip(" ")), content, lineno))
    return lines


def _unquote(text):
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        body = text[1:-1]
        out = []
        i = 0
        escapes = {"n": "\n", "t": "\t", '"': '"', "\\": "\\"}
        while i < len(body):
            ch = body[i]
            if ch == "\\" and i + 1 < len(body):
                out.append(escapes.get(body[i + 1], "\\" + body[i + 1]))
                i += 2
            else:
                out.append(ch)
                i += 1
        return "".join(out)
    if len(text) >= 2 and text[0] == "'" and text[-1] == "'":
        return text[1:-1].replace("''", "'")
    return text


def _parse_flow_sequence(text):
    if not (text.startswith("[") and text.endswith("]")):
        raise YamlParseError(f"unterminated flow sequence: {text[:60]}")
    inner = text[1:-1].strip()
    if not inner:
        return []
    items = []
    buf = []
    in_single = in_double = escaped = False
    for ch in inner:
        if escaped:
            buf.append(ch)
            escaped = False
        elif in_double and ch == "\\":
            buf.append(ch)
            escaped = True
        elif ch == '"' and not in_single:
            in_double = not in_double
            buf.append(ch)
        elif ch == "'" and not in_double:
            in_single = not in_single
            buf.append(ch)
        elif ch == "," and not in_single and not in_double:
            items.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    tail = "".join(buf).strip()
    if tail:
        items.append(tail)
    return [_parse_scalar(item) for item in items]


def _parse_scalar(text):
    text = text.strip()
    if text.startswith("["):
        return _parse_flow_sequence(text)
    return _unquote(text)


def _split_key(content, lineno):
    in_single = in_double = False
    for j, ch in enumerate(content):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == ":" and not in_single and not in_double:
            if j + 1 == len(content) or content[j + 1] == " ":
                return _unquote(content[:j].strip()), content[j + 1 :]
    raise YamlParseError(f"line {lineno}: expected 'key: value', got: {content[:60]}")


def _parse_block(lines, i, indent):
    if lines[i][1].startswith("- ") or lines[i][1] == "-":
        return _parse_sequence(lines, i, indent)
    return _parse_mapping(lines, i, indent)


def _parse_mapping(lines, i, indent):
    result = {}
    while i < len(lines) and lines[i][0] == indent and not lines[i][1].startswith("- "):
        _, content, lineno = lines[i]
        key, rest = _split_key(content, lineno)
        rest = rest.strip()
        if rest:
            result[key] = _parse_scalar(rest)
            i += 1
        elif i + 1 < len(lines) and lines[i + 1][0] > indent:
            result[key], i = _parse_block(lines, i + 1, lines[i + 1][0])
        else:
            result[key] = None
            i += 1
    return result, i


def _parse_sequence(lines, i, indent):
    items = []
    while i < len(lines) and lines[i][0] == indent and (lines[i][1].startswith("- ") or lines[i][1] == "-"):
        content = lines[i][1]
        rest = content[2:].strip() if content.startswith("- ") else ""
        if rest:
            items.append(_parse_scalar(rest))
            i += 1
        elif i + 1 < len(lines) and lines[i + 1][0] > indent:
            value, i = _parse_block(lines, i + 1, lines[i + 1][0])
            items.append(value)
        else:
            items.append(None)
            i += 1
    return items, i


def parse_yaml_minimal(text):
    """Parse the YAML subset used by docker-compose.yml without PyYAML."""
    lines = _prepare_lines(text)
    if not lines:
        return {}
    value, i = _parse_block(lines, 0, lines[0][0])
    if i != len(lines):
        _, content, lineno = lines[i]
        raise YamlParseError(f"line {lineno}: unexpected indentation near: {content[:60]}")
    return value


# ---------------------------------------------------------------------------
# Loading and normalization
# ---------------------------------------------------------------------------


def load_compose_file(path):
    """Return (data, parser_name) or raise ComposeError."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ComposeError(f"cannot read {COMPOSE_NAME}: {exc}") from exc
    try:
        import yaml  # type: ignore
    except ImportError:
        try:
            return parse_yaml_minimal(text), "built-in YAML reader"
        except YamlParseError as exc:
            raise ComposeError(f"{COMPOSE_NAME} could not be parsed by the built-in reader: {exc}") from exc
    try:
        return yaml.safe_load(text), "PyYAML"
    except Exception as exc:  # PyYAML raises several exception types
        raise ComposeError(f"{COMPOSE_NAME} could not be parsed: {exc}") from exc


def parse_env_example(text):
    """Parse KEY=VALUE lines, skipping comments and blank lines."""
    values = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        name, _, value = line.partition("=")
        name = name.strip()
        if not ENV_NAME_RE.fullmatch(name):
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[name] = value
    return values


def iter_strings(node):
    if isinstance(node, dict):
        for value in node.values():
            yield from iter_strings(value)
    elif isinstance(node, list):
        for value in node:
            yield from iter_strings(value)
    elif isinstance(node, str):
        yield node


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


def ref_has_default(rest):
    return rest.startswith(":-") or rest.startswith("-") or rest.startswith(":=") or rest.startswith("=")


def collect_env_refs(services):
    """Map variable name to {'services': set, 'hard': bool, 'defaulted': bool}."""
    refs = {}
    for service_name, service in services.items():
        for text in iter_strings(service):
            for match in ENV_REF_RE.finditer(text):
                var, rest = match.group(1), match.group(2)
                info = refs.setdefault(var, {"services": set(), "hard": False, "defaulted": False})
                info["services"].add(service_name)
                if ref_has_default(rest):
                    info["defaulted"] = True
                else:
                    info["hard"] = True
    return refs


def check_env_vars(services, env_values, env_available, findings):
    refs = collect_env_refs(services)
    for var in sorted(refs):
        if env_available and var in env_values:
            continue
        info = refs[var]
        where = ", ".join(sorted(info["services"]))
        if info["hard"]:
            findings.append((ERROR, f"{var} is referenced by service(s) {where} but not defined in {ENV_EXAMPLE_NAME}"))
        else:
            findings.append((WARN, f"{var} is only referenced with defaults by {where} and not defined in {ENV_EXAMPLE_NAME}"))
    return refs


def image_pin_problem(image):
    """Return a description of the pin problem, or None when pinned."""
    image = image.strip()
    if "${" in image:
        return None  # cannot verify a variable image reference
    if "@sha256:" in image:
        return None  # digest-pinned
    name = image.rsplit("/", 1)[-1]
    if ":" in name:
        tag = name.split(":", 1)[1]
        if tag == "latest":
            return "uses the floating tag latest"
        return None
    return "has no version tag"


def check_images(services, findings):
    for name in sorted(services):
        image = services[name].get("image")
        if not isinstance(image, str) or not image:
            findings.append((WARN, f"service {name} has no image"))
            continue
        problem = image_pin_problem(image)
        if problem:
            findings.append((WARN, f"service {name} image {image} {problem}"))


def host_port_of(binding):
    """Extract the host-side port token from a short-form port binding.

    Splits on colons outside ${...} so values such as ${PORT:-9000} stay
    in one piece.
    """
    binding = binding.strip()
    parts = []
    buf = []
    in_var = False
    i = 0
    while i < len(binding):
        ch = binding[i]
        if not in_var and ch == "$" and i + 1 < len(binding) and binding[i + 1] == "{":
            in_var = True
            buf.append("${")
            i += 2
            continue
        if in_var:
            buf.append(ch)
            if ch == "}":
                in_var = False
            i += 1
            continue
        if ch == ":":
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
        i += 1
    parts.append("".join(buf))
    parts = [part.strip() for part in parts if part.strip()]
    if not parts:
        return ""
    if len(parts) >= 3:
        return parts[1]
    return parts[0]


def resolve_token(token, env_values):
    """Resolve ${VAR} or ${VAR:-default} against .env.example values."""
    token = token.strip()
    match = ENV_REF_RE.fullmatch(token)
    if not match:
        return token
    var, rest = match.group(1), match.group(2)
    if var in env_values and env_values[var] != "":
        return env_values[var]
    if rest.startswith(":-") or rest.startswith(":="):
        return rest[2:]
    if rest.startswith("-") or rest.startswith("="):
        return rest[1:]
    return token


def normalize_port(port):
    return str(int(port)) if port.isdigit() else port


def collect_port_bindings(services, env_values):
    bindings = []
    for name in sorted(services):
        ports = services[name].get("ports") or []
        if isinstance(ports, (str, dict)):
            ports = [ports]
        for entry in ports:
            if isinstance(entry, dict):
                # long-form syntax only arrives from PyYAML
                entry = str(entry.get("published") or "")
            raw = str(entry).strip()
            token = host_port_of(raw)
            if not token:
                continue
            resolved = resolve_token(token, env_values)
            bindings.append((normalize_port(resolved), name, raw))
    return bindings


def check_ports(services, env_values, findings):
    by_port = {}
    for port, service, raw in collect_port_bindings(services, env_values):
        by_port.setdefault(port, []).append((service, raw))
    for port in sorted(by_port):
        entries = by_port[port]
        if len(entries) < 2:
            continue
        where = ", ".join(f"{service} ({raw})" for service, raw in entries)
        findings.append((WARN, f"host port {port} is bound more than once: {where}"))


def iter_scan_files(repo):
    for path in sorted(repo.rglob("*")):
        if not path.is_file():
            continue
        parts = path.relative_to(repo).parts
        if parts and parts[0] in SCAN_SKIP_DIRS:
            continue
        if path.suffix.lower() in SCAN_SUFFIXES or path.name in SCAN_FILENAMES:
            yield path


def check_workflow_references(repo, findings):
    workflow_dir = repo / WORKFLOW_DIR_NAME
    referenced = {}
    for path in iter_scan_files(repo):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        source = path.relative_to(repo).as_posix()
        for match in WORKFLOW_PATH_RE.finditer(text):
            token = f"{WORKFLOW_DIR_NAME}/{match.group(1)}"
            referenced.setdefault(token, source)
        if path.suffix in {".md", ".sh"}:
            for match in TICKED_JSON_RE.finditer(text):
                referenced.setdefault(match.group(1), source)
    for token in sorted(referenced):
        source = referenced[token]
        candidates = [repo / token] if "/" in token else [repo / token, workflow_dir / token]
        if not any(candidate.is_file() for candidate in candidates):
            findings.append((ERROR, f"{source} references {token} but that file does not exist"))


def check_workflow_files(repo, findings):
    workflow_dir = repo / WORKFLOW_DIR_NAME
    if not workflow_dir.is_dir():
        findings.append((NOTE, f"no {WORKFLOW_DIR_NAME} directory found, workflow file checks skipped"))
        return
    for path in sorted(workflow_dir.glob("*.json")):
        rel = f"{WORKFLOW_DIR_NAME}/{path.name}"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            findings.append((ERROR, f"{rel} is not valid JSON ({exc})"))
            continue
        if not isinstance(data, dict):
            findings.append((ERROR, f"{rel} does not contain a workflow object"))
            continue
        if not isinstance(data.get("name"), str):
            findings.append((ERROR, f"{rel} is missing the required field name"))
        if not isinstance(data.get("nodes"), list):
            findings.append((ERROR, f"{rel} is missing the required field nodes"))


def check_unused_env_vars(env_values, refs, repo, findings):
    if not env_values:
        return
    supporting_text = []
    scripts_dir = repo / "scripts"
    if scripts_dir.is_dir():
        for path in sorted(scripts_dir.glob("*.sh")):
            try:
                supporting_text.append(path.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                pass
    makefile = repo / "Makefile"
    if makefile.is_file():
        try:
            supporting_text.append(makefile.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            pass
    combined = "\n".join(supporting_text)
    for var in sorted(env_values):
        if var in refs:
            continue
        pattern = r"(?<![A-Za-z0-9_])" + re.escape(var) + r"(?![A-Za-z0-9_])"
        if re.search(pattern, combined):
            continue
        findings.append((NOTE, f"{var} is defined in {ENV_EXAMPLE_NAME} but not referenced by {COMPOSE_NAME}"))


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def validate_repository(repo):
    findings = []
    compose_path = repo / COMPOSE_NAME
    if not compose_path.is_file():
        findings.append((ERROR, f"{COMPOSE_NAME} not found in {repo}"))
        return findings

    try:
        data, parser_name = load_compose_file(compose_path)
    except ComposeError as exc:
        findings.append((ERROR, str(exc)))
        return findings
    findings.append((NOTE, f"{COMPOSE_NAME} parsed with {parser_name}"))

    if not isinstance(data, dict) or not isinstance(data.get("services"), dict) or not data["services"]:
        findings.append((ERROR, f"{COMPOSE_NAME} does not define any services"))
        return findings
    services = data["services"]
    for name, service in services.items():
        if not isinstance(service, dict):
            findings.append((ERROR, f"service {name} must be a mapping, found {type(service).__name__}"))
    services = {n: s for n, s in services.items() if isinstance(s, dict)}

    env_path = repo / ENV_EXAMPLE_NAME
    env_available = env_path.is_file()
    env_values = {}
    if env_available:
        env_values = parse_env_example(env_path.read_text(encoding="utf-8"))
    else:
        findings.append((ERROR, f"{ENV_EXAMPLE_NAME} not found in {repo}"))

    refs = check_env_vars(services, env_values, env_available, findings)
    check_images(services, findings)
    check_ports(services, env_values, findings)
    check_workflow_references(repo, findings)
    check_workflow_files(repo, findings)
    if env_available:
        check_unused_env_vars(env_values, refs, repo, findings)
    return findings


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="validate_stack.py",
        description="Offline validator for the openclaw-n8n-stack Docker Compose repository.",
    )
    parser.add_argument("--repo", required=True, help="path to the repository root that contains docker-compose.yml")
    parser.add_argument("--strict", action="store_true", help="treat warnings as issues and exit 1")
    args = parser.parse_args(argv)

    repo = Path(args.repo).expanduser()
    if not repo.is_dir():
        print(f"usage error: --repo path is not a directory: {repo}", file=sys.stderr)
        return 2

    findings = validate_repository(repo)
    counts = {ERROR: 0, WARN: 0, NOTE: 0}
    for level, message in findings:
        print(f"{level}: {message}")
        counts[level] += 1

    print()
    print(f"result: {counts[ERROR]} errors, {counts[WARN]} warnings, {counts[NOTE]} notes")
    failed = counts[ERROR] > 0 or (args.strict and counts[WARN] > 0)
    if failed:
        print("STACK FAILED")
    elif counts[WARN] > 0:
        print("STACK OK (with warnings)")
    else:
        print("STACK OK")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
