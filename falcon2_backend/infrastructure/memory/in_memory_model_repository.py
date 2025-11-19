from falcon2_backend.entities.model import Model
from typing import Dict

from falcon2_backend.services.interfaces.model_repository import ModelRepository


class InMemoryModelRepository(ModelRepository):
    def __init__(self):
        # In-memory storage
        self._storage: Dict[str, Model] = {}

    def fetch_all(self) -> Dict[str, Model]:
        """Retrieve all models stored in memory."""
        return self._storage

    def save(self, model: Model):
        """Save or update a model in memory."""
        self._storage[model.crunch_identifier] = model  # Save or update by identifier

    def clear(self):
        """Clear all models (only for testing)."""
        self._storage.clear()
