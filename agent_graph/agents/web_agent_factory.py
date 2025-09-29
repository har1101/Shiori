from strands import Agent
from strands.tools.mcp import MCPClient
import logging
from boto3.session import Session
import os

from agents.config.gateway_identity_config import _get_tool_name
from agents.config.mcp_config import MCPConfig

logger = logging.getLogger("web_search_agent")
logger.setLevel(logging.INFO)
logging.basicConfig(
    format="%(levelname)s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler()]
)

boto_session = Session()
region = boto_session.region_name

# システムプロンプトを定義
ACTIVITY_SEARCH_SYSTEM_PROMPT = """
あなたは活動内容分析アシスタントです。
提供されたURLから以下の情報を抽出してください：

1. 活動の種類判定:
    - event_presentation: 登壇・発表
    - article: ブログ記事・技術記事
    - study_group: 勉強会開催
    - other: その他

2. connpassのURLの場合、connpass_search_toolまたはextract_connpass_from_urlを使用し以下の内容を抽出
    - イベント名
    - 開催日時
    - 参加者数

3. その他のURLの場合、Firecrawlツールで以下の内容を抽出
    - タイトル
    - 投稿日
    - いいね数/参加者数
    - 本文の内容

4. 取得した技術ブログ・登壇資料の内容がAWSに関するものであった場合、以下4つのレベルのいずれかに判定してください。
    - Level 100: AWSサービスの概要を解説するレベル
      基本的な概念や用語の説明、サービスの紹介など
    - Level 200: 入門知識を前提に、ベストプラクティスやサービス機能を解説するレベル
      基本的な実装方法、標準的な使用パターンなど
    - Level 300: 対象トピックの詳細を解説するレベル
      高度な機能、パフォーマンス最適化、複雑な設定など
    - Level 400: 複数サービス・アーキテクチャによる実装を解説するレベル
      大規模システム設計、複雑な統合パターン、エンタープライズレベルの実装など

    判定時は以下の観点を考慮してください：
    - 使用されているAWSサービスの数と複雑さ
    - 技術的な深さと詳細度
    - 前提知識のレベル
    - 実装の規模と複雑さ
"""


# ToolUseを確認せず実行できるようにする
# https://strandsagents.com/latest/documentation/docs/user-guide/concepts/tools/community-tools-package/
# os.environ["BYPASS_TOOL_CONSENT"] = "true"

# ==== Firecrawl Agent Factory ======================================================
class FirecrawlAgentFactory(MCPConfig):
    """
    Firecrawl（web検索/クロール/抽出）用の Agent を、“今開いている” Firecrawl MCPセッションから構築。
    呼び出し側で必ず `with firecrawl_mcp:` の中で build() を呼ぶこと。
    """
    def __init__(self, model_id: str | None = None):
        self.model_id = model_id or os.getenv("MODEL_ID", "us.anthropic.claude-sonnet-4-20250514-v1:0")
        self.system_prompt = ACTIVITY_SEARCH_SYSTEM_PROMPT

        if not self.system_prompt:
            raise ValueError("Web検索エージェント用システムプロンプトが必要です")

    def build(self, mcp_client: MCPClient) -> Agent:
        # ★ with mcp_client: の内側で呼ぶこと
        firecrawl_tools = mcp_client.list_tools_sync()

        # 以下は複数MCPを登録した中からfirecrawlだけを抽出する処理
        # all_tools = mcp_client.list_tools_sync()
        # firecrawl / extract / crawl / search などを優先
        # firecrawl_tools = [t for t in all_tools if any(k in getattr(t, "tool_name", getattr(t, "name", "")).lower()
        #                                           for k in ("firecrawl", "extract", "crawl", "search"))] or all_tools

        agent = Agent(
            name="FirecrawlAgent",
            tools=firecrawl_tools,
            model=self.model_id,
            system_prompt=self.system_prompt,
        )

        # ログ（任意）
        try:
            tool_names = [_get_tool_name(t) for t in firecrawl_tools]
        except Exception:
            tool_names = [str(t) for t in firecrawl_tools]
        logger.info(f"FirecrawlAgent 構築: ツール数={len(firecrawl_tools)} -> {tool_names}")

        return agent

    async def stream(self, agent: Agent, prompt: str):
        # ★ with mcp_client: の内側で呼ぶこと
        async for ev in agent.stream_async(prompt):
            if ev is not None:
                yield ev