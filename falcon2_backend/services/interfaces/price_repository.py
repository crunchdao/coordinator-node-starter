from abc import ABC, abstractmethod
from datetime import datetime


class PriceRepository(ABC):

    # todo define resolution type
    @abstractmethod
    def fetch_historical_prices(self, asset, from_: datetime, to: datetime, resolution) -> list[tuple[int, float]]:
        pass
