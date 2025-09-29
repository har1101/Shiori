from strands import Agent
from strands.tools.mcp import MCPClient
from strands_tools.code_interpreter import AgentCoreCodeInterpreter
import logging
from boto3.session import Session
import os

from agents.config.gateway_identity_config import GatewayIdentityConfig, _filter_tools_by_keyword, _get_tool_name

logger = logging.getLogger("agent_graph")
logger.setLevel(logging.INFO)
logging.basicConfig(
    format="%(levelname)s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler()]
)

boto_session = Session()
region = boto_session.region_name
# interpreter = AgentCoreCodeInterpreter(region=region)

SLACK_SEARCH_SYSTEM_PROMPT = """
あなたはSlack統合アシスタントです。

<前提>
- 対象チャンネルID: {SLACK_CHANNEL}
- 使用可能ツール: slack___conversationsHistory, slack___usersList
- 目的: 技術アウトプット（ブログ・登壇資料・技術イベント等）のリンクとメタ情報を収集する
</前提>

<作業手順>
1) slack___conversationsHistory を1回だけ実行し、channel="{SLACK_CHANNEL}" のメッセージ履歴を取得する。
   - ページネーションは禁止。**cursor/next を使わず最初のページだけ**取得する（例: limit=100 を明示指定）。
   - メッセージごとに URL を抽出し、該当がなければスキップ。
2) 投稿者の Slack ユーザーID（例: "Uxxxx"）を控え、slack___usersList で対応するユーザーの
   表示名とメールアドレス（取得できる場合のみ）を得る。
3) Slackの ts（または UNIX epoch）を **LLM内の推論で** 日本時間(JST)の日付文字列 "YYYYMMDD" に変換する（秒未満は不要・追加ツールは使用しない）。
</作業手順>

<収集対象の基準>
- 収集する: 技術ブログ/登壇資料/技術イベントのURL（例: Qiita, Zenn, SpeakerDeck, connpass など）
- 原則除外: X(Twitter)等の雑多なポスト、技術的アウトプットと無関係なURL
- 記事の要約や感想は不要。純粋に情報収集に集中する。

<出力仕様(JSONL)>
- 各行が1レコードの JSON。フィールドは以下:
  - "user_id": 文字列（例 "U123ABC"）
  - "user_name": 文字列（取得できない場合は null）
  - "user_email": 文字列 or null
  - "url": 文字列（抽出したアウトプットURL）
  - "slack_upload_time": 文字列（"YYYYMMDD"）
  - "slack_channel": 文字列（常に "{SLACK_CHANNEL}" を入れる）
- 例:
  {{"user_id":"U123ABC","user_name":"alice","user_email":null,"url":"https://qiita.com/...","slack_upload_time":"20250916","slack_channel":"{SLACK_CHANNEL}"}}

<ツール使用の明示指示>
- 履歴取得: slack___conversationsHistory(channel="{SLACK_CHANNEL}", limit を明示指定し、cursor は**使用しない**)
- ユーザー解決: slack___usersList() の結果から対象ユーザーIDの情報を引く
- 変換処理: **追加ツールを使わず** LLM内で JST に変換し、"YYYYMMDD" へ整形
  - タイムゾーンは Asia/Tokyo を用いる

<出力上の注意>
- JSONL のみを出力。前置き・後置きの説明文は不要。
- 1メッセージに複数URLがあれば、それぞれ別レコードとして出力。
"""

# ==== Slack Agent Factory ======================================================
# 最終的にはこのAgentを使うのではなく、Agentをベースにしたカスタムノード(nodes/slack_agent_node.py)をGraphに登録する
class SlackAgentFactory(GatewayIdentityConfig):
    """
    Slack向けAgentのビルダー。
    - MCPセッションの 'with mcp_client:' は呼び出し側で保持する（重要）
    - build(...) は *必ず with の中* で呼ぶこと（ツール列挙もその場のセッションで実施）
    """

    def __init__(
            self,
            model_id: str | None = None,
            slack_channel: str | None = None
        ):
        super().__init__()
        self.model_id = model_id
        if not model_id:
            raise ValueError("環境変数にLLM_MODEL_IDを設定してください")

        self.system_prompt = SLACK_SEARCH_SYSTEM_PROMPT
        if not self.system_prompt:
            raise ValueError("Slackエージェント用システムプロンプトが必要です")
        
        self.slack_channel = slack_channel
        if not self.slack_channel:
            raise ValueError("環境変数にSlackチャンネルIDを設定してください")
    
    def _render_prompt(self) -> str:
        """環境変数に設定したSLACK_CHANNELをシステムプロンプトに埋め込む"""
        return self.system_prompt.format(SLACK_CHANNEL=self.slack_channel)

    def build(self, mcp_client: MCPClient) -> Agent:
        """
        with mcp_client: の内側で呼び出すこと。
        MCPツールを列挙し、Slack系のみを選り分けて Agent を生成して返す。
        """
        # 1) 現在のセッションでツール列挙（← これが with の内側必須）
        tools = self.get_full_tools_list(mcp_client)

        # 2) Slack系ツールに絞る（無ければ全部使う）
        slack_tools = _filter_tools_by_keyword(tools, "slack") or tools

        # 2-1) さらに使用可能なSlackツールを指定名で絞り込み
        allowed_slack_tool_names = {
            "slack___conversationsHistory",
            "slack___usersList",
        }
        try:
            slack_selected_tools = [
                t for t in slack_tools if _get_tool_name(t) in allowed_slack_tool_names
            ]
        except Exception:
            # 取得に失敗した場合は名前文字列比較を避けてそのまま使用
            raise ValueError("Slackツールの列挙に失敗しました。")

        # 2-2) 最終的なエージェント使用可能ツール
        agent_tools = slack_selected_tools # + [interpreter.code_interpreter]

        # 3) Agent生成
        agent = Agent(
            name="SlackAgent",
            # 指定名で抽出したツールのみを利用
            tools=agent_tools,
            model=self.model_id,
            system_prompt=self._render_prompt(),
        )

        # ログ（任意）
        try:
            tool_names = [_get_tool_name(t) for t in agent_tools]
        except Exception:
            tool_names = [str(t) for t in agent_tools]
        logger.info(
            f"SlackAgent 構築: ツール数={len(agent_tools)} -> {tool_names}"
        )

        return agent

    async def stream(self, agent: Agent, prompt: str):
        """with mcp_client: の内側で呼ぶこと。"""
        async for ev in agent.stream_async(prompt):
            if ev is not None:
                yield ev
