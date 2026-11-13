"""⟨1.37⟩ Contract §59.9-§59.10 (prompt 38): the automations board, its health, the owner's day, the
calendar and an automation's audit; the one switch for every kind that is not a flow.

STUB (groundwork): the board's builder fills this module. `switch` is called by
`POST /automations/{ref}/state` for any ref that is not a flow (routes/automations.py)."""

from __future__ import annotations

from typing import Any

from hq_api.db import Tx
from hq_api.principal import Principal


async def switch(tx: Tx, hub: Any, ref: str, state: str, who: Principal) -> bool:
    """The owner's switch on a board item of kind `routine`, `standing_publish` (`SP:<group>:<co>`),
    `line` (`LN-…`) or `archive` (`AU-…`): True when this module handled `ref`, False for a ref it
    does not know (a §31.7 rule then goes on as before)."""
    del tx, hub, ref, state, who
    return False
