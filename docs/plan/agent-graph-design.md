# グラフ構造を用いたAIエージェント設計

## 概要

[Bedrock AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/what-is-bedrock-agentcore.html)と[Strands Agents SDK](https://strandsagents.com/latest/documentation/docs/)を組み合わせて、2つのエージェントを構築します。

### Bedrock AgentCoreとは

- 2025年に発表された最新のAWSサービス（プレビュー中）
- エンタープライズグレードのエージェント実行環境を提供
- Strands Agentsを含む複数のフレームワークをサポート
- セキュアでスケーラブルなエージェント実行基盤

### Strands Agents SDKとは

- AWSがオープンソースで公開しているPython SDK
- シンプルなコードでAIエージェントを構築可能
- Bedrock、OpenAI、Anthropic等の複数のモデルプロバイダーをサポート
- デフォルトでAmazon Bedrockを使用

## エージェントグラフ設計

- Strands Agents SDKの[Agent Graph](https://strandsagents.com/latest/documentation/docs/user-guide/concepts/multi-agent/graph/)を用いる
- 1つ目のエージェントノード：Slack検索エージェント
- 2つ目のエージェントノード：Firecrawl検索エージェント
- 3つ目のエージェントノード：AWSレベル判定エージェント
- ツールノード：メッセージ前処理ツール、Aurora DSQLデータ格納ツール、処理完了通知送信ツール、connpass API検索ツール、

### グラフの流れ

1. Slack検索エージェントノード
2. Firecrawl検索エージェントノード
3. AWSレベル判定エージェント
4. Aurora DSQLデータ格納ツール
5. 処理完了通知送信ツール

## エージェント構成

### 1. Slack検索エージェント（Slack Research Agent）

**役割**: Slackメッセージから活動情報を検索・抽出

**使用するツール**:

- Slack検索ツール（Slack MCP）
  - AgentCore Gateway/Identityを用いてツールを使用する

**処理フロー**: Slack検索ツールを用いて、対象となるスレッドからメッセージを取得する
具体的な実装については、[agent_graph.py](../agent/agent_graph.py)を参照、これがたたき台

### 2. 活動内容検索エージェント（Activity Research Agent）

**役割**: Slack検索エージェントが取得した情報を元に、検索ツールでURL検索を行う

**使用するツール**:

- Firecrawl MCP
  - 公式が提供している[Firecrawl MCP](https://github.com/firecrawl/firecrawl-mcp-server)を用いる
  - ブログや登壇資料のリンクを添付した際には、こちらのツールを用いる
- connpass API検索ツール
  - Strands Agents SDKの @tool デコレータを用いて実装
  - 詳しくは[connpass API v2](https://connpass.com/about/api/v2/)を参照して実装する
  - イベント名、開催日時、参加者数などを取得する

**処理フロー**: 2つのツールを使い分けて、対象となるリンクから情報を取得する
具体的な実装については、[agent_graph.py](../agent/agent_graph.py)を参照、これがたたき台
ただしconnpass検索ツールについては別途実装が必要

### 3. AWSレベル判定エージェント（AWS Level Judge Agent）

**役割**: AWSブログ・AWSに関する登壇のレベルを判定するエージェント

**使用するツール**:

- AWS Knowledge MCP
- AWS API MCP

**処理フロー**: 2つのツールを使い分けて、AWSに関するアウトプットのレベルを判定するとともに、中身の妥当性を判定する
やりたいことについては、[AWSレベル判定くんMCPサーバー版](https://github.com/minorun365/mcp-aws-level-checker)を参照
ただし、ここではMCPサーバーではなくエージェントとして実装する

## エージェント間の連携

### オーケストレーション

Agent Graphを用いて、毎回必ず同じ順番で実行するようにオーケストレートする。
詳しくは[Agent Graph](https://strandsagents.com/latest/documentation/docs/user-guide/concepts/multi-agent/graph/)を参照しながら実装する。

```python
from strands import Agent

# 別途MCPなどの設定を行う

@tool
def connpass_search_tool():
    """connpass APIツール"""
    return ...

class PutDataTool(MultiAgentBase):
    """Aurora DSQLへのデータ格納ツール"""
    def __init__(self, func, name: str = None):
        super().__init__()
        self.func = func
        self.name = name or func.__name__

    def __call__(self, task, **kwargs: Any) -> MultiAgentResult:
        if isinstance(task, str):
            query = task
        elif isinstance(task, list):
            query = task[-1]["text"]
        
        """Aurora DSQLへのデータ格納処理"""

        return MultiAgentResult(
            status=Status.COMPLETED,
            results={
                self.name: NodeResult(
                    result=AgentResult(
                        stop_reason="end_turn",
                        message=Message(
                            role="assistant",
                            content=[{"text": json.dumps("""データ格納結果などを設定？""")}],
                        ),
                        metrics=EventLoopMetrics(),
                        state=None,
                    )
                )
            },
        )

    async def invoke_async(self, task, **kwargs):
        return self.__call__(task, **kwargs)

class SendResultTool(MultiAgentBase):
    """グラフ処理完了の通知ツール"""
    def __init__(self, func, name: str = None):
        super().__init__()
        self.func = func
        self.name = name or func.__name__

    def __call__(self, task, **kwargs: Any) -> MultiAgentResult:
        if isinstance(task, str):
            query = task
        elif isinstance(task, list):
            query = task[-1]["text"]
        
        """SNSでのGraph実行結果送信処理実行ツール"""

        return MultiAgentResult(
            status=Status.COMPLETED,
            results={
                self.name: NodeResult(
                    result=AgentResult(
                        stop_reason="end_turn",
                        message=Message(
                            role="assistant",
                            content=[{"text": json.dumps("""実行結果などを返却？""")}],
                        ),
                        metrics=EventLoopMetrics(),
                        state=None,
                    )
                )
            },
        )

    async def invoke_async(self, task, **kwargs):
        return self.__call__(task, **kwargs)

slack_research_agent = Agent(
    """toolsにslack検索ツール"""
)

activity_search_agent = Agent(
    tools=connpass_search_tool # Firecrawl MCPツールも設定
)

level_judge_agent = Agent(
    """toolsに2つのMCPサーバー"""
)

put_data_tool = PutDataTool("put_data_tool")
send_result_tool = SendResultTool("send_result_tool")

# Agent Graphを構築していく
builder = GraphBuilder()

builder.add_node(slack_research_agent, "slack-agent")
builder.add_node(activity_search_agent, "activity-agent")
builder.add_node(level_judge_agent, "judge-agent")
builder.add_node(put_data_tool, "db-tool")
builder.add_node(send_result_tool, "sns-tool")

builder.set_entry_point("slack")

graph = builder.build()

result = graph("アウトプットを調査して")
```

## 設計上の考慮事項

### 1. エラーハンドリング

- 各エージェントで適切なリトライ処理
- 失敗時のログ記録とアラート
- 部分的な成功の処理

### 2. パフォーマンス

- 並列処理可能な部分は並列実行
- キャッシュの活用（同じURLの重複取得を避ける）
- バッチ処理での効率化

### 3. セキュリティ

- Slack Token, Firecrawl API KeyはAgentCore IdentityとSecrets Managerで管理
- DB接続情報は環境変数で注入
- 最小権限の原則に従ったIAMロール

### 4. 監視とデバッグ

- AgentCore Observabilityでエージェントの動作を監視
- CloudWatch Logsで詳細ログ
- X-Rayでトレーシング
- 別途Langfuseも導入

## 次のステップ

1. 各ツールの詳細実装
   - Slack MCPとFirecrawl MCPの統合
   - カスタムツールの実装
2. エージェントのテスト戦略
   - ユニットテスト（各ツールの動作確認）
   - 統合テスト（グラフ全体の動作）
3. インフラのTerraform実装
   - 参考: [Amazon Bedrock AgentCoreのランタイムをAWS CodePipelineで安全に更新するためのパイプラインをTerraformで構築する](https://qiita.com/neruneruo/items/572e3007e5376cc08613)
4. 運用ドキュメントの作成
