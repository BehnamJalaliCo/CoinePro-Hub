"""The media studio's sandboxed render worker (prompt 13 §2.3, contract §22.2
step 6): a one-shot in the opt-in profile `media`.

    courier  (network hq-media: the api and OpenBao only) claims a job, writes
             it into the job volume, and later sends the outputs back;
    render   (no network at all, read-only root, uid 10001, every capability
             dropped but SYS_CHROOT for Chromium's own sandbox, Playwright's
             seccomp profile) draws the composition frame by frame in headless
             Chromium and muxes it with ffmpeg.

The composition is untrusted data: it is re-checked by rule
(hq_common.composition) before anything is drawn, every request its page
makes is aborted and recorded unless it is one of the harness's own files,
and the page runs on a virtual clock.
"""
