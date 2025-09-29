from strands import Agent, tool
from strands.tools.mcp import MCPClient
import logging
from boto3.session import Session
from typing import Any, List

from agents.config.gateway_identity_config import _get_tool_name
from agents.config.remote_mcp_config import RemoteMCPConfig
from agents.config.local_mcp_config import LocalMCPConfig

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
あなたは活動内容分析アシスタントです。指定URLの内容を評価し、Aurora DSQL `output_history` スキーマのテーブル構成（sql/create_tables_output_history.sql）に合わせた構造化データを生成してください。

1. 活動種別の判定 / Activity Type Classification
   - presentation: 登壇・勉強会・講演・ハンズオンなどの発表系アウトプット
   - article: ブログ記事・技術解説・資料公開
   - other: 上記に当てはまらないが記録すべき技術アウトプット

2. URL
   - `firecrawl` 系ツールで `title`、`activity_date`(公開日や実施日)、本文からの `description`(100-200文字)、`summary_by_ai`(詳細な要約) を抽出。
   - いいね数や閲覧数がわかる場合は `like_count` として整数で保存。

3. AWS技術レベルの判定 / AWS Proficiency Level
   - Level 100: サービス概要レベル
   - Level 200: ベストプラクティスや基本実装
   - Level 300: 詳細設計・高度な最適化
   - Level 400: 大規模・複合アーキテクチャの実装
   - AWSと無関係な場合は `aws_level` を省略し、`aws_services` も空にする。

4. Aurora DSQL への保存 / Persisting to Aurora DSQL
   - 構造化が完了したら `aurora_dsql_activity_tool` を1回呼び、以下のオブジェクトを渡す。

   * member オブジェクト / Member Object
     - `slack_user_id` (必須): SlackユーザーID (`U123ABC` 形式)
     - `slack_user_name` (任意): 表示名
     - `slack_user_email` (任意): メールアドレスが取得できる場合

   * activity オブジェクト / Activity Object
     - 必須 / Required: 
       - `title`: 抽出したタイトル
       - `activity_date`: `YYYY-MM-DD` 形式の日付 (Slackの `YYYYMMDD` や ISO8601 から変換)
       - `activity_type`: `presentation` / `article` / `other`
       - `url`: 元のコンテンツURL
       - `slack_user_id`: `member` と同じSlackユーザーID
     - 任意 / Optional:
       - `description`: 100-200文字の要約
       - `summary_by_ai`: AIによる詳細要約
       - `event_name`: connpass等のイベント名
       - `participant_count`, `like_count`: 整数で保存 (取得できない場合は省略)
       - `aws_services`: AWSサービス名のリスト（例: `["Amazon S3", "AWS Lambda"]`）
       - `aws_level`: `"100"|"200"|"300"|"400"` の文字列 (AWS関連時のみ)
       - `tags`: 技術タグのリスト
       - `slack_channel`: SlackチャンネルID (例: `C123ABC`)
       - `slack_message_id`: Slackメッセージの文字列ID (`ts` 等)
       - `slack_upload_time`: Slack投稿日時を `YYYYMMDD` で表現した文字列

   * track_processing オブジェクト (任意) / Optional track_processing
     - `status` は `success` / `failed` / `in_progress` のいずれか。`details` は辞書形式で渡す。

6. 重複防止 / Duplicate Prevention
   - SlackメッセージIDがない場合はURLと投稿日で整合性を保ち、同一データの再登録を避ける。
"""

ALLOWED_ACTIVITY_TYPES = {"presentation", "article", "other"}
AWS_LEVEL_CODES = {"100", "200", "300", "400"}
PROCESS_TYPES = {"slack_fetch", "daily_collection", "report_generation", "monthly_report"}
PROCESS_STATUSES = {"success", "failed", "in_progress"}


# ToolUseを確認せず実行できるようにする
# https://strandsagents.com/latest/documentation/docs/user-guide/concepts/tools/community-tools-package/
# os.environ["BYPASS_TOOL_CONSENT"] = "true"

# ==== Firecrawl Agent Factory ======================================================
class FirecrawlAgentFactory(RemoteMCPConfig, LocalMCPConfig):
    """
    Firecrawl（web検索/クロール/抽出）用の Agent を、“今開いている” Firecrawl MCPセッションから構築。
    呼び出し側で必ず `with firecrawl_mcp:` の中で build() を呼ぶこと。
    """
    def __init__(self, model_id: str):
        self.model_id = model_id
        self.system_prompt = ACTIVITY_SEARCH_SYSTEM_PROMPT

        if not self.system_prompt:
            raise ValueError("Web検索エージェント用システムプロンプトが必要です")

    def build(self, remote_mcp_client: MCPClient, local_mcp_client: MCPClient) -> Agent:
        # ★ with mcp_client: の内側で呼ぶこと
        firecrawl_tools = list(remote_mcp_client.list_tools_sync())
        dsql_tools = list(local_mcp_client.list_tools_sync())

        agent_tools: List[Any] = [*firecrawl_tools, *dsql_tools]

        agent = Agent(
            name="FirecrawlAgent",
            tools=agent_tools,
            model=self.model_id,
            system_prompt=self.system_prompt,
        )

        # ログ（任意）
        try:
            tool_names = [_get_tool_name(t) for t in agent_tools]
        except Exception:
            tool_names = [str(t) for t in agent_tools]
        logger.info(f"FirecrawlAgent 構築: ツール数={len(agent_tools)} -> {tool_names}")

        return agent

    async def stream(self, agent: Agent, prompt: str):
        # ★ with mcp_client: の内側で呼ぶこと
        async for ev in agent.stream_async(prompt):
            if ev is not None:
                yield ev
