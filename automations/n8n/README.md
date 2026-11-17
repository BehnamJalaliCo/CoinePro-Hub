# n8n workflows

- `hq-flows.json`: the hub's one clock (contract §59.7, §61.2). It ticks each minute with a signed
  `POST /internal/v1/flows/tick`. The hub starts every `automations.flows` row whose build hour has
  come, and its own backup runs the same when no tick came for 10 minutes.
- `flow-*.json`: the per-flow workflows from before §61 (one per daily flow, each at its own old
  hour). Since prompt 39.1 their call is a no-op whenever the row says so (before the row's build
  hour, off, paused, or a skipped day: `202 {started: false}`), and when the hub's clock has
  already started that day. **Retirement:** once the hub's clock has run a full week without a
  miss, they are switched off in n8n (never deleted); their files stay here.
- `line-callback-demo.json`: the demo of a line's signed callback (§30.4).
