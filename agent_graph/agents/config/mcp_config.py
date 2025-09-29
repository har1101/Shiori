from __future__ import annotations
from typing import Optional
import logging

from bedrock_agentcore.identity.auth import requires_api_key
from strands.tools.mcp import MCPClient
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamablehttp_client

# --- sse/connection 警告を抑制（ログフィルタ）-------------------------------
class SuppressSSEConnectionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = str(record.getMessage())
        return "method='sse/connection'" not in msg

# フィルタを root に追加（戻り値は None なので変数に代入しない）
logging.getLogger().addFilter(SuppressSSEConnectionFilter())

log = logging.getLogger("mcp_config")


class MCPConfig:
    """
    AgentCore Identity に保存した API Key を取得し、
    引数の与え方でトランスポートを自動選択して MCPClient を返す。

    判定ルール:
      - sse_path_template が与えられていれば → SSE
      - それ以外（http_path_template が None でも） → HTTP

    例:
      # Firecrawl（SSE・APIキーを URL に埋め込む）
      MCPConfig(
        provider_name="firecrawl_api_key",
        base_url="https://mcp.firecrawl.dev",
        http_path_template=None,
        sse_path_template="/{API_KEY}/v2/sse",
      )

      # AWS Knowledge MCP（HTTPのみ・APIキー不要）
      MCPConfig(
        provider_name=None,
        base_url="https://knowledge-mcp.global.api.aws",
        http_path_template="",        # ルート直下
        sse_path_template=None,
      )
    """

    def __init__(
        self,
        provider_name: Optional[str],
        base_url: str,
        http_path_template: Optional[str] = None,
        sse_path_template: Optional[str] = None,
        validate_on_connect: bool = True,
    ):
        self.provider_name = provider_name
        self.base_url = (base_url or "").rstrip("/")
        self.http_path_template = http_path_template
        self.sse_path_template = sse_path_template
        self.validate_on_connect = validate_on_connect
        self._client: Optional[MCPClient] = None

    def _fetcher(self):
        @requires_api_key(provider_name=self.provider_name)
        async def _get(*, api_key: str) -> str:
            return api_key
        return _get
    
    async def _get_api_key(self, needs_key: bool) -> Optional[str]:
        if not needs_key:
            return None
        if not self.provider_name:
            raise RuntimeError(
                "provider_name が指定されていないのに API キーが必要です。"
            )
        fetch = self._fetcher()
        api_key = await fetch()
        if not api_key:
            raise RuntimeError(
                f"AgentCore Identity から '{self.provider_name}' を取得できませんでした。"
            )
        return api_key

    # ---- URL 組み立て ------------------------------------------------------
    def _compose_http_url(self, api_key: Optional[str]) -> str:
        path = self.http_path_template or ""
        if "{API_KEY}" in path and not api_key:
            raise RuntimeError("HTTP パスに {API_KEY} が含まれていますが、API キーが取得できていません。")
        path = path.replace("{API_KEY}", api_key or "")
        return f"{self.base_url}{path}"

    def _compose_sse_url(self, api_key: Optional[str]) -> str:
        if not self.sse_path_template:
            raise RuntimeError("SSE を選択しましたが sse_path_template が未指定です。")
        if "{API_KEY}" in self.sse_path_template and not api_key:
            raise RuntimeError("SSE パスに {API_KEY} が含まれていますが、API キーが取得できていません。")
        path = self.sse_path_template.replace("{API_KEY}", api_key or "")
        return f"{self.base_url}{path}"

    # ---- クライアント構築（HTTP/SSE を自動選択）----------------------------
    async def build_client(self) -> MCPClient:
        if self._client:
            return self._client

        use_sse = self.sse_path_template is not None
        # {API_KEY} を含むテンプレートがある場合のみキー取得
        needs_key = False
        template = self.sse_path_template if use_sse else (self.http_path_template or "")
        if "{API_KEY}" in (template or ""):
            needs_key = True
        api_key = await self._get_api_key(needs_key)

        if use_sse:
            url = self._compose_sse_url(api_key)
            log.info(f"[MCP] Use SSE endpoint: {self.base_url}/... (masked)")
            client = MCPClient(lambda: sse_client(url))
        else:
            url = self._compose_http_url(api_key)
            log.info(f"[MCP] Use HTTP endpoint: {self.base_url}/... (masked)")
            client = MCPClient(lambda: streamablehttp_client(url))

        if self.validate_on_connect:
            # 早期に接続確認（tools 列挙）
            with client:
                _ = client.list_tools_sync()

        self._client = client
        return self._client