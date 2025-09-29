"""
Jr.Champions活動記録システム - Agent Graph実装 v2
設計書に基づいた3エージェント + 2ツールノードの構成

エージェント構成:
1. Slack検索エージェント - Slackからメッセージ取得
2. 活動内容検索エージェント - URLから詳細情報取得（Firecrawl + connpass）
3. AWSレベル判定エージェント - AWS技術レベル判定
4. データ格納ツール - Aurora DSQLへの保存
5. 通知送信ツール - SNS経由での通知
"""
import logging, os
import json
import boto3
import base64
from typing import Any, Dict, List
from strands import Agent
from strands.multiagent import GraphBuilder
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from strands.telemetry import StrandsTelemetry
from boto3.session import Session


# ツールのインポート
from agents.config.gateway_identity_config import GatewayIdentityConfig, parse_prompt_from_payload, always_false_condition, extract_message_content, detect_mcp_usage
from agents.config.remote_mcp_config import RemoteMCPConfig
from agents.config.local_mcp_config import LocalMCPConfig
from agents.slack_agent_factory import SlackAgentFactory
from agents.web_agent_factory import FirecrawlAgentFactory
from langfuse import get_client

# ロガー設定
logger = logging.getLogger("shiori_agent_graph")
logger.setLevel(logging.INFO)
logging.basicConfig(
    format="%(levelname)s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler()]
)

_boto_session = Session()
region = _boto_session.region_name

# ========== Langfuse setup ==========
langfuse_public_key_public_id = os.environ["LANGFUSE_PUBLIC_KEY_SECRET_ID"]
langfuse_public_key_secret_id = os.environ["LANGFUSE_SECRET_KEY_SECRET_ID"]

# Secrets ManagerからLangfuseのキーを取得
# 期待するデータ格納形式:
# - SecretId: "langfuse-public-key" → JSON形式 {"api_key_value":"実際のキー値"}
# - SecretId: "langfuse-secret-key" → JSON形式 {"api_key_value":"実際のキー値"}
secrets_manager = boto3.client("secretsmanager", region_name="us-east-1")

# Langfuse Public Keyを取得（JSON形式 {"api_key_value":"実際のキー値"} から取得）
public_secret = secrets_manager.get_secret_value(SecretId=langfuse_public_key_public_id)
public_data = json.loads(public_secret["SecretString"])
os.environ["LANGFUSE_PUBLIC_KEY"] = public_data["api_key_value"]
print(f"Langfuse パブリックキーを取得: {public_data['api_key_value'][:4]}...{public_data['api_key_value'][-4:]}:")

# Langfuse Secret Keyを取得（JSON形式 {"api_key_value":"実際のキー値"} から取得）
secret_key_secret = secrets_manager.get_secret_value(SecretId=langfuse_public_key_secret_id)
secret_data = json.loads(secret_key_secret["SecretString"])
os.environ["LANGFUSE_SECRET_KEY"] = secret_data["api_key_value"]
print(f"Langfuse シークレットキーを取得: {secret_data['api_key_value'][:4]}...{secret_data['api_key_value'][-4:]}:")

LANGFUSE_AUTH = base64.b64encode(
    f"{os.environ['LANGFUSE_PUBLIC_KEY']}:{os.environ['LANGFUSE_SECRET_KEY']}".encode()
).decode()

os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = (
    os.environ.get("LANGFUSE_HOST", "https://us.cloud.langfuse.com") + "/api/public/otel"
)

os.environ["OTEL_EXPORTER_OTLP_HEADERS"] = f"Authorization=Basic {LANGFUSE_AUTH}"

# os.environ["LANGFUSE_DEBUG"] = "True"

os.environ["OTEL_TRACES_EXPORTER"] = "otlp"

os.environ["OTEL_EXPORTER_OTLP_PROTOCOL"] = "http/protobuf"

strands_telemetry = StrandsTelemetry().setup_otlp_exporter()
langfuse = get_client()
# ========== Langfuse setup ==========

# AgentCoreアプリケーションを初期化
app = BedrockAgentCoreApp()

@app.entrypoint
async def invoke_agent_graph(payload: Dict[str, Any]):
    """Agent Graphのメインエントリーポイント
    
    Args:
        payload: AgentCore Runtimeから渡されるペイロード
                - prompt: ユーザーからの入力メッセージ
    
    Yields:
        AgentCore Runtime形式のストリーミングレスポンス
    """
    # プロンプトの検証とペイロード構造の処理
    user_message = parse_prompt_from_payload(payload)
    if not user_message:
        logger.error(f"無効なペイロード構造: {payload}")
        yield {"error": "無効なペイロード: 'prompt'フィールドが必要です"}
        return

    try:
        # MCPクライアントとツールを作成
        logger.info("🚀 MCPクライアント作成を開始...")

        # AgentCore Gatewayを用いたMCPのセッションを開く
        gateway_config = GatewayIdentityConfig()
        gateway_mcp = await gateway_config.create_mcp_client_and_tools()

        # Firecrawl MCPのセッション(SSE)を開く
        sse_config = RemoteMCPConfig(
            provider_name="firecrawl_api_key",
            base_url="https://mcp.firecrawl.dev",
            http_path_template=None,
            sse_path_template="/{API_KEY}/v2/sse"
        )
        sse_mcp = await sse_config.build_client()

        # Aurora DSQLのセッションを開く
        dsql_config = LocalMCPConfig()
        dsql_mcp = await dsql_config.build_client()

        # MCPのwithコンテキスト内でGraph全体を実行
        logger.info("📦 MCPコンテキストを開始（セッション維持）...")
        # AWS Knowledge MCPを用いる場合は、withにstreamable_http_mcpを追加する
        with gateway_mcp, sse_mcp, dsql_mcp:
            logger.info("✅ MCPコンテキストに入りました - セッションアクティブ")

            slack_agent = SlackAgentFactory(
                model_id=os.environ.get("SLACK_AGENT_MODEL_ID", "us.anthropic.claude-sonnet-4-5-20250929-v1:0"),
                slack_channel=os.environ.get("SLACK_CHANNEL", "")
            ).build(gateway_mcp)

            firecrawl_agent = FirecrawlAgentFactory(
                model_id=os.environ.get("FIRECRAWL_AGENT_MODEL_ID", "us.anthropic.claude-sonnet-4-5-20250929-v1:0"),
            ).build(sse_mcp, dsql_mcp)

            block_agent = Agent()

            # Graphを作成していく
            builder = GraphBuilder()

            # ノードを追加
            builder.add_node(slack_agent, "slack_agent")
            builder.add_node(firecrawl_agent, "firecrawl_agent")
            builder.add_node(block_agent, "block_agent")

            # エッジを追加
            builder.add_edge("slack_agent", "firecrawl_agent")

            # firecrawl_agentの後に条件付きエッジを追加（常にFalseで終了）
            # これによりfirecrawl_agentの後でグラフが確実に終了する
            builder.add_edge("firecrawl_agent", "block_agent", condition=always_false_condition)

            # エントリーポイントの設定
            builder.set_entry_point("slack_agent")

            # Graphをビルドする
            graph = builder.build()

            # ユーザーメッセージはすでに取得済み
            logger.info(f"ユーザーメッセージ: {user_message}")

            # MCPコンテキスト内で処理を実行
            logger.info("🎯 MCPコンテキスト内でエージェント処理を開始...")

            # Graph.invoke_async()を使用して非同期実行
            try:
                # 非同期実行でGraphを実行
                logger.info("🚀 Graph.invoke_async()を開始...")
                graph_result = graph(user_message)

                # 結果の処理（graph_with_tool_response_format.mdに基づく改善版）
                logger.info("🔍 Graph実行結果を処理中...")
                from strands.multiagent.base import Status

                # 構造化されたレスポンスを作成
                structured_response = {
                    "status": "completed" if graph_result.status == Status.COMPLETED else "failed",
                    "agents": [],
                    "total_execution_time_ms": getattr(graph_result, "execution_time", 0),
                    "total_tokens": graph_result.accumulated_usage.get("totalTokens", 0) if hasattr(graph_result, "accumulated_usage") else 0,
                    "mcp_tools_used": False,
                    "full_text": "",  # フロントエンド表示用の統合テキスト
                    "metadata": {
                        "session_id": payload.get("sessionId", "unknown"),
                        "total_nodes": getattr(graph_result, "total_nodes", 0),
                        "completed_nodes": getattr(graph_result, "completed_nodes", 0),
                        "failed_nodes": getattr(graph_result, "failed_nodes", 0)
                    }
                }

                all_texts = []
                logger.info(f"📊 Graph全体ステータス: {structured_response['status']}")

                # 各ノードの結果を処理
                for node_name, node_result in graph_result.results.items():
                    node_data = {
                        "name": node_name,
                        "messages": [],
                        "execution_time_ms": getattr(node_result, "execution_time", 0),
                        "status": str(getattr(node_result, "status", "unknown")),
                        "tokens_used": node_result.accumulated_usage.get("totalTokens", 0) if hasattr(node_result, "accumulated_usage") else 0
                    }

                    # NodeResult.get_agent_results() で入れ子もフラットに
                    for agent_result in node_result.get_agent_results():
                        text, jsons = extract_message_content(agent_result)

                        if text:
                            node_data["messages"].append({
                                "type": "text",
                                "content": text
                            })
                            all_texts.append(f"[{node_name}] {text}")

                            # MCPツール使用を検出
                            if detect_mcp_usage(text):
                                structured_response["mcp_tools_used"] = True

                        if jsons:
                            node_data["messages"].append({
                                "type": "json",
                                "content": jsons
                            })

                        # ログ出力
                        logger.info(
                            f"📦 Node: {node_name} | status={node_data['status']} | "
                            f"stop_reason={getattr(agent_result,'stop_reason',None)}"
                        )

                    structured_response["agents"].append(node_data)

                # 全体の統合テキストを作成
                structured_response["full_text"] = "\n\n".join(all_texts) if all_texts else "レスポンスが空でした"

                # 結果をログ出力
                logger.info(f"✅ 最終レスポンス準備完了: {len(structured_response['full_text'])} 文字")
                logger.info(f"📊 MCPツール使用: {structured_response['mcp_tools_used']}")
                logger.info(f"⏱️ 総実行時間: {structured_response['total_execution_time_ms']}ms")
                logger.info(f"🎯 トークン使用量: {structured_response['total_tokens']}")

                # Langfuse SDK でテレメトリー送信
                langfuse.flush()

                # 構造化されたレスポンスをJSON形式で返す
                yield json.dumps(structured_response, ensure_ascii=False)

            except Exception as graph_error:
                logger.error(f"Graph実行中にエラーが発生: {graph_error}")
                # エラーの詳細をログ出力
                import traceback
                logger.error(f"スタックトレース: {traceback.format_exc()}")

                # エラーレスポンスを返す
                yield {
                    "type": "error",
                    "error": f"Graph実行エラー: {str(graph_error)}"
                }
                return

            logger.info("🎉 Graph処理完了 - MCPセッションを正常にクローズします")

    except RuntimeError as e:
        # create_agentからのエラー
        logger.error(f"❌ エージェント作成エラー: {e}")
        yield {"error": str(e)}
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"❌ 処理中にエラーが発生: {e}")
        logger.error(f"📊 詳細なスタックトレース:\n{error_trace}")

        # エラーメッセージ
        error_msg = str(e)
        if "connection" in error_msg.lower() or "mcp" in error_msg.lower():
            yield {"error": f"MCP接続エラー: {error_msg}. MCPクライアントのセッションが切れている可能性があります。"}
        elif "tool" in error_msg.lower():
            yield {"error": f"ツール実行エラー: {error_msg}. ツールの利用権限またはパラメータを確認してください。"}
        else:
            yield {"error": f"リクエストの処理中にエラーが発生しました: {error_msg}"}

if __name__ == "__main__":
    # Slackツール連携エージェントサーバーを起動
    # デフォルトでポート8080でリッスンします
    app.run()
