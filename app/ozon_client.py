"""Совместимый фасад Ozon-клиента."""
from app.core.errors import ExternalServiceError as OzonApiError
from app.ozon.read_api import OzonReadApi
from app.ozon.transport import OzonHttpTransport


class OzonClient:
    def __init__(self, client_id: str, api_key: str) -> None:
        self.transport = OzonHttpTransport(client_id, api_key)
        self.api = OzonReadApi(self.transport)

    async def test_connection(self):
        return await self.api.test_connection()

    async def close(self) -> None:
        await self.transport.close()
