"""Funnel, referral rescue, templates, lifecycle rules and NPS (prompt 10 §3,
§7; contract §19.2, §19.5). Empty until those sections land.

Owner (/api/v1):  /growth/funnel, /growth/rescue (+ /{ref}), /growth/templates
                  (+ /{ref}/seal 🔏 growth.template = ref@version:sha256), /growth/rules
                  (+ /{ref}/seal 🔏 growth.rule, /pause, /resume 🔏), /growth/nps
Agents (/internal/v1, internal_router): referral.check, rescue.update; OPA op "funnel.read".
Tables: growth.* (migration 0025). A rule sends only a sealed template under a
sealed rule, after the outbound guard, and never while the gate is locked.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["growth"])
internal_router = APIRouter(tags=["internal"])
