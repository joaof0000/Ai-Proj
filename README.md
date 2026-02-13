# Brave Focus Guard

This script watches for Brave browser startup and starts a timer.
If you do **not** visit one of your allowed websites before the timer expires, it can:

1. close Brave, or
2. shut down the whole computer.

## File

- `brave_focus_guard.py`

## Quick start

```bash
python3 brave_focus_guard.py \
  --allowed-domain youtube.com \
  --allowed-domain wikipedia.org \
  --timeout-minutes 10
```

If you want computer shutdown instead of just closing Brave:

```bash
python3 brave_focus_guard.py \
  --allowed-domain youtube.com \
  --allowed-domain wikipedia.org \
  --timeout-minutes 10 \
  --shutdown-computer
```

## How to test safely (yes, with prints)

Yes — prints are a good way to test. This script now supports a safe test mode:

```bash
python3 brave_focus_guard.py \
  --allowed-domain youtube.com \
  --timeout-minutes 0.25 \
  --check-interval-seconds 2 \
  --verbose \
  --dry-run
```

What this does:

- `--verbose`: prints loop-by-loop status (timer, allowed hit, history path)
- `--dry-run`: **does not** close Brave or shutdown your machine; only prints what it would do
- `--timeout-minutes 0.25`: short timeout (15 seconds) so you can test quickly

## Emergency stop (kill switch)

If anything feels wrong, stop it immediately:

- If running in terminal: press `Ctrl+C`.
- If running in background/systemd:

```bash
systemctl --user stop brave-focus-guard.service
systemctl --user disable brave-focus-guard.service
```

You can also run with a PID file:

```bash
python3 brave_focus_guard.py --pid-file ~/.local/state/brave-focus-guard.pid
kill "$(cat ~/.local/state/brave-focus-guard.pid)"
```

## Make it run from the start (Linux systemd user service)

Create `~/.config/systemd/user/brave-focus-guard.service`:

```ini
[Unit]
Description=Brave Focus Guard

[Service]
Type=simple
ExecStart=/usr/bin/python3 /FULL/PATH/TO/brave_focus_guard.py --allowed-domain youtube.com --allowed-domain wikipedia.org --timeout-minutes 10 --pid-file %h/.local/state/brave-focus-guard.pid
Restart=always
RestartSec=3

[Install]
WantedBy=default.target
```

Enable it:

```bash
systemctl --user daemon-reload
systemctl --user enable --now brave-focus-guard.service
```

## Notes

- The script checks Brave history database, so it works best when Brave can write history normally.
- If Brave is installed in a non-default profile/path, use `--history-path`.
