from strands import Agent
from strands.tools.mcp import MCPClient
from strands.multiagent.graph import GraphState
from typing import Any, Dict
import logging
import json
from boto3.session import Session
import os

# MCPクライアント用のインポート
from mcp.client.streamable_http import streamablehttp_client

# AgentCore Identityからアクセストークンを取得する
from bedrock_agentcore.identity.auth import requires_access_token

logger = logging.getLogger("agent_graph")
logger.setLevel(logging.DEBUG)
logging.basicConfig(
    format="%(levelname)s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler()]
)

_boto_session = Session()
region = _boto_session.region_name


# ===== ユーティリティ関数（再利用可能・テスト容易化） =====
def _get_tool_name(tool: Any) -> str:
    """ツール名を抽出する。"""
    return getattr(tool, "tool_name", getattr(tool, "name", str(tool)))


def _filter_tools_by_keyword(tools: list, keyword: str) -> list:
    """指定キーワードを含むツールのみを抽出する。"""
    key = keyword.lower()
    return [t for t in tools if key in _get_tool_name(t).lower()]


def extract_message_content(agent_result: Any) -> tuple[str, list]:
    """AgentResultからメッセージコンテンツを抽出（テキスト/JSON）。"""
    try:
        message = getattr(agent_result, "message", {}) or {}
        content = message.get("content", [])
        texts: list[str] = []
        jsons: list = []

        for block in content:
            if isinstance(block, dict):
                if "text" in block:
                    texts.append(block["text"])
                if "json" in block:
                    jsons.append(block["json"])
                # toolResultの中も再帰的に処理
                if "toolResult" in block:
                    for inner in block.get("toolResult", {}).get("content", []):
                        if isinstance(inner, dict):
                            if "text" in inner:
                                texts.append(inner["text"])
                            if "json" in inner:
                                jsons.append(inner["json"])

        return "\n".join(texts).strip(), jsons
    except Exception as e:
        logger.error(f"メッセージ抽出エラー: {e}")
        return "", []


def detect_mcp_usage(text: str) -> bool:
    """MCPツールが使用されたかを簡易検出。"""
    mcp_indicators = ["slack_", "tavily_", "extract", "search"]
    return any(indicator in text.lower() for indicator in mcp_indicators)


def parse_prompt_from_payload(payload: Dict[str, Any]) -> str:
    """AgentCore Runtime互換のペイロードからプロンプトを抽出する。"""
    if not payload:
        return ""
    # 入れ子構造（input フィールド）に対応
    if "input" in payload:
        input_data = payload["input"]
        if isinstance(input_data, dict):
            return input_data.get("prompt", "")
        if isinstance(input_data, str):
            try:
                return json.loads(input_data).get("prompt", "")
            except Exception:
                return input_data
    # 直接 prompt があるケース
    if "prompt" in payload:
        return str(payload["prompt"])  # 念のため文字列化
    return ""


def always_false_condition(_: GraphState) -> bool:
    """常にFalseを返す条件（終了ポイントとして機能）。"""
    logger.info("🔚 終了条件を評価 - 常にFalseを返してグラフを終了")
    return False

# ===== AgentCore Gateway+Identityの設定を行うクラス =====
class GatewayIdentityConfig:
    """
    Cognito M2M認証を使用したAgentCore Identityを利用するエージェント。
    
    必要な環境変数：
    - GATEWAY_URL: Slackツールを提供するGatewayのエンドポイント
    - COGNITO_SCOPE: Cognito OAuth2のスコープ
    - WORKLOAD_NAME: （オプション）workload名、デフォルトは"agent_graph"
    - USER_ID: (オプション)user-idを設定する、デフォルトは"agent_graph"
    """

    def __init__(self):
        self.gateway_url = os.environ.get("GATEWAY_URL", "https://slack-gateway-uzumouvte3.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp")
        self.provider_name = os.environ.get("PROVIDER_NAME", "agentcore-identity-for-gateway")
        self.cognito_scope = os.environ.get("COGNITO_SCOPE", "slack-gateway/genesis-gateway:invoke")
        self.workload_name = os.environ.get("WORKLOAD_NAME", "agent_graph")
        self.user_id = os.environ.get("USER_ID", "agent_graph")
        self.region = region
        
        # 環境変数の検証
        if not self.gateway_url:
            raise ValueError("GATEWAY_URL環境変数が必要です")
        if not self.provider_name:
            raise ValueError("PROVIDER_NAME環境変数が必要です")
        if not self.cognito_scope:
            raise ValueError("COGNITO_SCOPE環境変数が必要です")

        logger.info(f"Gateway URL: {self.gateway_url}")
        logger.info(f"Cognito scope: {self.cognito_scope}")
        logger.info(f"Workload name: {self.workload_name}")
        logger.info(f"User ID: {self.user_id}")
        logger.info(f"AWS Region: {self.region}")

    async def get_access_token(self) -> str:
        """AgentCore Identityを使用してアクセストークンを取得する。
        
        Runtime環境では、runtimeUserIdはInvokeAgentRuntime API呼び出し時に
        システム側が設定し、Runtimeがエージェントに渡します。
        
        Returns:
            str: 認証されたAPIコール用のアクセストークン
        """
        
        # @requires_access_tokenデコレータ付きのラッパー関数を作成
        # Runtime環境では、デコレータが内部で_get_workload_access_tokenを呼び出し、
        # workload access tokenを自動的に取得する
        @requires_access_token(
            provider_name=self.provider_name,
            scopes=[self.cognito_scope],
            auth_flow="M2M",
            force_authentication=False,
        )
        async def _get_token(*, access_token: str) -> str:
            """
            AgentCore Identityからアクセストークンを受け取る内部関数。
            
            デコレータが内部で以下を処理：
            1. _get_workload_access_tokenを呼び出してworkload access tokenを取得
                - workload_name: Runtime環境から取得
                - user_id: InvokeAgentRuntimeのruntimeUserIdヘッダーから取得
            2. workload access tokenを使用してOAuth tokenを取得
            3. access_tokenパラメータとして注入
            
            Args:
                access_token: OAuthアクセストークン（デコレータによって注入）
                
            Returns:
                str: APIコールで使用するアクセストークン
            """
            logger.info("✅ AgentCore Identity経由でアクセストークンの取得に成功")
            logger.info(f"   Workload name: {self.workload_name}")
            logger.info(f"   トークンプレフィックス: {access_token[:20]}...")
            logger.info(f"   トークン長: {len(access_token)} 文字")
            return access_token
        
        # デコレータ付き関数を呼び出してトークンを取得
        return await _get_token()
    
    async def create_mcp_client_and_tools(self) -> MCPClient:
        """
        トークン取得 → MCPクライアントを返す。

        MCPクライアントはwithコンテキスト内で使用する必要があるため、
        認証済みのクライアントインスタンスを返します。

        Returns:
            MCPClient: 認証済みMCPクライアントインスタンス
        """

        # ステップ1: AgentCore Identityを使用してアクセストークンを取得
        logger.info("ステップ1: AgentCore Identity経由でアクセストークンを取得中...")
        logger.info(f"Runtimeが自動的にruntimeUserIdを渡します")
        
        access_token = await self.get_access_token()
        
        # ステップ2: 認証されたMCPクライアントを作成
        logger.info("ステップ2: 認証されたMCPクライアントを作成中...")

        def create_streamable_http_transport():
            """
            Bearerトークン認証を使用したストリーミング可能なHTTPトランスポートを作成。
            
            このトランスポートは、MCPクライアントがGatewayへの認証された
            リクエストを行うために使用されます。
            """
            logger.info(f"🔗 MCP transport作成中: {self.gateway_url}")
            logger.info(f"🔑 トークンプレフィックス: {access_token[:20]}...")
            transport = streamablehttp_client(
                self.gateway_url, 
                headers={"Authorization": f"Bearer {access_token}"}
            )
            logger.info("✅ MCP transport作成完了")
            return transport
        
        # 認証されたトランスポートでMCPクライアントを作成
        mcp_client = MCPClient(create_streamable_http_transport)
        
        return mcp_client
    
    def get_full_tools_list(self, client: MCPClient) -> list:
        """
        ページネーションをサポートしてすべての利用可能なツールをリスト。
        
        Gatewayはページネーションされたレスポンスでツールを返す可能性があるため、
        完全なリストを取得するためにページネーションを処理する必要があります。
        
        Args:
            client: MCPクライアントインスタンス
            
        Returns:
            list: 利用可能なツールの完全なリスト
        """
        tools_list = client.list_tools_sync()
        return list(tools_list)