"""The substitute players' runner (prompt 12 §9.1, contract §21.13).

One process per job, in a one-shot container: the Job JSON (as the api's
`POST /internal/v1/substitutes/jobs/claim` gave it to the host dispatcher) on
stdin, JSON lines on stdout (`login_started` for a sign-in, then exactly one
`done`). The prompt goes to the CLI on the CLI's own stdin, never in argv; the
CLIs' own tools are off (Codex: its read-only sandbox in an empty directory;
Gemini: no core tool at all), except that a code review reads its read-only
checkout. Standard library only.
"""

__version__ = "0.1.0"
