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

## Additional confirmed Python CI timeout

The same revision’s Python 3.12 job `117751237962` reached 84%, then GitHub annotated: “The job has exceeded the maximum execution
time of 15m0s”. Its Python 3.11 peer passed in 13m42s. Increase only the enclosing
full-test job allowance to 30 minutes, preserving every test command and assertion,
physical research budget, shutdown deadline and Windows installer limit.
The raw log is `/tmp/ra-github-python312-ea4773c.log`; the exact annotation is available
on [the job](https://github.com/francis-chen0405/ResearchAssistant/actions/runs/39153304572/job/117751237962).
The earlier Mac harness commit is `5c16bc1`; the final CI target also includes this
capacity correction. Verify both at the final revision rather than inheriting the
intermediate run’s results.

## PDF fixture failure exposed by the complete Python 3.12 run

At `473555949297316f197975eb118ba20588ac6750`, the Mac job passed completely,
as did Python 3.11. Python 3.12 completed with **three failures / 3,185 passed /
17 existing skips**, 1,221.88 seconds. All three failures were missing parser-phase
markers in `test_pdf_worker_deadline.py`: imports under coverage consumed the 1.5-second
request deadline before the intended Reader constructor/pages/extraction stalls.
The same failure markers were present in the earlier cancelled log and were missed
during the first timeout inspection. The timeout correction was necessary but was
not sufficient. Raw complete log: `/tmp/ra-github-python312-4735559.log`.

The fixture now preloads its parser double, waits for explicit readiness under a
bounded setup guard, and then times the real worker protocol/parser stall with the
same **1.5-second request / under-five-second assertion** and killed/reaped process
checks. Its test-only CPU-limit adapter accounts for CPU spent during that preload;
the worker retains its original post-preload CPU allowance and unchanged memory limit.
The application worker itself is unchanged. A separate real cold-child stall verifies
that startup still consumes the original overall request deadline.

All five PDF tests pass locally with coverage in 50.41 seconds. A focused coverage
step runs these cases before the full CI suite, providing quick failure reports;
the complete test command and its assertions remain intact. The new exact revision
still needs Linux/Windows CI confirmation. Unchanged runtime identity and installed
app/data preservation continue to apply.
