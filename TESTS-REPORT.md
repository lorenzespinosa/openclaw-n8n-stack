# Stack Validator Backfill Report

This delivery adds an offline validator for the compose stack, a pytest
suite for it, and a CI workflow that runs both. All files are new; nothing
in the referenced repository was modified.

## Files

| Path | Purpose |
| --- | --- |
| `scripts/validate_stack.py` | Offline stack validator, pure standard library |
| `test/test_validate_stack.py` | Pytest suite (49 tests) for the validator |
| `.github/workflows/ci.yml` | CI pipeline: validator self check plus tests |
| `REPORT.md` | This report |

## What the validator checks

The validator reads repository files only. It never contacts a container
registry, a Docker daemon, or the network.

1. Environment variable coverage. Every variable interpolated by the
   compose file (written as `${VAR}`, `${VAR:-default}`, or the other
   compose interpolation forms) must be defined in `.env.example`.
   Scanning covers environment blocks in both mapping and list syntax,
   plus any interpolation anywhere else in a service definition, including
   healthcheck commands and port bindings.
   - Referenced without a default and missing from `.env.example`: error.
   - Referenced only with defaults and missing: warning.
   - Defined in `.env.example` but never referenced: informational note.
     Variables also mentioned by scripts or the Makefile do not produce
     the note.
2. Image pins. Each service image must carry an explicit version tag.
   The floating tag `latest` and images with no tag at all produce
   warnings. Images pinned by digest pass. Images written with a variable
   reference are skipped because the tag cannot be checked offline.
3. Host port conflicts. Host side ports are extracted from short form
   port bindings, `${VAR}` and `${VAR:-default}` port values are resolved
   against `.env.example` before comparison, and any host port bound by
   more than one service, or twice by one service, produces a warning.
4. Workflow files.
   - Every path reference of the form workflows/<name>.json found in
     scanned repository text files (markdown, shell scripts, yaml, env
     example, Makefile) must exist on disk.
   - Backtick quoted file names ending in .json in markdown and shell
     scripts, such as the bundled workflow names in the README table,
     must resolve either at the repository root or inside the workflows
     directory.
   - Every JSON file in the workflows directory must parse and must
     contain a `name` string and a `nodes` list, matching the shape of an
     exported workflow such as `service-health-check.json`.

## How to run

Validate a checkout of the stack repository:

    python3 scripts/validate_stack.py --repo /path/to/openclaw-n8n-stack

From inside the repository itself:

    python3 scripts/validate_stack.py --repo .

Add `--strict` to treat warnings as issues and exit 1.

Run the test suite:

    python -m pip install pytest
    python -m pytest test/ -q

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Clean, or warnings only without `--strict` |
| 1 | Issues found (errors, or warnings under `--strict`) |
| 2 | Usage error, for example `--repo` pointing at a directory that does not exist, a missing `--repo` flag, or an unknown flag |

A missing `docker-compose.yml` or `.env.example` inside an existing
repository directory is reported as a validation error (exit 1), not a
usage error, because it is a broken stack rather than a bad invocation.

## Output format

Each finding prints on one line prefixed with `ERROR:`, `WARN:`, or
`NOTE:`. A summary line reports counts, and the last line is one of
`STACK OK`, `STACK OK (with warnings)`, or `STACK FAILED`.

Running the validator against the current repository reports two
warnings, both for the `latest` image tags, and otherwise passes.

## Known limitations

- YAML parsing. PyYAML is used when installed. Without it, a minimal
  indentation-aware reader handles the subset of YAML this repository
  uses: block mappings, block sequences, quoted scalars, single-line
  flow sequences (such as healthcheck test entries), and comments. It
  does not support anchors, tags, multi-line block scalars, flow
  mappings, tab indentation, block sequence items that are themselves
  mappings (common in GitHub Actions workflow files), YAML merge keys,
  or multi-document files. The fallback reader is only used for the
  compose file, which does not use those shapes.
  CI exercises this fallback path because only pytest is installed.
- Port syntax. Only short form bindings are understood. Long form
  (`published:`) entries are read when PyYAML is present and ignored
  otherwise. Port ranges are compared as text, so overlapping ranges are
  not detected. IPv6 bind addresses are not supported.
- The variable used for an image reference cannot be verified offline, so
  such images are skipped by the pin check.
- The reference scan only reads selected file types (markdown, shell,
  yaml, env example, Makefile) so references in other file types are
  invisible to it.
- The validator checks structure, not behavior: it cannot tell whether a
  pinned tag is current, whether secrets are strong, or whether the
  services work together at runtime.

## Test results

The suite was run before delivery:

    49 tests total. On a full checkout, including CI, all 49 run. From a
    bare overlay of only the new files, the reference-repository test skips
    (48 passed, 1 skipped).

49 tests were collected. The single skip is the parser agreement test,
which requires PyYAML; the run environment had only pytest installed, so
that test skips itself and the built-in reader path is what the other
tests exercise. Environment: Python 3.15.0 on macOS, pytest 9.2.0. CI
runs the same suite on Python 3.12 on ubuntu-latest, where the same skip
applies for the same reason.
