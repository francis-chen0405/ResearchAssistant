# Current-layout backend installability — Prompt 07

Verified locally on macOS 26.6.2 arm64 / Python 3.12.14. The existing checkout is now
an installable distribution before Prompt 08's Python/renderer folder migration.
No Python implementation directories moved. The only resource relocation is all
18 root prompt Markdown files to `researchassistant/prompts/`, byte for byte.
Their pre-move SHA-256 values are retained in
`tests/fixtures/packaging/prompt-hashes.json`. Historical prompt headers, policy
dispatch, schema identities, inspection/export and immutable releases are preserved.
Relative-path/source changes still invalidate incompatible resume; no fingerprint
or resume gate was relaxed.

## Supported install and contents

`pyproject.toml` uses `setuptools.build_meta` with `setuptools>=84,<85`, explicit
discovery of the four current package families (including existing namespace
packages), four compatibility modules, package data and the console entry point
`researchassistant = researchassistant.runtime.cli:main`. Runtime requirements are
unchanged; Streamlit remains a separate legacy dependency, while `httpx2` remains
a development dependency. `MANIFEST.in` includes the build hook in the source
distribution and excludes tests, archives, desktop/web products and runtime data.

The exact wheel contains **162 files**:

| Contents | Count |
| --- | ---: |
| `researchassistant/**/*.py` | 68 |
| `agents/*.py` | 23 |
| `providers/*.py` | 27 |
| Python `frontend/*.py` | 13 |
| Root `cli.py`, `models.py`, `orchestrator.py`, `store.py` | 4 |
| `researchassistant/prompts/*.md` | 18 |
| Unifont 15.0.01 TTF, `UNIFONT-LICENSE.txt`, font `README.md` | 3 |
| `researchassistant/_distribution/pyproject.toml` | 1 |
| Distribution `METADATA`, `WHEEL`, `entry_points.txt`, `top_level.txt`, `RECORD` | 5 |

The [complete file inventory](backend-installability-2026-10-10-wheel-files.txt)
lists every member. Verification compares each non-metadata path and byte to the
current source, and allows exactly the five metadata members. The wheel contains
no tests, fixture inputs, private keys, caches, user databases/data, archived plans,
build scripts, Electron/Node or Next.js output. A source-distribution rebuild also
produced the same exact wheel payload. The wheel SHA-256 recorded for this check is
`a32597ef9795df9b639beeb83a2d45e4c5c3ccb247547f75b2f456f5e5ae6137`;
build timestamps may change the archive hash on another build.

Install with `python -m pip install .` or, for development,
`python -m pip install -c desktop/constraints.txt -e ".[dev]"`.
Run **`researchassistant --help`** from any working directory.
`python -m researchassistant.runtime.cli`, `python -m cli`, and the checkout
`cli.py` script launcher remain supported. Installed `models`, `store` and
`orchestrator` alias the same canonical module objects; old agents/providers/frontend
imports remain available. Root prompt filesystem paths are replaced by package
resources; callers supplying their own prompt directory can still pass a `Path`.

## Identity and resource behavior

`researchassistant.common.resources` uses `importlib.resources` for executable
prompts and the PDF font. The existing exporter loads the font under `as_file`.
`scripts/build_distribution.py` copies exact build configuration bytes only into
the wheel build directory; editable installs read the live checkout configuration.
Installed configuration is hashed under logical `pyproject.toml`, in the same
ordering as the source configuration. Every executable source and canonical prompt
path/byte remains in identity; no old stored fingerprint is rewritten or accepted
through normalization. Frozen identity requires every one of the 18 prompts and
the font/configuration/engine/CLI surface, and additionally binds executable bytes.

For this source, editable, wheel and actual frozen source-data surfaces agree:
`source-sha256:3db588793ffa3fd023a39172b798eec5682202a53c433dbb2b056a4d46945e5b`.
The rebuilt executable adds its own bytes and yields
`source-sha256:2256b745738c65ff48c2960c1bc53ba672b97a34ac74834e41e83417b1e5b26d`.
Tampering with installed prompt/font/configuration bytes changes identity; removing
any individual frozen prompt fails completeness. Fresh binding replay and existing
incompatible-resume regressions passed; historical prompt/schema meaning is preserved.

## Fresh verification

- Two fresh virtual environments with no inherited system/user packages, outside
  the checkout at `/private/tmp/researchassistant-prompt07/verification3`, installed
  the wheel and editable tree using normal dependency resolution. The isolated
  build backend and installs used previously downloaded declared dependency wheels;
  `pip check` passed in both. Tests ran from distinct unrelated working directories
  using `python -I`, with custom import paths removed and no user provider credentials.
- Both installs verified all public facades, three CLI help launchers, credential-free
  API construction/OpenAPI, exact 18-prompt/font hashes and prompt headers, released
  and blocked fixture pipelines, a console fixture run, fresh v2 discovery binding
  and exact replay, and a three-page Unicode PDF with extracted text. Fixture inputs
  were copied outside the checkout and remain excluded from the distribution.
- **2,371 Python tests passed, 5 existing skips in 329.23 seconds**. Focused checks:
  **103 passed / 2 existing skips**, plus **33 resource/boundary/type checks passed**.
  Ruff lint and format passed across **311 Python files**; repository boundaries and
  staged/unstaged/new-file whitespace checks passed.
- **38 offline adversarial cases** and **six synthetic discovery scenarios** passed.
- A fresh `desktop/build.py --backend-only` build passed, with its cache redirected
  into temporary storage. Actual frozen source identity and all 18 prompt bytes
  matched the checkout; frozen executable binding differed as required. The native
  frozen smoke passed from an unrelated cwd with an empty developer-tool PATH:
  UI/backend, authentication, namespaced dummy-vault cleanup, durable temporary
  settings, owned acquisition lifecycle and restart identity.
- CI now installs the project via its supported editable `dev` extra and verifies
  isolated wheel/editable installs on Python 3.11/3.12. Desktop CI runs the constrained
  verifier before building. Local Python 3.11, native Windows and fresh installers/
  minimum-OS delivery were not tested here; workflow definitions are separate from
  executed evidence. No renderer implementation changed, so no new renderer build
  was required for this resource/packaging work.

## Git boundary and Prompt 08

Started on `master`, HEAD `94a241b`, one commit ahead of local `origin/master`, with
substantial staged and unstaged earlier work. No branch switch, staging, commit,
push, paid call, real research database mutation or app replacement occurred.
The pre-existing staged diff is byte-identical after this task. Graph freshness was
checked and refreshed against live source before discovery and after implementation.

Prompt 08 starts with supported current-layout installs, the canonical prompt
resources already relocated, the existing font path, build hook/manifests and
outside-checkout verifier. Move the backend distribution/runtime and Python
`frontend` services first, preserving installed public facades. Then rename `web/`
to root `frontend/`, and reconcile tooling/CI, desktop source/static paths, identity
roots, boundary allowlists and resource fixtures. Carry the exact build-configuration
resource into the new distribution and preserve logical configuration hashing.
Relative source moves must create a new identity and reject incompatible resume;
historical records must stay readable without rewriting hashes. Re-run the isolated
install and applicable frozen/native checks at each owning-folder transition.
The [Prompt 08 instructions](https://github.com/francis-chen0405/ResearchAssistant/blob/c59e54d3fcb86dd1b9f0a16242303af8fd32b608/docs/proposals/project-foundation-implementation-prompts/08-folder-consolidation.md)
now record this starting state. App replacement and public release remain separate.
