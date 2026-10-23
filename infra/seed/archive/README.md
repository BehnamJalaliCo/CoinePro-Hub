# The archive's seed (prompt 14 §2, contract §23)

The first version of the archive's open layer: levels, clearance, classes and
their fields, the file plan, party kinds, link kinds, retention and reminder
rules, and the system sources. The api's seed (`hq_api.archive.seed`, run by
`api-migrate` on every `make up`) reads these files from `HQ_ARCHIVE_SEED`
(compose: `/app/seed/archive`, read-only).

Idempotent and conservative: a row is added only when its key (or `seed_key`)
is not there yet. Nothing the owner changed or retired in the app is ever
written again. The retention periods are defaults the owner reviews; they are
not legal advice.
