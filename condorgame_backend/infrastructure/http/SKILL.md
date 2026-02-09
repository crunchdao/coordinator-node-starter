---
name: coordinator-data-sources
description: Use when customizing price feeds or data sources - replacing CrunchDAO/Pyth APIs with custom data providers
---

# Customizing Data Sources

Replace CrunchDAO/Pyth price feeds with your own data sources (different APIs, databases, files, etc.).

## Interface Contract

All data sources implement `PriceRepository` from `services/interfaces/price_repository.py`:

```python
from abc import ABC, abstractmethod
from datetime import datetime

Prices = list[tuple[int, float]]  # list of (timestamp, price)

class PriceRepository(ABC):
    @abstractmethod
    def fetch_historical_prices(self, asset, from_: datetime, to: datetime, resolution) -> Prices:
        pass
```

**Parameters:**
- `asset`: Asset code (e.g., "BTC", "ETH")
- `from_`, `to`: Time range (datetime, UTC)
- `resolution`: Data granularity (e.g., "minute", "hour")

**Returns:** List of `(unix_timestamp, price)` tuples, ordered by time ascending.

## Existing Implementations

### CrunchDAO Prices (`crunchdao_prices_http_repository.py`)

```python
class CrunchdaoPricesHttpRepository(PriceRepository):
    def __init__(self, url="https://api--pricedb--tournament.crunchdao.cloud/v1/prices", retries=10, backoff=5):
        self.url = url
        self.retries = retries
        self.backoff = backoff

    def fetch_historical_prices(self, asset, from_: datetime, to: datetime, resolution) -> Prices:
        params = {
            "asset": asset,
            "from": int(from_.timestamp()),
            "to": int(to.timestamp()),
            "resolution": resolution
        }
        response = requests.get(self.url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        return list(zip(data["timestamp"], data["close"]))
```

### Pyth Prices (`pyth_prices_http_repository.py`)

Similar pattern, different API endpoint and response format.

## Step-by-Step: Add Custom Data Source

### 1. Create New Repository

Create `condorgame_backend/infrastructure/http/my_prices_http_repository.py`:

```python
from datetime import datetime
import requests
import logging

from condorgame_backend.services.interfaces.price_repository import PriceRepository, Prices


class MyPricesHttpRepository(PriceRepository):
    
    def __init__(self, api_key: str, base_url: str = "https://my-api.com/prices"):
        self.api_key = api_key
        self.base_url = base_url
        self.logger = logging.getLogger(__name__)

    def fetch_historical_prices(self, asset, from_: datetime, to: datetime, resolution) -> Prices:
        self.logger.debug(f"Fetching {asset} from {from_} to {to}")
        
        # Adapt to your API's expected format
        response = requests.get(
            f"{self.base_url}/{asset}",
            headers={"Authorization": f"Bearer {self.api_key}"},
            params={
                "start": from_.isoformat(),
                "end": to.isoformat(),
                "interval": resolution
            },
            timeout=30
        )
        response.raise_for_status()
        
        # Transform response to expected format: list of (timestamp, price)
        data = response.json()
        return [(int(item["ts"]), float(item["price"])) for item in data["prices"]]
```

### 2. Export from Package

Edit `condorgame_backend/infrastructure/http/__init__.py`:

```python
from .crunchdao_prices_http_repository import CrunchdaoPricesHttpRepository
from .pyth_prices_http_repository import PythPricesHttpRepository
from .my_prices_http_repository import MyPricesHttpRepository  # Add this
```

### 3. Wire Up in Workers

Edit `condorgame_backend/workers/predict_worker.py`:

```python
# Before
from condorgame_backend.infrastructure.http import CrunchdaoPricesHttpRepository
price_repo = CrunchdaoPricesHttpRepository()

# After
from condorgame_backend.infrastructure.http import MyPricesHttpRepository
price_repo = MyPricesHttpRepository(api_key=os.getenv("MY_API_KEY"))
```

Do the same in `condorgame_backend/workers/score_worker.py`.

### 4. Add Environment Variables

Edit `.local.env` (and `.dev.env`, `.production.env`):

```
MY_API_KEY=your-api-key-here
```

Edit `docker-compose.yml` to pass the variable:

```yaml
predict-worker:
  environment:
    MY_API_KEY: ${MY_API_KEY}
```

### 5. Update Asset Codes

If your data source uses different asset codes, update `prediction_configs` in the database or seed data.

## Advanced: Multiple Data Sources

For different assets from different sources:

```python
class CompositeePriceRepository(PriceRepository):
    def __init__(self):
        self.crypto_repo = CrunchdaoPricesHttpRepository()
        self.stocks_repo = MyStocksRepository()
    
    def fetch_historical_prices(self, asset, from_, to, resolution) -> Prices:
        if asset in ["BTC", "ETH", "SOL"]:
            return self.crypto_repo.fetch_historical_prices(asset, from_, to, resolution)
        else:
            return self.stocks_repo.fetch_historical_prices(asset, from_, to, resolution)
```

## Caching Layer

The system uses `PriceStore` (`infrastructure/memory/prices_cache.py`) for in-memory caching:

- Predict worker caches 30 days of prices
- Score worker caches 7 days of prices
- Cache is refreshed incrementally via `_update_prices()`

If your data source is slow or rate-limited, the cache protects you.

## Testing Your Implementation

```python
if __name__ == "__main__":
    from datetime import datetime, timedelta, timezone
    import logging
    logging.basicConfig(level=logging.DEBUG)

    repo = MyPricesHttpRepository(api_key="test-key")
    
    now = datetime.now(timezone.utc)
    prices = repo.fetch_historical_prices(
        asset="BTC",
        from_=now - timedelta(days=1),
        to=now,
        resolution="minute"
    )
    
    print(f"Fetched {len(prices)} prices")
    print(f"First: {prices[0]}, Last: {prices[-1]}")
```

Run with: `python -m condorgame_backend.infrastructure.http.my_prices_http_repository`
