"""Cloud sync for Wystan SaaS dashboard.

Optional, opt-in module. When ``WYSTAN_API_KEY`` is set:
  - ``wystan scan`` + push upload the feature map to the SaaS
  - The MCP server batches tool-call events and sends them every minute

Without an API key, all cloud calls become silent no-ops. The CLI and
MCP server work entirely locally and never reach out to wysten.ai.
"""

from wystan.cloud.sync import push_feature_map, send_mcp_events_batch

__all__ = ["push_feature_map", "send_mcp_events_batch"]
