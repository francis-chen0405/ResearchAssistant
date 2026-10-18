# Mac shutdown smoke PID race — October 18

The user reported another GitHub failure after Windows packaging became manual-only.
At `ea4773cb030200e5ab0bbf134d09e9a51f4a11ac`, the
[Mac job](https://github.com/francis-chen0405/ResearchAssistant/actions/runs/39153304644/job/117751238932)
failed in `desktop/shutdown-smoke.cjs:178` with `ps -o pgid= -p 0`.
The test observes file existence before Python’s `write_text` has finished writing;
reading an empty string makes `Number(...)` zero. That also made the old cleanup
parser unsafe because signalling negative zero targets the current process group.
Windows packaging was skipped correctly; the independent Windows native checks
passed. This is a test harness defect, not a newly demonstrated app shutdown defect.
Raw log: `/tmp/ra-github-mac-shutdown-ea4773c.log`.

## Repair and verification

- Publish manager PID and executed-process records by sibling temporary file plus
  atomic rename. Require a complete newline-terminated record before proceeding.
- Reject empty/partial/malformed, zero/one, negative and out-of-range PIDs before
  process lookup or cleanup. Keep original process ownership/sentinel assertions,
  production timeouts and all CI jobs unchanged.
- A deterministic file-descriptor regression forces the create/truncate and partial
  write windows, then verifies completed single/multiple PID records and unsafe inputs.
- All 22 desktop units pass. Two complete local native runs pass all nine scenarios
  each, including real manager handoff/ack boundaries, root exit, immediate stop,
  descendants and unrelated sentinels. Focused Python shutdown/boundaries: 19 pass,
  two existing Windows-only skips. Logs are `/tmp/ra-mac-pid-race-smoke-{1,2}.log`
  and `/tmp/ra-mac-pid-race-python.log`.

Only test harness sources and task guidance change; application source identity is
still `source-sha256:fe0cc617eaba0753c9895d0a5f4a983f07946c594c7054d9696775250dcf937c`.
The installed app, data, credentials and Windows manual-only boundary are preserved.
The preceding 3,196/nine-skip Python suite remains evidence for unchanged runtime
source; it is not claimed as rerun for this test-only fix. Push and inspect the exact
new CI revision before claiming remote acceptance. Leave the unrelated newly
untracked local root `.gitignore` untouched and out of the commit.
