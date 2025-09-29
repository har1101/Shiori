from strands import Agent
from strands.tools.mcp import MCPClient
import logging
from boto3.session import Session
import os

from agents.config.gateway_identity_config import _get_tool_name
from agents.config.mcp_config import MCPConfig

logger = logging.getLogger("aws_level_judge_agent")
logger.setLevel(logging.INFO)
logging.basicConfig(
    format="%(levelname)s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler()]
)

boto_session = Session()
region = boto_session.region_name

# システムプロンプト
AWS_LEVEL_JUDGE_SYSTEM_PROMPT = """
あなたはAWS技術レベル判定アシスタントです。
提供されたコンテンツを分析し、以下の4つのレベルのいずれかに判定してください：

- Level 100: AWSサービスの概要を解説するレベル
  基本的な概念や用語の説明、サービスの紹介など

- Level 200: 入門知識を前提に、ベストプラクティスやサービス機能を解説するレベル
  基本的な実装方法、標準的な使用パターンなど

- Level 300: 対象トピックの詳細を解説するレベル
  高度な機能、パフォーマンス最適化、複雑な設定など

- Level 400: 複数サービス・アーキテクチャによる実装を解説するレベル
  大規模システム設計、複雑な統合パターン、エンタープライズレベルの実装など

判定時は以下の観点を考慮してください：
1. 使用されているAWSサービスの数と複雑さ
2. 技術的な深さと詳細度
3. 前提知識のレベル
4. 実装の規模と複雑さ

出力形式：
レベル: [100/200/300/400]
判定理由: [詳細な判定理由]
"""

# ==== AWS Level Judge Agent Factory ======================================================
class AwsLevelJudgeAgentFactory(MCPConfig):
    """
    アウトプットに関するAWSレベル判定用Agentを構築する
    """
    def __init__(self, model_id: str | None = None):
        self.model_id = model_id or os.getenv("MODEL_ID", "us.anthropic.claude-sonnet-4-20250514-v1:0")
        self.system_prompt = AWS_LEVEL_JUDGE_SYSTEM_PROMPT

        if not self.system_prompt:
            raise ValueError("AWSレベル判定エージェント用システムプロンプトが必要です")

    def build(self, mcp_client: MCPClient) -> Agent:
        # 1) ツール定義
        # AWS Knowledge MCPを使う想定だったが、なくても良いかも
        # judge_tools = mcp_client.list_tools_sync()

        # 2) Agent定義
        agent = Agent(
            name="AwsLevelJudgeAgent",
            #tools=judge_tools,
            model=self.model_id,
            system_prompt=self.system_prompt,
        )

        # ログ（任意）
        # try:
        #     tool_names = [_get_tool_name(t) for t in judge_tools]
        # except Exception:
        #     tool_names = [str(t) for t in judge_tools]
        # logger.info(f"AwsLevelJudgeAgent 構築: ツール数={len(judge_tools)} -> {tool_names}")

        return agent

    async def stream(self, agent: Agent, prompt: str):
        # with mcp_client: の内側で呼ぶこと。
        async for ev in agent.stream_async(prompt):
            if ev is not None:
                yield ev