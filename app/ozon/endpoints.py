from dataclasses import dataclass


@dataclass(frozen=True)
class Endpoint:
    path: str
    mutating: bool = False
    contract_verified: bool = True


# Проверено по официальному журналу Ozon Seller API на 2026-07-12.
CLUSTERS = Endpoint("/v2/cluster/list")
FBO_WAREHOUSES = Endpoint("/v1/warehouse/fbo/seller/list")
FBO_STOCKS = Endpoint("/v1/product/info/stocks-by-warehouse/fbo")
PRODUCT_LIST = Endpoint("/v3/product/list")
ANALYTICS_STOCKS = Endpoint("/v1/analytics/stocks")

DRAFT_DIRECT_CREATE = Endpoint("/v1/draft/direct/create", mutating=True, contract_verified=False)
DRAFT_INFO = Endpoint("/v2/draft/create/info")
DRAFT_TIMESLOTS = Endpoint("/v2/draft/timeslot/info")
SUPPLY_CREATE = Endpoint("/v2/draft/supply/create", mutating=True, contract_verified=False)
SUPPLY_CREATE_STATUS = Endpoint("/v2/draft/supply/create/status")
CARGOES_CREATE = Endpoint("/v1/cargoes/create", mutating=True, contract_verified=False)
CARGOES_STATUS = Endpoint("/v1/cargoes/create/info")
LABELS_CREATE = Endpoint("/v1/cargoes-label/create", mutating=True, contract_verified=False)
LABELS_GET = Endpoint("/v1/cargoes-label/get")
LABELS_FILE = Endpoint("/v1/cargoes-label/file/{file_guid}")

