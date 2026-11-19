# @behnamjalali.tech — the hub's host jobs for the page (owner 2026-11-18)

- `breaking.py` — the always-awake breaking-news watcher (rules only, no model): every 4 minutes
  (`systemd/bjtech-breaking.timer`, as Hub) it reads the AI vendors' own feeds, API changelogs, model pages and
  Hugging Face orgs through the hub's egress, folds what it finds into one event per release, and starts the
  event flows of the hub (`bjtech_flash`: the flash story out at once; `bjtech_tg_breaking`: the Telegram channel's
  breaking post, out at once (2026-11-19); `bjtech_breaking`: the full reel) through
  `domain/flow_events.start_event`. Never the same news twice (its state + the hub's one run per event). State:
  /home/Hub/sites/bjtech-breaking/state.json; `breaking.py --status`.
- `youtube_long.py` — the daily long video's uploader to @behnamjalali-tech (browser profile `youtube-bj`,
  `systemd/bjtech-longform.timer`, every 10 minutes): out/ checked, the soundtrack 0/0/0, THE CHANNEL GUARD (only when
  the profile's active channel is `youtube_channel_name` of bjtech-common/brand/config.json; empty = nothing ever
  uploads), one Public upload, then tags, Persian subtitles, thumbnail. `youtube_long.py --channel` (read only) shows
  the switcher's channels and the active one. It runs from a detached worktree /home/Hub/sites/bjtech-auto
  (`git -C /home/Hub/sites/bjtech-auto checkout --detach origin/server/p39-deploy` after a fetch to update it), so a fix to it
  never needs the live checkout moved.

- `youtube.py` — every reel of the page, once, as a Public YouTube Short on @behnamjalali-tech, its thumbnail the
  reel's own Instagram cover (the owner, 2026-11-19; `systemd/bjtech-shorts.timer`, every 15 minutes, as Hub). A
  sibling of DotCoin's youtube.py (site commit c3680b82) on the profile `youtube-bj`: it shares youtube_long.py's
  lock, egress client, spool and CHANNEL GUARD. Title = the caption's first line + " #Shorts"; description = the
  caption without its Instagram calls to action, then the Telegram channel and the Instagram page (links from
  bjtech-common/brand/config.json), 3-5 hashtags. Never twice: key `youtube:@behnamjalali-tech|instagram:<work ref>`,
  the video's sha256 (also against the long videos), its title in the channel's Shorts. An upload that failed
  after its file went in (YouTube keeps a draft) is state `check`, never retried by itself. State:
  /home/Hub/sites/bjtech-shorts.json. `youtube.py --dry-run` prints what it would upload; `test_youtube.py` (stdlib)
  checks its rules.

Install (once, as root): `cp systemd/*.service systemd/*.timer /etc/systemd/system/ && systemctl daemon-reload &&
systemctl enable --now bjtech-breaking.timer` (and `bjtech-longform.timer` and `bjtech-shorts.timer` once the
channel is reachable).
