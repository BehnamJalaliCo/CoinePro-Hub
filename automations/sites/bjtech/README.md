# @behnamjalali.tech — the hub's host jobs for the page (owner 2026-11-18)

- `breaking.py` — the always-awake breaking-news watcher (rules only, no model): every 4 minutes
  (`systemd/bjtech-breaking.timer`, as Hub) it reads the AI vendors' own feeds, API changelogs, model pages and
  Hugging Face orgs through the hub's egress, folds what it finds into one event per release, and starts the two
  event flows of the hub (`bjtech_flash`: the flash story out at once; `bjtech_breaking`: the full reel) through
  `domain/flow_events.start_event`. Never the same news twice (its state + the hub's one run per event). State:
  /home/Hub/sites/bjtech-breaking/state.json; `breaking.py --status`.
- `youtube_long.py` — the daily long video's uploader to @behnamjalali-tech (browser profile `youtube-bj`).

Install (once, as root): `cp systemd/*.service systemd/*.timer /etc/systemd/system/ && systemctl daemon-reload &&
systemctl enable --now bjtech-breaking.timer`.
