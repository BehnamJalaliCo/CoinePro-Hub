# Model-provider logos

The SVGs in this folder come from **LobeHub Icons** (`@lobehub/icons-static-svg` 1.95.1, MIT License,
https://github.com/lobehub/lobe-icons). The marks themselves belong to their companies; they appear only to label which provider's model a
treasury line used. `gen_logos.py` turns them into the web's `src/generated/provider-logos.ts` and Android's `ProviderLogos.kt`
(gradient overlays are dropped or flattened to their first colour, so both clients draw plain filled paths).
