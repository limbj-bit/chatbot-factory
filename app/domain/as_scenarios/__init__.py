"""Cafe24 AS conversation scenarios (cancel / exchange / partial return).

API adapters plug in later; the state machine is channel-agnostic.
"""

from app.domain.as_scenarios.machine import AsScenarioMachine, advance
from app.domain.as_scenarios.models import (
    AsIntent,
    AsScenarioEvent,
    AsScenarioState,
    AsScenarioStatus,
    AsSlots,
)

__all__ = [
    "AsIntent",
    "AsScenarioEvent",
    "AsScenarioMachine",
    "AsScenarioState",
    "AsScenarioStatus",
    "AsSlots",
    "advance",
]
