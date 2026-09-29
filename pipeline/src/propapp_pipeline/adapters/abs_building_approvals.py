from propapp_pipeline.adapters.abs_sdmx import AbsSdmxAdapter
from propapp_pipeline.adapters.base import register
from propapp_pipeline.models import Period


@register
class AbsBuildingApprovalsAdapter(AbsSdmxAdapter):
    """ABS Building Approvals by SA2, monthly: total dwelling units approved."""

    source_id = "abs_building_approvals"
    metric = "building_approvals_dwellings"

    def period(self, time_period):
        year, month = time_period.split("-")
        return Period.month(int(year), int(month))
