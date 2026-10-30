# ⟨1.9⟩ prompt 18: the memory limits (MiB) while on-demand stt runs, from
# `hq.sh ... --profile stt --profile backup-tools config --format json`: every
# service but the start-up one-shots (a long-running service waits for them:
# they have finished before the worker can ask for stt), the backup's
# one-shot (stt holds the one-shot lock it waits on) and stt-fetch (make
# stt-on runs it before; the starter never does). hq.sh and the memory gate
# both read this file.
.services as $s
| ([$s[] | (.depends_on // {}) | to_entries[]
    | select(.value.condition == "service_completed_successfully") | .key] | unique) as $start
| [$s | to_entries[]
   | select(.key as $k | ($start | index($k)) == null and $k != "backup-tools" and $k != "stt-fetch")
   | .value.deploy.resources.limits.memory | tonumber]
| add / 1048576 | floor
