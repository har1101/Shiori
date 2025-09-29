from mcp import stdio_client, StdioServerParameters
from strands.tools.mcp import MCPClient
import logging
import os
from boto3.session import Session
from typing import Optional

log = logging.getLogger("mcp_config")

_boto_session = Session()
region = _boto_session.region_name or "us-east-1"

class LocalMCPConfig:
    def __init__(self):
        self.aurora_endpoint = os.environ.get("AURORA_DSQL_CLUSTER_ENDPOINT", "")
        self.aurora_db_user = os.environ.get("AURORA_DSQL_DATABASE_USER", "")
        self.aurora_region = region
        self._client: Optional[MCPClient] = None

        if not self.aurora_endpoint:
            raise ValueError("AURORA_DSQL_CLUSTER_ENDPOINT is not set")
        if self.aurora_endpoint == "":
            raise ValueError("AURORA_DSQL_CLUSTER_ENDPOINT is not set")
        if not self.aurora_db_user:
            raise ValueError("AURORA_DSQL_DATABASE_USER is not set")
        if self.aurora_db_user == "":
            raise ValueError("AURORA_DSQL_DATABASE_USER is not set")
        
    async def build_client(self) -> MCPClient:
        if self._client:
            return self._client
        
        local_mcp_client = MCPClient(lambda: stdio_client(
            StdioServerParameters(
                command="uvx",
                args=[
                    "awslabs.aurora-dsql-mcp-server@latest",
                    "--cluster_endpoint", self.aurora_endpoint,
                    "--database_user", self.aurora_db_user,
                    "--allow-writes",
                    "--region", self.aurora_region
                ],
                env={
                    "FASTMCP_LOG_LEVEL": "ERROR"
                },
            )
        ))
        
        # 接続確認
        with local_mcp_client:
            tools = local_mcp_client.list_tools_sync()

        self._client = local_mcp_client
        return self._client
