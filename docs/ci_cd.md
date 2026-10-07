# CI/CD

Both pipelines run offline after installing dependencies. Neither needs secrets
(only the built-in `GITHUB_TOKEN`), GPUs, real agents, or paid models.

## CI: `.github/workflows/ci.yml`

CI runs:

- on every pull request;
- on every push to `main`;
- manually (`workflow_dispatch`);
- as a reusable workflow called by the release pipeline.

```text
lint ─┐
test ─┼─> smoke    (demo runs, artifacts uploaded even on failure)
      └─> package  (build sdist + wheel, smoke-test the wheel, upload dist)
```

| Job | What it checks |
| --- | --- |
| `lint` | `ruff check` (pinned in `requirements.lock.txt`; rule set F, E, W, B) and byte-compilation |
| `test` | `python -m unittest discover -s tests -v`. This covers the original nine tests, integrity, the stale-write regression suite, generated-stream properties, reporting, preservation of original fixture bytes and committed artifacts, and Scout round-trip and direct/scheduled agreement. |
| `smoke` | `fragmentguard demo` in both modes on the bundled fixtures, then on `examples/custom_inputs/`, all run from outside the checkout. A failed scheduled scan fails the job; there is no fallback to direct mode. Run directories are uploaded as `fragmentguard-runs`. |
| `package` | `python -m build` creates the sdist and wheel plus `SHA256SUMS`. The **built wheel** is installed into a fresh venv and run in both modes from an unrelated directory, so the packaged fixtures are exercised. `dist/` is uploaded. |

Dependencies come from `requirements.lock.txt`. The package itself is installed
with `--no-deps`, so the lock is the only source of versions.

## CD: `.github/workflows/release.yml`

Pushing a tag such as `v0.2.0`:

1. runs the whole CI pipeline (via `workflow_call`) against the tagged commit;
2. checks that the tag equals `v` + `project.version` in `pyproject.toml`;
3. downloads the `dist` artifact that CI built and tested, and verifies
   `SHA256SUMS`;
4. creates a GitHub Release for the tag with the wheel, the sdist, and
   `SHA256SUMS` attached.

The release job is the only job with `contents: write`. To cut a release:

```bash
# bump project.version in pyproject.toml (and fragmentguard.__version__), merge to main, then:
git tag v0.2.0 origin/main
git push origin v0.2.0
```

Nothing is published to PyPI. To add that later, configure
[PyPI trusted publishing](https://docs.pypi.org/trusted-publishers/) for this
repository, then add a job after `release` that uses
`pypa/gh-action-pypi-publish` with `id-token: write`. That is a decision for
the project owner. No credentials are stored here.

## Merge flow

Feature branches open a pull request into `main`. CI must be green before
merging. The required-checks rule itself is a branch-protection setting in the
GitHub repository settings, and it is not stored in this repository.

## Not covered

- Windows and macOS runners. The README documents PowerShell activation, but only
  Linux is exercised in CI.
- Python versions other than 3.12 (`requires-python` is `>=3.12,<3.13`).
- Two-process scheduled scans (`--max-processes 2`).
