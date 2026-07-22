import asyncio
import json
import unittest
from unittest.mock import AsyncMock

from app.inventory.contract_probe import OzonContractProbe
from app.ozon.endpoints import ANALYTICS_STOCKS, CLUSTERS, FBO_STOCKS, FBO_WAREHOUSES, PRODUCT_LIST
from app.ozon.read_api import OzonReadApi
from app.ozon.transport import MockTransport
from app.core.errors import ExternalServiceError


class InventoryContractProbeTest(unittest.TestCase):
    def test_capture_preserves_shape_and_removes_values(self):
        transport = MockTransport({
            PRODUCT_LIST.path: [{"result": {"items": [{"product_id": 999, "offer_id": "SECRET-SKU", "sku": 321}]}}],
            CLUSTERS.path: [{"clusters": [{"id": 987, "name": "Москва"}]}],
            FBO_WAREHOUSES.path: [{"result": [{"warehouse_id": 654, "name": "Склад"}]}],
            FBO_STOCKS.path: [{"items": [{"sku": 321, "offer_id": "SECRET-SKU", "present": 17}]}],
            ANALYTICS_STOCKS.path: [{"result": {"rows": [{"sku": 321, "stock": 17.0}]}}],
        })

        document = asyncio.run(OzonContractProbe(OzonReadApi(transport)).capture())
        text = document.decode("utf-8")
        data = json.loads(text)

        self.assertEqual(data["fbo_stocks"]["response"]["items"][0]["offer_id"], "sample")
        self.assertEqual(data["fbo_stocks"]["response"]["items"][0]["sku"], 1)
        self.assertNotIn("SECRET-SKU", text)
        self.assertNotIn("Москва", text)
        self.assertEqual(data["products"]["response"]["result"]["items"][0]["product_id"], 1)
        fbo_call = next(payload for path, payload in transport.calls if path == FBO_STOCKS.path)
        analytics_call = next(payload for path, payload in transport.calls if path == ANALYTICS_STOCKS.path)
        self.assertEqual(fbo_call, {"skus": [321]})
        self.assertEqual(analytics_call, {"skus": [321]})

    def test_capture_includes_safe_http_status_without_error_body(self):
        api = AsyncMock()
        api.clusters.side_effect = ExternalServiceError("private response", status_code=400)
        api.products.return_value = {"result": {"items": [{"sku": 321}]}}
        api.warehouses.side_effect = ExternalServiceError("private response", status_code=403)
        api.fbo_stocks.side_effect = ExternalServiceError("private response", status_code=404, metadata={"field_identifiers": ["sku"]})
        api.analytics_stocks.side_effect = ExternalServiceError("private response", status_code=429)

        text = asyncio.run(OzonContractProbe(api).capture()).decode("utf-8")
        data = json.loads(text)

        self.assertEqual(data["fbo_stocks"]["http_status"], 404)
        self.assertEqual(data["analytics_stocks"]["http_status"], 429)
        self.assertEqual(data["fbo_stocks"]["field_identifiers"], ["sku"])
        self.assertNotIn("private response", text)


if __name__ == "__main__":
    unittest.main()
