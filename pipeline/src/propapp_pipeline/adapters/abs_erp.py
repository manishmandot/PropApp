from propapp_pipeline.adapters.abs_sdmx import AbsSdmxAdapter
from propapp_pipeline.adapters.base import register
from propapp_pipeline.models import Period


@register
class AbsErpAdapter(AbsSdmxAdapter):
    """ABS Estimated Resident Population by SA2 (dataflow ABS_ANNUAL_ERP_ASGS2021)."""

    source_id = "abs_erp"
    metric = "population"

    def period(self, time_period):
        return Period.year(int(time_period[:4]))
