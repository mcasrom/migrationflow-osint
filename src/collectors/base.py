from abc import ABC, abstractmethod
from src.logging import get_logger
from src.models import Event
from src.db import save_events_batch, record_run_start, record_run_end

logger = get_logger("src.collectors.base")


class BaseCollector(ABC):
    name: str = ""
    source: str = ""

    @abstractmethod
    async def collect(self) -> list[Event]:
        pass

    async def run(self) -> list[Event]:
        run_id = record_run_start(self.name)
        events: list[Event] = []
        try:
            events = await self.collect()
            created, updated = save_events_batch(events)
            record_run_end(run_id, True, created, updated,
                           meta={"events": len(events)})
            logger.info("[OK] %s: %d eventos (%d nuevos, %d actualizados)",
                        self.name, len(events), created, updated)
            return events
        except Exception as e:
            logger.error("[%s] error: %s", self.name, e)
            record_run_end(run_id, False, 0, 0, error=str(e))
            return []
