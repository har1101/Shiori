"""
データ格納と通知送信のカスタムツールノード
"""

import json
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime
from strands.multiagent.base import MultiAgentBase, NodeResult, Status, MultiAgentResult
from strands.agent.agent_result import AgentResult
from strands.types.content import Message
from strands.telemetry.metrics import EventLoopMetrics

# データアクセス層のインポート
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data_access import dsql_client

logger = logging.getLogger(__name__)

class PutDataTool(MultiAgentBase):
    """Aurora DSQLへのデータ格納ツール"""
    
    def __init__(self, name: str = "put_data_tool"):
        super().__init__()
        self.name = name
        logger.info(f"PutDataTool initialized: {name}")
    
    def __call__(self, task, **kwargs: Any) -> MultiAgentResult:
        """
        Aurora DSQLへデータを格納
        
        Args:
            task: 前のノードからの入力（活動情報）
        
        Returns:
            MultiAgentResult: 格納結果
        """
        try:
            # タスクから情報を抽出
            if isinstance(task, str):
                query = task
            elif isinstance(task, list):
                query = task[-1].get("text", "") if task else ""
            else:
                query = str(task)
            
            logger.info(f"PutDataTool processing: {query[:100]}...")
            
            # TODO: 実際のデータ解析と格納処理
            # 現時点では仮実装
            result_message = self._store_activity_data(query)
            
            # AgentResult形式でラップ
            agent_result = AgentResult(
                stop_reason="end_turn",
                message=Message(
                    role="assistant",
                    content=[{"text": result_message}],
                ),
                metrics=EventLoopMetrics(),
                state=None,
            )
            
            # MultiAgentResultとして返却
            return MultiAgentResult(
                status=Status.COMPLETED,
                results={
                    self.name: NodeResult(
                        result=agent_result,
                        execution_time=0,
                        status=Status.COMPLETED
                    )
                },
            )
            
        except Exception as e:
            logger.error(f"PutDataTool error: {e}")
            
            # エラー時のAgentResult
            error_result = AgentResult(
                stop_reason="end_turn",
                message=Message(
                    role="assistant",
                    content=[{"text": f"データ格納エラー: {str(e)}"}],
                ),
                metrics=EventLoopMetrics(),
                state=None,
            )
            
            return MultiAgentResult(
                status=Status.FAILED,
                results={
                    self.name: NodeResult(
                        result=error_result,
                        execution_time=0,
                        status=Status.FAILED
                    )
                },
            )
    
    def _store_activity_data(self, data: str) -> str:
        """
        活動データを解析してDSQLに格納
        
        Args:
            data: 活動情報を含む文字列
        
        Returns:
            格納結果メッセージ
        """
        try:
            # TODO: データの解析処理
            # 現時点では仮のデータで格納テスト
            
            # メンバー取得または作成（関数として呼び出し）
            member_id = dsql_client.get_or_create_member(
                email="test@example.com",
                name="テストユーザー",
                github_username="test_user"
            )
            
            # 活動データの格納（仮データ）
            activity_data = {
                "member_id": member_id,
                "activity_type": "article",
                "title": "テスト記事",
                "description": "これはテスト用の記事です",
                "activity_date": datetime.now().date(),
                "blog_url": "https://example.com/article",
                "aws_level": "200"
            }
            
            result = dsql_client.store_activity(**activity_data)
            activity_id = result.get("activity_id", "unknown")
            
            # 処理履歴の記録
            dsql_client.record_processing(
                process_type="slack_fetch",
                status="success"
            )
            
            return f"✅ データ格納成功\n- メンバーID: {member_id}\n- 活動ID: {activity_id}"
            
        except Exception as e:
            logger.error(f"Data storage error: {e}")
            
            # エラー時も処理履歴を記録
            try:
                dsql_client.record_processing(
                    process_type="slack_fetch",
                    status="failed",
                    error_message=str(e)
                )
            except:
                pass
            
            raise
    
    async def invoke_async(self, task, **kwargs):
        """非同期実行のラッパー"""
        return self.__call__(task, **kwargs)


class SendResultTool(MultiAgentBase):
    """処理完了通知送信ツール"""
    
    def __init__(self, name: str = "send_result_tool"):
        super().__init__()
        self.name = name
        logger.info(f"SendResultTool initialized: {name}")
    
    def __call__(self, task, **kwargs: Any) -> MultiAgentResult:
        """
        処理結果の通知を送信
        
        Args:
            task: 前のノードからの処理結果
        
        Returns:
            MultiAgentResult: 送信結果
        """
        try:
            # タスクから情報を抽出
            if isinstance(task, str):
                query = task
            elif isinstance(task, list):
                query = task[-1].get("text", "") if task else ""
            else:
                query = str(task)
            
            logger.info(f"SendResultTool processing: {query[:100]}...")
            
            # TODO: 実際の通知送信処理（SNS経由）
            # 現時点では仮実装
            result_message = self._send_notification(query)
            
            # AgentResult形式でラップ
            agent_result = AgentResult(
                stop_reason="end_turn",
                message=Message(
                    role="assistant",
                    content=[{"text": result_message}],
                ),
                metrics=EventLoopMetrics(),
                state=None,
            )
            
            # MultiAgentResultとして返却
            return MultiAgentResult(
                status=Status.COMPLETED,
                results={
                    self.name: NodeResult(
                        result=agent_result,
                        execution_time=0,
                        status=Status.COMPLETED
                    )
                },
            )
            
        except Exception as e:
            logger.error(f"SendResultTool error: {e}")
            
            # エラー時のAgentResult
            error_result = AgentResult(
                stop_reason="end_turn",
                message=Message(
                    role="assistant",
                    content=[{"text": f"通知送信エラー: {str(e)}"}],
                ),
                metrics=EventLoopMetrics(),
                state=None,
            )
            
            return MultiAgentResult(
                status=Status.FAILED,
                results={
                    self.name: NodeResult(
                        result=error_result,
                        execution_time=0,
                        status=Status.FAILED
                    )
                },
            )
    
    def _send_notification(self, data: str) -> str:
        """
        通知を送信（SNS経由）
        
        Args:
            data: 通知内容
        
        Returns:
            送信結果メッセージ
        """
        try:
            # TODO: 実際のSNS送信処理
            # 現時点ではログ出力のみ
            
            notification_summary = {
                "timestamp": datetime.now().isoformat(),
                "status": "completed",
                "message": "Jr.Champions活動記録の処理が完了しました",
                "details": data[:200] if len(data) > 200 else data
            }
            
            logger.info(f"Notification would be sent: {json.dumps(notification_summary, ensure_ascii=False)}")
            
            return f"📨 通知送信完了\n{json.dumps(notification_summary, ensure_ascii=False, indent=2)}"
            
        except Exception as e:
            logger.error(f"Notification send error: {e}")
            raise
    
    async def invoke_async(self, task, **kwargs):
        """非同期実行のラッパー"""
        return self.__call__(task, **kwargs)
