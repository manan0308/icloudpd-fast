# icloudpd-fast

A fast, parallel command-line downloader for your iCloud Photos library, with **adaptive concurrency** and a **live progress bar**.

- Downloads your whole library (or selected albums) to a local folder
- Parallel downloads that automatically tune themselves to the fastest rate Apple allows, backing off the moment iCloud pushes back (AIMD, like TCP congestion control)
- Live progress: how many photos checked, how many left, download rate, ETA, data transferred, and the current worker count
- Incremental re-runs: already-downloaded files are detected (by size and an MD5 database) and skipped
- Live Photos, EXIF date fixing, duplicate listing, auto-delete sync, email/script notifications on expired 2FA
- Works on Linux, Windows, and macOS

## Install

```sh
git clone https://github.com/manan0308/icloudpd-fast.git
cd icloudpd-fast
python -m venv .venv
.venv/bin/pip install -r requirements.txt        # Windows: .venv\Scripts\pip install -r requirements.txt
```

Requires Python 3.14+.

## Usage

```sh
cd src
../.venv/bin/python icloudpd.py -d /path/to/photos -u you@icloud.com
```

On first run you'll be prompted for your password and a 2FA code; the session is cached (default `~/.pyicloud`) so later runs are non-interactive.

While it runs you'll see one line that tells you everything:

```
downloading:  37%|████████▌              | 18502/50000 [12:41<21:35, 24.3photo/s, new 1204 · have 17290 · fail 8 · 3.9 GB · 14w]
```

- `18502/50000` — photos checked so far vs. total, with time elapsed / ETA
- `new` — files actually downloaded this run (`3.9 GB` transferred)
- `have` — files you already had on disk (skipped)
- `fail` — files that failed after all retries (details in `icloudpd.log`)
- `14w` — current parallel download limit chosen by the adaptive controller

And a plain-English summary at the end:

```
done: checked 50,000 files in 34m 16s — 1,204 downloaded (3.9 GB), 48,788 already on disk, 8 FAILED (see log)
adaptive: finished at 16 parallel downloads, peak this run was 18 (the ceiling Apple tolerated)
```

## How the adaptive concurrency works

Apple does not publish rate limits, and they vary by account, IP, and time of day. So instead of guessing a number, the downloader discovers it:

1. Starts at **8** parallel downloads.
2. After every **25 clean downloads**, allows **+1** more (up to `--download-workers`, default 32).
3. On any pushback — throttle error, session kick, timeout — **halves** the limit (never below 2) and climbs again.

The limit hovers just under whatever iCloud tolerates right now. The `peak` number printed at the end *is* the measured ceiling for that run. Prefer a fixed rate (e.g. for overnight cron jobs)? Use `--no-adaptive`.

## Key options

| Option | Default | What it does |
|---|---|---|
| `-d, --directory` | required | Where to put the photos |
| `-u, --username` | required | Your iCloud email |
| `-a, --album` | All Photos | Download one album |
| `--all-albums` | off | Download every album |
| `--album-workers N` | 4 | Albums processed in parallel |
| `--download-workers N` | 32 | Ceiling on total concurrent downloads |
| `--no-adaptive` | off | Fixed concurrency instead of adaptive |
| `--no-progress` | off | Plain log output, no progress bar (auto-off when piped) |
| `--recent N` | all | Only the N most recent photos |
| `--newest` | off | Only photos newer than the newest already downloaded |
| `--skip-videos` / `--skip-live-photos` | off | Skip those types |
| `--set-exif-datetime` | off | Write EXIF date from photo creation date |
| `--auto-delete` | off | Delete local files found in iCloud's Recently Deleted |
| `--folder-structure` | `{:%Y/%m/%d}` | Date folders; `album` or `none` also supported |

Run `icloudpd.py --help` for the complete list (sizes, SMTP notifications, duplicate listing, JSON catalog, and more).

A rotating debug log is written to `icloudpd.log` in the working directory; the progress bar keeps the console quiet and the log file keeps every detail.

## Credits & lineage

This project builds on two excellent open-source projects:

- [icloud-photos-downloader](https://github.com/icloud-photos-downloader/icloud_photos_downloader) — the original single-threaded tool
- [gordonaspin/icloudpd](https://github.com/gordonaspin/icloudpd) — a parallel rewrite of the original, which this repo forks

What this repo adds on top: the AIMD adaptive concurrency controller with a shared global download gate (upstream opened up to ~128 unbounded connections), the live progress UI and end-of-run summary, configurable worker counts, and packaging/logging fixes (installable requirements, log file no longer hardcoded to `/var/log`).

MIT licensed — see [LICENSE](LICENSE).
