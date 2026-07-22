import asyncio
import unittest

from app.inventory.gateway import OzonAnalyticsInventoryGateway
from app.ozon.endpoints import ANALYTICS_STOCKS, PRODUCT_LIST
from app.ozon.read_api import OzonReadApi
from app.ozon.transport import MockTransport


class InventoryGatewayContractTest(unittest.TestCase):
    def test_verified_analytics_fixture_maps_stocks_and_deduplicates_cluster_demand(self):
        transport = MockTransport({
            PRODUCT_LIST.path: [{"result": {"items": [
                {"sku": 101, "has_fbo_stocks": True},
                {"sku": 202, "has_fbo_stocks": False},
            ], "last_id": ""}}],
            ANALYTICS_STOCKS.path: [{"items": [
                {"sku": 101, "offer_id": "A-101", "warehouse_id": 11, "warehouse_name": "Склад 1", "cluster_id": 7, "cluster_name": "Москва", "available_stock_count": 12, "ads_cluster": 2.25},
                {"sku": 101, "offer_id": "A-101", "warehouse_id": 12, "warehouse_name": "Склад 2", "cluster_id": 7, "cluster_name": "Москва", "available_stock_count": 8, "ads_cluster": 2.25},
            ]}],
        })
        gateway = OzonAnalyticsInventoryGateway(OzonReadApi(transport))

        stocks = asyncio.run(gateway.stock_snapshots())
        demand = asyncio.run(gateway.demand_snapshots())

        self.assertEqual([row.present for row in stocks], [12, 8])
        self.assertEqual(len(demand), 1)
        self.assertEqual(demand[0].units / demand[0].period_days, 2.25)
        analytics_call = next(payload for path, payload in transport.calls if path == ANALYTICS_STOCKS.path)
        self.assertEqual(analytics_call, {"skus": [101]})

    def test_missing_contract_field_fails_closed(self):
        gateway = OzonAnalyticsInventoryGateway(OzonReadApi(MockTransport({
            PRODUCT_LIST.path: [{"result": {"items": [{"sku": 101, "has_fbo_stocks": True}], "last_id": ""}}],
            ANALYTICS_STOCKS.path: [{"items": [{"sku": 101}]}],
        })))

        with self.assertRaisesRegex(RuntimeError, "Неполный DTO"):
            asyncio.run(gateway.stock_snapshots())

    def test_null_cluster_sales_means_zero_demand(self):
        gateway = OzonAnalyticsInventoryGateway(OzonReadApi(MockTransport({
            PRODUCT_LIST.path: [{"result": {"items": [{"sku": 101, "has_fbo_stocks": True}], "last_id": ""}}],
            ANALYTICS_STOCKS.path: [{"items": [
                {"sku": 101, "offer_id": "A-101", "warehouse_id": 11, "warehouse_name": "Склад", "cluster_id": 7, "cluster_name": "Москва", "available_stock_count": 12, "ads_cluster": None},
            ]}],
        })))

        asyncio.run(gateway.stock_snapshots())
        demand = asyncio.run(gateway.demand_snapshots())

        self.assertEqual(demand[0].units, 0)

    def test_invalid_identifier_reports_field_without_value(self):
        gateway = OzonAnalyticsInventoryGateway(OzonReadApi(MockTransport({
            PRODUCT_LIST.path: [{"result": {"items": [{"sku": 101, "has_fbo_stocks": True}], "last_id": ""}}],
            ANALYTICS_STOCKS.path: [{"items": [
                {"sku": 101, "offer_id": "A-101", "warehouse_id": None, "warehouse_name": "Склад", "cluster_id": 7, "cluster_name": "Москва", "available_stock_count": 12, "ads_cluster": 1.0},
            ]}],
        })))

        with self.assertRaisesRegex(RuntimeError, "warehouse_id"):
            asyncio.run(gateway.stock_snapshots())
