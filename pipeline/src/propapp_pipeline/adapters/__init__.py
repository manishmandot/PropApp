"""Source adapters. Importing this package registers every adapter in REGISTRY."""
from propapp_pipeline.adapters import (  # noqa: F401
    abs_building_approvals,
    abs_census,
    abs_erp,
    jsa_salm,
    nsw_rent,
    nsw_vg_sales,
    vic_dffh_rental,
    vic_vg_medians,
)
