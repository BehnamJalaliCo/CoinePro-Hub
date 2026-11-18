# @behnamjalali.tech — the hub's host jobs for the page (owner 2026-11-18)

- `breaking.py` — the always-awake breaking-news watcher (rules only, no model): every 4 minutes
  (`systemd/bjtech-breaking.timer`, as Hub) it reads the AI vendors' own feeds, API changelogs, model pages and
  Hugging Face orgs through the hub's egress, folds what it finds into one event per release, and starts the two
  event flows of the hub (`bjtech_flash`: the flash story out at once; `bjtech_breaking`: the full reel) through
  `domain/flow_events.start_event`. Never the same news twice (its state + the hub's one run per event). State:
  /home/Hub/sites/bjtech-breaking/state.json; `breaking.py --status`.
- `youtube_long.py` — the daily long video's uploader to @behnamjalali-tech (browser profile `youtube-bj`,
  `systemd/bjtech-longform.timer`, every 10 minutes): out/ checked, the soundtrack 0/0/0, THE CHANNEL GUARD (only when
  the profile's active channel is `youtube_channel_name` of bjtech-common/brand/config.json; empty = nothing ever
  uploads), one Public upload, then tags, Persian subtitles, thumbnail. `youtube_long.py --channel` (read only) shows
  the switcher's channels and the active one. It runs from a detached worktree /home/Hub/sites/bjtech-auto
  (`git -C /home/Hub/sites/bjtech-auto checkout --detach origin/server/p39-deploy` after a fetch to update it), so a fix to it
  never needs the live checkout moved.

Install (once, as root): `cp systemd/*.service systemd/*.timer /etc/systemd/system/ && systemctl daemon-reload &&
systemctl enable --now bjtech-breaking.timer` (and `bjtech-longform.timer` once the channel is reachable).
