# Desktop packaging and CI review — 2026-10-01

> Historical October 1 audit evidence. Subsequent repairs and local app replacement are recorded in [October 2 delivery](../../verification/committed-app-redelivery-2026-10-02.md); [current STATUS](../../../STATUS.md) owns today’s source and delivery state. Findings, test counts and artifact hashes below describe the original audit point.

## Scope and method

Read-only review of `.github/workflows/ci.yml`, `.github/workflows/desktop.yml`,
`desktop/build.py`, packaging manifests and lockfiles, the frozen backend and
Electron entry points, desktop smoke/upgrade scripts, and the operating and build
assumptions in `README.md`, `STATUS.md`, and `desktop/README.md`. The review
checked runtime staging, platform/architecture selection, checksums, frozen
resource paths, app startup/shutdown, smoke isolation, CI target claims, and
upgrade-test boundaries against live source.

## Findings

No new confirmed defect was established in this pass. In particular, the
packaging guide explicitly limits the current delivery claim to Apple Silicon
macOS 14+, records that clean-machine/macOS 14 validation and signing/notarization
remain open, and says Windows build support does not constitute current release
verification. The workflows' broader build matrix is consistent with that
distinction.

No packaging build or installer was executed during this read-only pass. The
existing CI and documented local verification records were inspected as evidence;
they were not rerun. This report makes no claim that the current checkout has
passed a fresh cross-platform build.
