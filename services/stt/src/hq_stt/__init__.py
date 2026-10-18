"""stt: Persian speech to text on the hub's own CPU (prompt 06 §3, contract §17.2).

faster-whisper (CTranslate2, int8) with a pinned model fetched once into a
volume; no audio ever leaves the hub. Only the worker reaches it (network
hq-stt). The text is normalised deterministically (hq_common.persian).
"""
