from datetime import datetime
import requests
import time
import logging

from falcon2_backend.services.interfaces.price_repository import PriceRepository, Prices


class CrunchdaoPricesHttpRepository(PriceRepository):

    def __init__(self, url="https://api--pricedb--tournament.crunchdao.cloud/v1/prices", retries=10, backoff=5):
        self.url = url
        self.retries = retries
        self.backoff = backoff
        self.logger = logging.getLogger(__spec__.name if __spec__ else __name__)

    def fetch_historical_prices(self, asset, from_: datetime, to: datetime, resolution) -> Prices:
        self.logger.debug(f"Fetching historical prices with parameters: asset={asset}, from={from_}, to={to}, resolution={resolution}")

        params = {
            "asset": asset,
            "from": int(from_.timestamp()),
            "to": int(to.timestamp()),
            "resolution": resolution
        }

        for attempt in range(self.retries):
            try:
                response = requests.get(self.url, params=params, timeout=10)
                response.raise_for_status()
                data = response.json()
                return list(zip(data["timestamp"], data["close"]))
            except requests.RequestException as e:
                logging.error(f"Attempt {attempt + 1} failed: {e}")
                if attempt < self.retries - 1:
                    time.sleep(self.backoff)
                else:
                    raise


if __name__ == "__main__":
    from datetime import datetime, timedelta, timezone
    logging.basicConfig(level=logging.DEBUG)

    repository = CrunchdaoPricesHttpRepository()

    # Test parameters
    asset = "BTC"
    now = datetime.now(timezone.utc)
    from_date = now - timedelta(days=30)
    to_date = now
    resolution = "minute"

    try:
        prices = repository.fetch_historical_prices(asset, from_date, to_date, resolution)
        logging.info(f"Fetched {len(prices)} prices for asset {asset}")
        #logging.debug(f"Prices: {prices}")
    except Exception as e:
        logging.error(f"An error occurred while fetching prices: {e}")
