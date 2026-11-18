# Official AI vendor sources (researched and fetched 2026-11-18) — the reels' news step and the breaking watcher

Checked from the hub on 2026-11-18 with curl (browser User-Agent, `-L --compressed`). Every URL below was fetched today unless it says otherwise. "verified 2026-11-18" on a feed means: HTTP 200 and the body starts as RSS (`<rss`) or Atom (`<feed`) XML. "Latest item seen" is what the feed or page showed at check time, only to orient the first run.

## General watcher notes

- Poll politely: feeds every 5 to 10 minutes, HTML pages and sitemaps every 15 to 30 minutes, the Hugging Face API every 5 to 10 minutes, GitHub `releases.atom` every 10 to 15 minutes. Add random jitter and back off (double the interval) on 403, 429 or 5xx.
- Send a full desktop browser User-Agent plus `Accept-Language: en-US`. With a bare `Mozilla/5.0` UA, microsoft.ai answers a Cloudflare "Attention Required" HTML page instead of its feed. ai.meta.com answers HTTP 400 unless the request also carries `Accept`, `Sec-Fetch-*` and `Upgrade-Insecure-Requests` headers.
- Always ask for compressed responses (`Accept-Encoding: gzip`, curl `--compressed`). deepmind.google returns gzip even when you do not ask for it.
- Use conditional GETs. These sent an ETag and/or Last-Modified today: deepmind.google feed (ETag), mistral.ai feed (ETag), about.fb.com feed (both), blogs.nvidia.com feed (both), machinelearning.apple.com feed (both), huggingface.co blog feed (ETag), docs.z.ai feed (Last-Modified), GitHub releases.atom (ETag), Hugging Face models API (ETag). openai.com, platform.claude.com and blog.google sent neither, so dedupe those by item GUID or link.
- Do not trust Content-Type. mistral.ai serves its RSS as `text/plain`. api-docs.deepseek.com answers HTTP 200 with its docs homepage for any unknown path, so `/rss.xml` there "works" but is HTML. Check the body for `<rss` or `<feed`.
- Signal strength for "a new model just shipped" (strongest first):
  1. A new model id in an official API changelog or models page: OpenAI changelog, Claude release-notes feed, Gemini API changelog, xAI `release-notes.md`, Mistral changelog, DeepSeek change log, Alibaba Model Studio "Model releases and updates".
  2. An official news feed item whose title matches `Introducing|launch|now available|release|model name + version`.
  3. A new repo on the vendor's Hugging Face org (open weights). The HF API is fast, keyless and has an ETag.
  4. A new GitHub repo in the vendor org, or a new release of its SDK. SDKs often add a model id hours before the blog post.
  5. Sitemap `lastmod` changes (anthropic.com, microsoft.ai, openai.com) as a fallback where the news page blocks bots.
- Authenticated model lists (`GET /v1/models`) are another strong signal if keys exist. Without a key today, these answered 401: api.openai.com/v1/models, api.anthropic.com/v1/models, api.x.ai/v1/models, api.mistral.ai/v1/models, api.deepseek.com/models, api.moonshot.ai/v1/models and api.minimax.io/v1/models. generativelanguage.googleapis.com/v1beta/models answered 403 without a key.
- Unofficial cross-check (not a vendor source): https://openrouter.ai/api/v1/models is public JSON with a `created` timestamp per model. It listed 478 models today; the newest were `openai/gpt-6.2-astra`, `-astra-pro`, `-sol` and `-sol-pro` (created 2026-11-17).
- Hugging Face API `author=` is case-sensitive. `Qwen` returns models and `qwen` returns `[]`; the same goes for `mistralai` against `MistralAI`. Use the exact org names below.
- GitHub org-level `https://github.com/<org>.atom` answers but is empty for organisations, so it is useless. For model repos that never publish releases, use `https://github.com/<org>/<repo>/commits/main.atom` (works: verified on QwenLM/Qwen3.8 and meta-models/muse-code-sdk). To catch new repos, use `https://api.github.com/orgs/<org>/repos?sort=created&direction=desc&per_page=5`. That API is keyless but limited to 60 requests per hour per IP, so poll it at most every 30 minutes per org, or use a token.
- Launch image: prefer `og:image`, then `twitter:image`, then the first large `<img>` in the article body. Several vendors fall back to a generic site image on some posts (Anthropic, Mistral, DeepSeek, Apple ML, qwen.ai), so keep a per-vendor blocklist of known generic images (listed in each section). Some image URLs are signed and expire (Meta's fbcdn `oe=` parameter), so download the image as soon as you see it.

---

## OpenAI

- News: https://openai.com/news/ (blocks curl and WebFetch with HTTP 403 from Cloudflare; article pages such as https://openai.com/index/introducing-gpt-6-2-astra-sol also answer 403 to non-browsers).
- RSS: https://openai.com/news/rss.xml (verified 2026-11-18; https://openai.com/blog/rss.xml redirects to it). Latest item seen: "Le Groupe Figaro and OpenAI partner..." (2026-11-18). Before that: "Introducing GPT-6.2 Astra and Sol" (Tue, 17 Nov 2026 17:45 GMT, https://openai.com/index/introducing-gpt-6-2-astra-sol). Items carry title, description, link, category (Product, Company, ...) and pubDate, but no image.
- Secondary feed: https://developers.openai.com/rss.xml (verified 2026-11-18; the changelog page links to it as its alternate feed). It is a guides and cookbook feed and is not in date order. Its newest item is from 2026-05-05, so it is not a launch signal.
- Changelog, models and pricing:
  - https://developers.openai.com/api/docs/changelog (200; https://platform.openai.com/docs/changelog redirects here). Server-rendered, with a dated "Nov 17 ... gpt-6.2-astra / gpt-6.2-sol" entry. Diff this page.
  - https://developers.openai.com/api/docs/models (200; redirected from platform.openai.com/docs/models)
  - https://developers.openai.com/api/docs/pricing (200)
  - https://openai.com/api/pricing/ and the ChatGPT release notes at https://help.openai.com/en/articles/6825453-chatgpt-release-notes both answer 403 to bots.
  - Sitemap index: https://openai.com/sitemap.xml (200, XML, with per-section child sitemaps).
- Hugging Face org: `openai`. https://huggingface.co/api/models?author=openai&sort=createdAt&direction=-1&limit=5 (verified, JSON list). Newest: `openai/privacy-filter` (2026-04-17).
- GitHub org: `openai`
  - https://github.com/openai/codex/releases.atom (verified Atom; newest 0.171.0-alpha.13, 2026-11-18)
  - https://github.com/openai/openai-python/releases.atom (verified; v3.55.0, 2026-11-18)
  - https://github.com/openai/openai-agents-python/releases.atom (verified; v0.25.0, 2026-11-18)
  - https://github.com/openai/gpt-oss/releases.atom (verified; v0.0.9, 2026-01-13)
- Launch image: the RSS has no image, and article pages answer 403 to curl, WebFetch and link-preview bot user-agents. The og:image could not be verified from this server. Load the article in a real headless browser (the hub's browser-web) and read `meta[property="og:image"]`. As a fallback, the developers site has its own og images, for example `https://developers.openai.com/og/api/docs/changelog.png`.

## Anthropic

- News: https://www.anthropic.com/news (200). Also https://www.anthropic.com/engineering (200) and the product articles at https://claude.com/resources/articles (https://claude.com/blog redirects there).
- RSS: no official feed for anthropic.com/news (`/rss.xml`, `/news/rss.xml`, `/feed.xml`, `/atom.xml` and `/news/feed` all 404, and the page has no alternate link). There are two official feeds elsewhere:
  - https://platform.claude.com/docs/en/release-notes/feed.xml (verified 2026-11-18; declared as the alternate feed on the release-notes page). Latest items seen: November 17, 2026 (linked billing), November 16, November 12, and November 9, 2026 with anchor `#claude-fable-5-2`. This is the strongest Anthropic model signal.
  - https://claude.com/resources/articles/rss.xml (verified 2026-11-18; https://claude.com/blog/rss.xml redirects here). Latest item seen: "Linked billing on the Claude Platform" (2026-11-17).
  - Fallback: https://www.anthropic.com/sitemap.xml (200, XML, `lastmod` per URL, 281 news URLs). The newest news lastmod seen was 2026-11-17, `/news/advancing-claude-for-financial-services`.
- Changelog, models and pricing:
  - https://platform.claude.com/docs/en/release-notes/overview (200; https://docs.claude.com/en/release-notes/overview redirects here)
  - https://platform.claude.com/docs/en/models/overview (200; redirected from docs.claude.com/en/docs/about-claude/models/overview)
  - https://platform.claude.com/docs/en/about-claude/pricing (200)
  - https://claude.com/pricing (200; https://www.anthropic.com/pricing redirects here)
  - App release notes: https://support.claude.com/en/articles/12138966-release-notes (200)
  - Status RSS: https://status.claude.com/history.rss (verified RSS; incidents only)
- Hugging Face org: `Anthropic` (https://huggingface.co/anthropic redirects to /Anthropic). The models API returns `[]` (no model weights). It publishes datasets instead: https://huggingface.co/api/datasets?author=Anthropic&sort=createdAt&direction=-1&limit=5 (verified; newest `Anthropic/scorpion-toxin-binder-design`, 2026-10-18). Not a model-launch signal.
- GitHub org: `anthropics`
  - https://github.com/anthropics/claude-code/releases.atom (verified Atom; v2.1.327, 2026-11-17)
  - https://github.com/anthropics/anthropic-sdk-python/releases.atom (verified; v2.10.0, 2026-11-17)
  - https://github.com/anthropics/claude-agent-sdk-python/releases.atom (verified; v0.2.184, 2026-11-18)
  - https://github.com/anthropics/skills/releases.atom (answers, but has 0 entries: no releases)
- Launch image: verified. https://www.anthropic.com/news/claude-opus-5-5 has `og:image` = `https://assets.claude.com/f4d37a1d1f582f53f4e89440062b649b6273a093.jpg` (twitter:image is the same). Older or other posts fall back to the generic logo `https://assets.claude.com/6d4a0d28992ade92d6fa63646fd9c9d318245c6c.jpg` (seen on /news and on /news/claude-opus-4-5), so blocklist that hash. Release-notes pages have a generated og image (`https://platform.claude.com/web-api/og/docs/...`).

## Google (Google AI blog, Google DeepMind, Gemini, Google for Developers)

- News: https://blog.google/technology/ai/ (redirects into /innovation-and-ai/...), https://deepmind.google/blog/ (200) and https://developers.googleblog.com/ (200).
- RSS (all verified 2026-11-18):
  - https://deepmind.google/blog/rss.xml. Latest seen: "Introducing Gemini 4 Hydrogen" (Thu, 12 Nov 2026 18:00 UTC) and "Gemini 4 Carbon is now available" (Tue, 10 Nov 2026). Many items carry `media:content` images, but the Hydrogen item did not.
  - https://blog.google/products/gemini/rss/ (redirects to https://blog.google/products-and-platforms/products/gemini/rss/). Latest seen: "See what 5 builders are making with Gemini 4 Carbon" (2026-11-17).
  - https://blog.google/technology/ai/rss/ (redirects to https://blog.google/innovation-and-ai/technology/ai/rss/). Latest seen 2026-11-17.
  - https://developers.googleblog.com/rss/ (same as /feeds/posts/default). Latest seen: "Accelerating development for massive Git repositories" (2026-11-18). Items have no pubDate in the first entries, so dedupe by link.
  - https://research.google/blog/rss/ (latest seen 2026-11-13)
  - https://docs.cloud.google.com/feeds/generative-ai-on-vertex-ai-release-notes.xml is official Atom but stale: its newest entry is May 26, 2026. Low value.
- Changelog, models and pricing:
  - https://ai.google.dev/gemini-api/docs/changelog redirects to https://aistudio.google.com/docs/changelog (200). Server-rendered, with a newest heading of "November 18, 2026". Diff this page. There is no feed link.
  - https://ai.google.dev/gemini-api/docs/models redirects to https://aistudio.google.com/docs/models (200)
  - https://ai.google.dev/gemini-api/docs/pricing redirects to https://aistudio.google.com/docs/pricing (200)
  - https://deepmind.google/models/gemini/ (200, model family page)
  - Gemini app release notes: https://gemini.google/release-notes/ (200; geo-redirects, so use `?hl=en`, which lands on https://gemini.google/us/release-notes/?hl=en)
- Hugging Face org: `google`. https://huggingface.co/api/models?author=google&sort=createdAt&direction=-1&limit=5 (verified). Newest: `google/embeddinggemma-2` (2026-09-14).
- GitHub orgs: `google-gemini`, `google-deepmind`, `googleapis`, `google`
  - https://github.com/google-gemini/gemini-cli/releases.atom (verified; v0.69.0-preview.0, 2026-11-10)
  - https://github.com/googleapis/python-genai/releases.atom (verified; v3.6.0, 2026-11-18)
  - https://github.com/google-deepmind/gemma/releases.atom (verified; v4.0.1, 2026-05-20)
  - https://github.com/google/adk-python/releases.atom (verified; v2.14.1, 2026-11-12)
- Launch image: verified. DeepMind model posts redirect to blog.google. For example, https://deepmind.google/blog/introducing-gemini-4-hydrogen/ ends at https://blog.google/innovation-and-ai/models-and-research/gemini-models/introducing-gemini-4-hydrogen/ with `og:image` = `https://storage.googleapis.com/gweb-uniblog-publish-prod/images/gemini-4-hydrogen__key-art__lockup__16-9.width-1300.jpg`. blog.google posts always carry a per-post og:image on storage.googleapis.com.

## Meta AI

- News: https://ai.meta.com/blog/ (200 only with full browser headers; HTTP 400 otherwise). Company newsroom: https://about.fb.com/news/ (200).
- RSS: there is no official feed for ai.meta.com (`/blog/rss/`, `/blog/feed/` and the publications RSS all answer 400 or error, and the page has no alternate link). Official feeds elsewhere:
  - https://about.fb.com/news/feed/ (verified 2026-11-18; all of Meta, so filter for AI). Latest AI item seen: "Muse Is Now Available in Australia: The World's First Personal AI Agent Built for Everyone" (2026-11-17).
  - https://engineering.fb.com/feed/ (verified 2026-11-18; engineering blog, latest seen 2026-11-13)
- Models, pricing and changelog: Meta's developer site is now https://dev.meta.ai/ (https://www.llama.com/ redirects there). The model family is "Muse": the site links /models/muse-spark, muse-spark-1-1, muse-spark-1-2, muse-spark-open, muse-ember, muse-glimmer, muse-wonder and muse-image.
  - https://dev.meta.ai/docs/models (200)
  - https://dev.meta.ai/docs/pricing-rate-limits (200)
  - https://dev.meta.ai/models/muse-spark-1-2 (200, example model page)
  - https://dev.meta.ai/docs/muse-code/changelog (200; the changelog of the Muse Code coding tool only). There is no general API changelog: `/docs/changelog` and `/changelog` are 404.
  - Legacy Llama model cards: https://dev.meta.ai/llama/docs/model-cards-and-prompt-formats (200)
- Hugging Face orgs:
  - `meta-models` (new): https://huggingface.co/api/models?author=meta-models&sort=createdAt&direction=-1&limit=5 (verified). Newest: `meta-models/Muse-Spark-Open-816B-A42B` (2026-09-15).
  - `facebook` (research): verified. Newest: `facebook/meta-encoder-v1` (2026-11-12).
  - `meta-llama` (legacy): verified, but its newest model is from 2025-04-28 (Llama-Prompt-Guard-2). It is effectively frozen.
- GitHub orgs: `meta-models` (new, linked from dev.meta.ai), `facebookresearch`, `meta-llama`
  - https://github.com/meta-models/muse-code-sdk/releases.atom (answers, 0 entries). Use https://github.com/meta-models/muse-code-sdk/commits/main.atom instead (verified Atom; last commit 2026-11-17).
  - https://github.com/facebookresearch/faiss/releases.atom (verified; v1.16.0, 2026-11-10)
  - https://github.com/facebookresearch/sam3/releases.atom (answers, 0 entries)
  - https://github.com/meta-llama/llama-models/releases.atom (verified, but stale: v0.2.0, 2025-04-05). Note: github.com/meta-llama/llama-stack now redirects to github.com/ogx-ai/ogx, so it is no longer a Meta signal.
- Launch image: verified. https://ai.meta.com/blog/introducing-muse-spark-meta-model-api/ has a per-post `og:image` on `scontent-*.xx.fbcdn.net`. The URL is signed with an `oe=` expiry, so download it immediately. about.fb.com posts also carry og:image.

## xAI (now publishing as "SpaceXAI" / "SpaceXSI" on its pages and docs)

- News: https://x.ai/news answers 403 (Cloudflare) to curl and WebFetch. Single article pages do answer: https://x.ai/news/grok-4-7 (200, og:title "Introducing Grok 4.7"). The sitemap (https://x.ai/sitemap.xml) and https://status.x.ai/ also answer 403.
- RSS: no official feed (`/news/rss.xml` and `/news/feed.xml` are 404; `/rss.xml` and `/feed` are 403).
- Changelog, models and pricing. The docs are keyless and have plain-markdown twins, which are ideal for diffing:
  - https://docs.x.ai/developers/release-notes (200; https://docs.x.ai/docs/release-notes redirects here). Markdown: https://docs.x.ai/developers/release-notes.md (200). Newest seen: November, "grok-imagine-image-quality retired"; October, "Grok Voice 3.0 is available".
  - https://docs.x.ai/developers/models (200; titled "Grok Models & Pricing"; mentions grok-4.7). Markdown: https://docs.x.ai/developers/models.md (200, text/markdown)
  - https://docs.x.ai/developers/pricing.md (200, text/markdown; listed in https://docs.x.ai/llms.txt, which is 200)
- Hugging Face org: `xai-org`. https://huggingface.co/api/models?author=xai-org&sort=createdAt&direction=-1&limit=5 (verified). Only `xai-org/grok-2` (2025-08-22) and `xai-org/grok-1` (2024-03-17), so this is a weak signal.
- GitHub org: `xai-org`
  - https://github.com/xai-org/xai-sdk-python/releases.atom (verified; v1.21.0, 2026-10-23)
  - https://github.com/xai-org/grok-build/releases.atom (answers, 0 entries)
  - https://github.com/xai-org/grok-1/releases.atom (answers, 0 entries)
- Launch image: verified. https://x.ai/news/grok-4-7 has `og:image` = `https://x.ai/images/news/grok-4-7-og.webp`. Article pages are fetchable even though /news is blocked, so build the URL from the release notes or the model id and fetch the article directly.

## Mistral AI

- News: https://mistral.ai/news (redirects to /news/, 200)
- RSS: https://mistral.ai/news/rss (verified 2026-11-18; declared as the alternate feed on every page; https://mistral.ai/rss.xml redirects here). It is served as `text/plain`, so parse the body anyway. Latest seen: "Le Chonk brings the brains. Studio puts it to work." (2026-11-05), "Le Chonk: Built for Coders, Trusted by Defenders." (Mistral Large 4 open weights, 2026-10-29), "Voxtral 3" (2026-10-20).
- Changelog, models and pricing:
  - https://docs.mistral.ai/resources/changelogs (200; https://docs.mistral.ai/getting-started/changelog/ redirects here). No feed.
  - https://docs.mistral.ai/models (200; redirected from /getting-started/models/)
  - https://mistral.ai/pricing (200)
- Hugging Face org: `mistralai` (case-sensitive). https://huggingface.co/api/models?author=mistralai&sort=createdAt&direction=-1&limit=5 (verified). Newest: `mistralai/Mistral-Large-4-1T-A52B-NVFP4` (2026-10-15).
- GitHub org: `mistralai`
  - https://github.com/mistralai/mistral-vibe/releases.atom (verified; v3.1.3, 2026-11-18)
  - https://github.com/mistralai/client-python/releases.atom (verified; v3.7.0, 2026-11-01)
  - https://github.com/mistralai/mistral-common/releases.atom (verified; v1.13.1, 2026-11-02)
  - https://github.com/mistralai/mistral-inference/releases.atom (verified, but stale: v1.6.0, 2025-03-20)
- Launch image: verified, with a caveat. Some posts have their own og:image (Voxtral 3: `https://mistral.ai/cms-media/api/media/file/hero-blog-voxtral.png`). Others, including the Mistral Large 4 post, fall back to the generic site cover `https://mistral.ai/cms-media/api/media/file/cover-mistral-sovereign%20copie.webp`, so blocklist it. In that case use the first hero `<img>` under `/images/heros/<slug>/`.

## DeepSeek

- News: the announcements live in the API docs as https://api-docs.deepseek.com/news/newsYYMMDD. Newest seen: https://api-docs.deepseek.com/news/news261113 ("The full DeepSeek App experience, now via API"). Before it: news261017, news260910, news260821, news260813 and news260424. Homepage: https://www.deepseek.com/en/ (200).
- RSS: no official feed. Careful: `/rss.xml`, `/atom.xml` and `/news/rss.xml` return HTTP 200, but the body is the docs homepage HTML (an SPA fallback). Watch for new `/news/newsYYMMDD` links in the sidebar of any docs page instead.
- Changelog, models and pricing:
  - https://api-docs.deepseek.com/updates/ (200, page title "Change Log")
  - https://api-docs.deepseek.com/quick_start/pricing/ (200, page title "Models & Pricing")
- Hugging Face org: `deepseek-ai`. https://huggingface.co/api/models?author=deepseek-ai&sort=createdAt&direction=-1&limit=5 (verified). Newest: `deepseek-ai/DeepSeek-V4.1-Flash-1017` (2026-10-17).
- GitHub org: `deepseek-ai`
  - https://github.com/deepseek-ai/deepseek-harness/releases.atom (verified; v0.2.2-rc.4, 2026-11-17; the org's most-starred repo now)
  - https://github.com/deepseek-ai/DeepSeek-V3/releases.atom (verified; one release only, v1.0.0, 2025-06-27)
  - https://github.com/deepseek-ai/FlashMLA/releases.atom (answers, 0 entries)
  - https://github.com/deepseek-ai/DeepInfer/releases.atom (answers, 0 entries)
  - New-repo check (keyless JSON, verified): https://api.github.com/orgs/deepseek-ai/repos?sort=created&direction=desc&per_page=5
- Launch image: the og:image is generic (`https://api-docs.deepseek.com/img/deepseek-social-card.jpeg`; the homepage uses `https://www.deepseek.com/images/deepseek-social.jpg`), so blocklist both. News pages embed real images in the body. news261113 has `<img src="/img/app_api_261113_pricing_en.png">`, so take the first body image under `/img/` that is not a logo.

## Qwen (Alibaba)

- News: https://qwen.ai/research, https://qwen.ai/blog and https://qwen.ai/news all answer 200, but they are a client-rendered SPA. The raw HTML is just "Qwen", and WebFetch sees no posts. Posts use URLs of the form https://qwen.ai/blog?id=<slug> (for example https://qwen.ai/blog?id=qwen3.8, 200). Alibaba Cloud mirrors the posts at https://www.alibabacloud.com/blog/<slug>_<id> (for example https://www.alibabacloud.com/blog/qwen3-8-max-a-new-bar-for-coding-and-cowork_603421, 200).
- RSS: no current official feed. https://qwenlm.github.io/blog/index.xml is valid official RSS, but it is frozen: the newest item is "Qwen3Guard" from 2025-09-23. Alibaba Cloud blog feed paths (`/blog/rss`, `/blog/rss.xml`, `/blog/feed.xml`) are 404.
- Changelog, models and pricing (the strongest Qwen signal):
  - https://www.alibabacloud.com/help/en/model-studio/newly-released-models (200, server-rendered, "Model releases and updates | Last Updated: Nov 16, 2026"). Newest entry seen: 2026-11-16, `qwen4-max`, "Qwen4-Max is the next-generation flagship multimodal model in the Qwen family". Diff this page.
  - https://www.alibabacloud.com/help/en/model-studio/models (200; models and pricing)
- Hugging Face org: `Qwen` (case-sensitive: `qwen` returns []). https://huggingface.co/api/models?author=Qwen&sort=createdAt&direction=-1&limit=5 (verified). Newest: `Qwen/Qwen-Image-2.1-Turbo` (2026-10-09).
- GitHub org: `QwenLM`
  - https://github.com/QwenLM/qwen-code/releases.atom (verified; v0.28.1-preview.0, 2026-11-17)
  - https://github.com/QwenLM/Qwen3.8/releases.atom (answers, 0 entries). Use https://github.com/QwenLM/Qwen3.8/commits/main.atom (verified Atom; last commit 2026-08-17).
  - https://github.com/QwenLM/Qwen-Agent/releases.atom (verified, but stale: v0.0.26, 2025-05-29)
  - https://github.com/QwenLM/Qwen3-Coder/releases.atom (answers, 0 entries)
- Launch image: qwen.ai's og:image is a generic 80x80 icon (`https://img.alicdn.com/imgextra/i4/O1CN01OXv3EM1FN8t9W4P79_!!6000000000474-2-tps-80-80.png`), so blocklist it. The Alibaba Cloud blog mirror has a real per-post og:image (verified: `https://yqintl.alicdn.com/1ab611f7051a9845382b166092e781edb59dbab1.png` on the Qwen3.8-Max post). Hugging Face model card README images are another source.

## Microsoft AI

- News: https://microsoft.ai/news/ (redirects to https://microsoft.ai/blog/, 200). Posts are at https://microsoft.ai/news/<slug>/, for example https://microsoft.ai/news/introducing-mai-code-2-and-mai-code-2-flash/ (200).
- RSS:
  - https://microsoft.ai/feed/ answers valid RSS, but with 0 items (only channel metadata, lastBuildDate 2026-11-18). Treat it as no usable feed. The WordPress REST API is locked (401).
  - Usable official feeds: https://news.microsoft.com/source/topics/ai/feed/ (verified 2026-11-18; latest seen "Microsoft and Salesforce Announce Copilotforce..." on 2026-11-17) and https://www.microsoft.com/en-us/research/feed/ (verified 2026-11-18; latest seen 2026-11-17). https://blogs.microsoft.com/ai/feed/ is gone (HTTP 410).
  - Best fallback, the sitemaps (verified XML with lastmod): https://microsoft.ai/new-sitemap.xml (news posts; newest lastmod 2026-11-18T02:37, introducing-mai-cyber-2-flash, plus mai-image-2-7, mai-code-2, mai-licensed-weights) and https://microsoft.ai/model-sitemap.xml (model pages; newest mai-cyber-2-flash, mai-image-2-7, mai-realtime-1, mai-thinking-1, mai-voice-2). The index is https://microsoft.ai/sitemap_index.xml. A new URL in model-sitemap.xml is a strong "new MAI model" signal.
- Models and changelog:
  - https://microsoft.ai/models/ (200)
  - Azure AI Foundry "what's new": https://learn.microsoft.com/en-us/azure/foundry/whats-new-foundry (200; redirected from .../ai-foundry/whats-new-azure-ai-foundry)
  - Foundry models sold by Azure: https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/models-sold-directly-by-azure (200)
- Hugging Face org: `microsoft`. https://huggingface.co/api/models?author=microsoft&sort=createdAt&direction=-1&limit=5 (verified). Newest: `microsoft/Mage-VL-Cowork` (2026-10-30).
- GitHub org: `microsoft`
  - https://github.com/microsoft/semantic-kernel/releases.atom (verified; dotnet-1.82.0, 2026-11-07)
  - https://github.com/microsoft/autogen/releases.atom (verified, but stale: python-v0.7.5, 2025-09-30)
  - https://github.com/microsoft/BitNet/releases.atom (answers, 0 entries)
  - Not usable: github.com/microsoft/agent-framework/releases.atom answered 404.
- Launch image: verified. https://microsoft.ai/news/introducing-mai-code-2-and-mai-code-2-flash/ has `og:image` = `https://microsoft.ai/wp-content/uploads/2026/11/MAI-Code-2-Ignite-WithHeader-16x9-1.jpg`.

## NVIDIA

- News: https://blogs.nvidia.com/ (200), https://nvidianews.nvidia.com/ (200) and https://developer.nvidia.com/blog/ (200)
- RSS (all verified 2026-11-18):
  - https://blogs.nvidia.com/feed/ (latest seen "Ian Buck Kicks Off NVIDIA's Week at SC26..." on 2026-11-17)
  - https://nvidianews.nvidia.com/releases.xml (press releases; latest seen 2026-11-17/18; each item has a `media:content` image)
  - https://developer.nvidia.com/blog/feed (Atom; latest seen 2026-11-17)
  - https://research.nvidia.com/rss.xml is valid RSS but stale (2021 dates). Skip it.
- Models:
  - https://build.nvidia.com/models (200)
  - https://developer.nvidia.com/nemotron (redirects to https://developer.nvidia.com/topics/ai/nemotron, 200)
  - https://docs.api.nvidia.com/nim/reference/models-1 (200)
- Hugging Face org: `nvidia`. https://huggingface.co/api/models?author=nvidia&sort=createdAt&direction=-1&limit=5 (verified). Newest: `nvidia/Llama-3.2-1B-Qwen3.8-27B-Draft` (2026-11-11). NVIDIA posts many small models a day, so filter by name (Nemotron and similar).
- GitHub orgs: `NVIDIA`, `NVIDIA-NeMo`
  - https://github.com/NVIDIA/TensorRT-LLM/releases.atom (verified; v1.4.0rc4, 2026-11-15)
  - https://github.com/NVIDIA/Megatron-LM/releases.atom (verified; Megatron Core 0.20.0, 2026-10-29)
  - https://github.com/NVIDIA/NemoClaw/releases.atom (verified; v0.1.0-rc10, 2026-11-16)
  - https://github.com/NVIDIA-NeMo/NeMo/releases.atom (verified; NeMo Speech 3.0, 2026-08-07; github.com/NVIDIA/NeMo redirects here)
- Launch image: verified. https://blogs.nvidia.com/blog/ian-buck-sc26/ has `og:image` = `https://blogs.nvidia.com/wp-content/uploads/2026/11/Buck-Talk-SC26-scaled.jpeg`. Newsroom items carry the image in the RSS itself (`media:content url=".../nvidia-supply-chain-partners_thmb.jpg"`).

## Apple Machine Learning

- News: https://machinelearning.apple.com/ (200). Company news: https://www.apple.com/newsroom/
- RSS (all verified 2026-11-18):
  - https://machinelearning.apple.com/rss.xml (latest seen "Split-and-Scale Latent 3D Representations" on 2026-11-16)
  - https://www.apple.com/newsroom/rss-feed.rss (Atom despite the .rss name; latest seen 2026-11-17; AI item "Apple launches research study to explore the use of AI for health" on 2026-11-16)
  - https://developer.apple.com/news/rss/news.rss (latest seen 2026-11-17)
- Models and docs (Apple has no public model price list):
  - https://developer.apple.com/documentation/foundationmodels (200, Foundation Models framework)
  - https://developer.apple.com/apple-intelligence/ (200)
- Hugging Face org: `apple`. https://huggingface.co/api/models?author=apple&sort=createdAt&direction=-1&limit=5 (verified). Newest: `apple/FastFrames-S` and `apple/FastFrames-L` (2026-11-16).
- GitHub orgs: `ml-explore` (MLX), `apple`
  - https://github.com/ml-explore/mlx/releases.atom (verified; v0.32.4, 2026-10-14)
  - https://github.com/ml-explore/mlx-lm/releases.atom (verified; v0.32.2, 2026-10-16)
  - https://github.com/apple/coremltools/releases.atom (verified; 9.1.dev1, 2026-08-03)
  - https://github.com/apple/ml-fastvlm/releases.atom (answers, 0 entries)
- Launch image: Apple Newsroom posts have a real per-post og:image (verified: `https://www.apple.com/newsroom/images/2026/11/apple-launches-research-study-to-explore-the-use-of-ai-for-health/tile/Apple-Health-AI-Usage-Study-hero-lp.jpg.og.jpg?202611171700`). machinelearning.apple.com research posts use a generic og:image (`https://mlr.cdn-apple.com/media/Home_1200x630_48225d82e9.png`), so blocklist it and use the first figure in the body.

## Moonshot AI (Kimi)

- News: https://www.kimi.com/en/blog/ (200; https://www.kimi.com/blog redirects to the zh-cn version). Posts seen: /en/blog/kimi-k3-1-pro, kimi-k3, kimi-k2-6, kimi-k2-5, kimi-k2-thinking, agent-swarm. Company site: https://www.moonshot.ai/ (200).
- RSS: no official feed. https://www.kimi.com/blog/rss.xml redirects to the HTML blog, moonshotai.github.io has no feed (404), and the pages have no alternate link. Watch for new `/en/blog/<slug>` links on the blog index.
- Models and pricing (platform.moonshot.ai now redirects to platform.kimi.ai):
  - https://platform.kimi.ai/docs/models (200, "Model List")
  - https://platform.kimi.ai/docs/pricing/chat (200)
  - https://platform.kimi.ai/docs/llms.txt (200, full page index; it lists "Kimi K3.1 Pro ... 1M-token context window"). Diffing it catches new model quickstart pages. There is no changelog page: /docs/guide/changelog redirects to the API-key page.
- Hugging Face org: `moonshotai`. https://huggingface.co/api/models?author=moonshotai&sort=createdAt&direction=-1&limit=5 (verified). Newest: `moonshotai/Kimi-K3.1-Pro` (2026-11-02).
- GitHub org: `MoonshotAI`
  - https://github.com/MoonshotAI/kimi-code/releases.atom (verified; 2.7.0-canary, 2026-11-18)
  - https://github.com/MoonshotAI/kimi-cli/releases.atom (verified; 1.52.0, 2026-09-22)
  - https://github.com/MoonshotAI/Kimi-K3/releases.atom (answers, 0 entries; use commits/main.atom)
- Launch image: verified. https://www.kimi.com/en/blog/kimi-k3-1-pro has a per-post `og:image` = `https://kimi-img.kimi.ai/pub/slides/kimi-fs/managed-assets/9558f8d5-08fc-42de-8e4e-339076e03895.webp`. The blog index og:image points at the newest post's cover (`https://statics.kimi.ai/kimi-blogs/kimi-k3-1/20261022/k3-1-pro-cover.webp`).

## Zhipu AI (Z.ai, GLM)

- News: posts are at https://z.ai/blog/<slug>, for example https://z.ai/blog/glm-5.3 (200). There is no blog index: https://z.ai/blog and https://z.ai/blog/ are 404. The Chinese site has a news page at https://www.zhipuai.cn/news (200).
- RSS: https://docs.z.ai/release-notes/new-released/rss.xml (verified 2026-11-18; official, Mintlify-generated). Latest entry: 2026-08-26 (before it 2026-08-18 and 2026-06-16), so it updates rarely but is reliable.
- Changelog, models and pricing:
  - https://docs.z.ai/release-notes/new-released (200)
  - https://docs.z.ai/guides/overview/pricing (200)
  - https://docs.z.ai/llms.txt (200; its header names GLM-5.3 and GLM-5.3-FLASH)
- Hugging Face org: `zai-org`. https://huggingface.co/api/models?author=zai-org&sort=createdAt&direction=-1&limit=5 (verified). Newest: `zai-org/GLM-5.3-Flash-BF16` and `zai-org/GLM-5.3-BF16` (2026-08-25). The old org `THUDM` now returns [].
- GitHub org: `zai-org`
  - https://github.com/zai-org/ZCode/releases.atom (verified; v3.18.2, 2026-11-16)
  - https://github.com/zai-org/GLM-OCR/releases.atom (verified; v0.1.5, 2026-04-08)
  - https://github.com/zai-org/GLM-5/releases.atom (answers, 0 entries; use commits/main.atom)
- Launch image: not available from raw HTML. z.ai/blog pages are a JS shell of about 600 bytes with no og or twitter meta tags. Render the page in a headless browser and take the first hero image, or use the images in the Hugging Face or GitHub README.

## MiniMax

- News: https://www.minimax.io/news (200, client-rendered; only one link appears in raw HTML). Model launch posts are at https://www.minimax.io/blog/<slug> (for example https://www.minimax.io/blog/minimax-h3-image, 200). https://www.minimax.io/blog is 200.
- RSS: no official feed. `/news/rss.xml` answers 500, `/blog/rss.xml` 404, `/rss.xml` redirects to the homepage, and the Mintlify `release-notes/models/rss.xml` is 404.
- Changelog, models and pricing:
  - https://platform.minimax.io/docs/release-notes/models (200), with a plain-markdown twin at https://platform.minimax.io/docs/release-notes/models.md (200; dated headings). This is the best poll target. Newest entries seen: Nov. 10, 2026, MiniMax H3 Image; Oct. 19, 2026, MiniMax M3.1 Flash; Jul. 31, 2026, MiniMax H3; Jul. 16, 2026, Music-3.0.
  - API updates: https://platform.minimax.io/docs/release-notes/apis.md (200, text/markdown; listed in https://platform.minimax.io/docs/llms.txt, which is 200)
  - Pricing: https://platform.minimax.io/docs/pricing/overview (200; /docs/guides/pricing redirects here)
- Hugging Face org: `MiniMaxAI`. https://huggingface.co/api/models?author=MiniMaxAI&sort=createdAt&direction=-1&limit=5 (verified). Newest: `MiniMaxAI/MiniMax-H3-Image-PE` (2026-11-08) and `MiniMaxAI/MiniMax-H3-Image` (2026-11-03).
- GitHub org: `MiniMax-AI`
  - https://github.com/MiniMax-AI/minimax-code/releases.atom (verified; code-sdk-python-v0.1.1, 2026-11-17)
  - https://github.com/MiniMax-AI/cli/releases.atom (verified; v1.0.29, 2026-11-10)
  - https://github.com/MiniMax-AI/MiniMax-M2/releases.atom (answers, 0 entries)
  - https://github.com/MiniMax-AI/MiniMax-MCP/releases.atom (answers, 0 entries)
- Launch image: verified. https://www.minimax.io/blog/minimax-h3-image has `og:image` = `https://file.cdn.minimax.io/public/h3-image-cover-1794323228475.jpg?x-oss-process=image/format,webp`. The /news and /blog index pages use a generic image (`https://filecdn.minimax.chat/public/58eca777-e31f-448a-9823-e2220e49b426.png`), so blocklist it.

## Hugging Face

- News: https://huggingface.co/blog (200). Product changelog: https://huggingface.co/changelog (200).
- RSS: https://huggingface.co/blog/feed.xml (verified 2026-11-18; latest seen "Hugging Face and OpenRouter join forces to make open-weight models easy to run" on 2026-11-16). It includes community and partner posts (for example /blog/nvidia/..., /blog/allenai/...). The changelog has no feed (`/changelog/feed.xml` is 404).
- Cross-vendor signals (keyless JSON, verified):
  - Trending: https://huggingface.co/api/models?sort=trendingScore&direction=-1&limit=5. Top today: `higurashi-ai/Haru-4B`, `Lightricks/LTX-2.5`, `thinkingmachines/Inkling-2-Small`, `MiniMaxAI/MiniMax-H3-Image`, `harness-hub/Qwen3.8-27B-pi-adapted`.
  - Per-org newest: https://huggingface.co/api/models?author=<org>&sort=createdAt&direction=-1&limit=5 (the pattern used for every vendor above).
- Hugging Face's own orgs: `huggingface` (verified; newest `huggingface/ml-intern-models`, 2026-04-29) and `HuggingFaceTB` (verified; newest `HuggingFaceTB/nanowhale-100m-base`, 2026-04-24).
- GitHub org: `huggingface`
  - https://github.com/huggingface/transformers/releases.atom (verified; v5.23.0, 2026-11-13). Release notes name newly supported models, often on launch day.
  - https://github.com/huggingface/diffusers/releases.atom (verified; 0.43.0, 2026-11-12, "MiniMax-H3-Image, Pika H3 Flex, ...")
  - https://github.com/huggingface/huggingface_hub/releases.atom (verified; v2.4.0, 2026-10-29)
  - https://github.com/huggingface/smolagents/releases.atom (verified; v1.26.0, 2026-05-29)
- Launch image: verified. Blog posts carry `twitter:image` (for example `https://huggingface.co/blog/assets/openrouter/thumbnail.jpg`). The changelog uses a generic `https://huggingface.co/front/thumbnails/changelog.png`.

---

## Feed verification summary (2026-11-18)

| Vendor | Official feed status |
|---|---|
| OpenAI | verified 2026-11-18: openai.com/news/rss.xml |
| Anthropic | no feed for anthropic.com/news. Verified 2026-11-18: platform.claude.com release-notes feed.xml and claude.com/resources/articles/rss.xml |
| Google | verified 2026-11-18: deepmind.google/blog/rss.xml, blog.google Gemini and AI feeds, developers.googleblog.com/rss/, research.google/blog/rss/ |
| Meta AI | no feed for ai.meta.com. Verified 2026-11-18: about.fb.com/news/feed/, engineering.fb.com/feed/ |
| xAI | no official feed (x.ai/news is bot-blocked). Use docs.x.ai/developers/release-notes.md |
| Mistral | verified 2026-11-18: mistral.ai/news/rss |
| DeepSeek | no official feed. Use api-docs.deepseek.com sidebar and /updates/ |
| Qwen / Alibaba | no current feed (qwenlm.github.io/blog/index.xml is frozen since 2025-09). Use Alibaba Model Studio "newly-released-models" |
| Microsoft AI | microsoft.ai/feed/ answers but is empty (0 items). Verified 2026-11-18: news.microsoft.com/source/topics/ai/feed/ and the Microsoft Research feed. Use the microsoft.ai sitemaps |
| NVIDIA | verified 2026-11-18: blogs.nvidia.com/feed/, nvidianews releases.xml, developer blog Atom |
| Apple ML | verified 2026-11-18: machinelearning.apple.com/rss.xml, Newsroom Atom, developer news RSS |
| Moonshot | no official feed. Use the kimi.com/en/blog index and platform.kimi.ai/docs/llms.txt |
| Zhipu | verified 2026-11-18: docs.z.ai/release-notes/new-released/rss.xml (no blog feed) |
| MiniMax | no official feed. Use platform.minimax.io/docs/release-notes/models.md |
| Hugging Face | verified 2026-11-18: huggingface.co/blog/feed.xml |
