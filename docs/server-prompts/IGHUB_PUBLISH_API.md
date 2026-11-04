# Change Request for IG-Hub: a publishing API for CoinePro HQ's production lines

> برای مالک: این متن را به Claude خودِ IG-Hub بده. هاب (CoinePro HQ) فقط همین نقطه‌ها را صدا می‌زند و هیچ توکن اینستاگرامی در هاب نیست.
> بعد از ساخته شدن، در اتصال «اینستاگرام» همان شرکت، `base_url` و `account` را بگذار و توکن را با `make growth-secret` (نوع instagram) بده.

**Change Request, repository `IG-Hub` only. Nothing in CoinePro-Hub changes.**

## Why
CoinePro HQ runs "production lines" (render a reel, make a cover, publish, then a story the same day).
Its `publish` step needs a small HTTPS API on IG-Hub to publish a reel, a story or a post, to set the
cover when the platform lets it, and to read the post's figures later. The hub never holds an
Instagram token; IG-Hub does.

## Transport and auth
- HTTPS only, behind IG-Hub's own domain. The hub calls it through its egress service, so IG-Hub's
  host must be reachable from the hub's public address (allow-list its address if you filter).
- `Authorization: Bearer <token>`: one static token per company, which the owner stores in the hub.
  Constant-time comparison; refuse with `401` otherwise. Never log the token.
- `Idempotency-Key: <client_ref>` on every POST. A repeat with the same key returns the first
  answer (same `id`) and publishes nothing twice.
- JSON in, JSON out. Persian text is UTF-8, kept as is.

## Endpoints (paths are configurable in the hub's connection; these are the defaults)

### `POST /v1/publish/reel`  and  `POST /v1/publish/post`
```json
{
  "kind": "reel",
  "account": "<IG-Hub's own account reference>",
  "client_ref": "LR-000123:publish",
  "media_url": "https://hq.coinepro.com/public/v1/media/<token>",
  "cover_url": "https://hq.coinepro.com/public/v1/media/<token>",
  "caption": "text with hashtags, at most 2200 characters",
  "publish_at": "2026-11-05T09:30:00+03:30"
}
```
- `media_url` and `cover_url` are one-file signed URLs that are **valid for 15 minutes**. IG-Hub must
  download both **when the call arrives** and keep its own copy; `publish_at` may be hours later.
- `cover_url` is optional. `publish_at` is optional (`null`: publish now).
- Label the content as AI-generated when the Instagram API offers the flag.
- Answer `202` (or `200`):
```json
{ "id": "ighub-9f2c", "state": "scheduled", "url": null, "cover_set": true }
```
  `state`: `scheduled | publishing | published`. `url` is the permalink once known (else `null`).
  **`cover_set`**: `true` if the cover was applied, **`false` if the platform could not take that
  cover** (the post is published anyway). The hub then sends the cover to the owner by hand.
- Errors: `400` with `{"error_fa": "<one plain Persian sentence>"}` for a bad request, `401`/`403`
  for the token, `429` when Instagram's publishing limit is reached (with `Retry-After`), `5xx`
  only for IG-Hub's own failure. `error_fa` is shown to the owner as written.

### `POST /v1/publish/story`
Same body without `caption` and `cover_url` (a story takes neither). The hub sends it the same day,
a few hours after the reel, with its own `publish_at`.

### `GET /v1/publish/{id}`
Returns the same object as the publish answer, with the current `state` (`failed` adds `error_fa`).
The hub reads it to learn when a scheduled post went out.

### `GET /v1/insights/{id}`
Returns the post's figures now, flat numbers only; the hub asks 24 hours and 7 days after publishing:
```json
{ "views": 1200, "reach": 900, "likes": 80, "comments": 6, "saves": 14, "shares": 9 }
```
Missing figures are left out, not zero.

## Rules
- No other endpoint is needed; no delete, no edit, no comment, no follow.
- Never accept a `media_url` outside `https://hq.coinepro.com/public/v1/media/` (the hub's own host).
- Rate-limit by token. Keep an audit line per publish (time, account, client_ref, outcome), never the token.
- Tests: a publish with and without a cover, a repeat with the same `Idempotency-Key`, a cover the
  platform refuses (`cover_set: false`), a story, the 401 and 429 answers, the insights read.

## What the owner does after
In the hub: Connections, Instagram, this company: `base_url` (IG-Hub's address), `account`, and
optionally `reel_path`, `story_path`, `post_path`, `insights_path` if the paths differ; the token with
`make growth-secret`.
