"""
Aurora DSQL データアクセス層
Agent Graphのツールとして使用されるデータ格納関数

このモジュールは、Agent Graph内で収集されたデータを
Aurora DSQLに格納するための最小限の関数を提供します。
"""

import os
import hashlib
import logging
from typing import Dict, Optional, Any
from datetime import date
import boto3
import psycopg2
from psycopg2.extras import RealDictCursor
import json
from botocore.exceptions import ClientError

# ロギング設定
logger = logging.getLogger(__name__)

# 環境変数から設定を読み込み
DSQL_ENDPOINT = os.environ.get('DSQL_ENDPOINT', '')
# Aurora DSQLは単一のpostgresデータベースのみサポート
DB_NAME = 'postgres'  # Aurora DSQLでは固定値
AWS_REGION = os.environ.get('AWS_REGION', 'us-east-1')


def get_connection():
    """
    Aurora DSQLへの接続を取得
    IAMトークン認証を使用
    
    注意: agent_graphロールを使用（アプリケーション接続用）
    adminロールはDDL操作・管理タスク専用
    """
    try:
        # IAMトークン生成（agent_graph用）
        dsql_client = boto3.client('dsql', region_name=AWS_REGION)
        auth_token = dsql_client.generate_db_connect_auth_token(
            Hostname=DSQL_ENDPOINT,
            ExpiresIn=900  # 15分
        )
        
        # 接続（agent_graphロールを使用）
        conn = psycopg2.connect(
            host=DSQL_ENDPOINT,
            database=DB_NAME,
            user='agent_graph',  # app_userからagent_graphに変更
            password=auth_token,
            port=5432,
            sslmode='require'
        )
        return conn
        
    except Exception as e:
        logger.error(f"Connection failed: {e}")
        raise


def store_activity(
    member_id: str,
    activity_date: date,
    activity_type: str,
    title: str,
    description: Optional[str] = None,
    blog_url: Optional[str] = None,
    github_repo_url: Optional[str] = None,
    aws_services: Optional[list] = None,
    aws_level: Optional[str] = None,
    tags: Optional[list] = None,
    summary_by_ai: Optional[str] = None
) -> Dict[str, Any]:
    """
    活動記録をデータベースに格納
    
    Args:
        member_id: メンバーID
        activity_date: 活動日
        activity_type: 活動タイプ（slack_post, event_participation等）
        title: 活動タイトル（必須）
        description: 活動内容詳細
        blog_url: ブログURL
        github_repo_url: GitHubリポジトリURL
        aws_services: 使用したAWSサービスリスト
        aws_level: AWSレベル判定結果
        tags: 技術タグリスト
        summary_by_ai: AI生成要約
    
    Returns:
        格納結果
    """
    conn = get_connection()
    
    # 重複チェック（同一メンバー、同一日、同一タイトル）
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM output_history.activities WHERE member_id = %s::uuid AND activity_date = %s AND title = %s",
                (member_id, activity_date, title)
            )
            if cur.fetchone():
                conn.close()
                return {"status": "skipped", "reason": "duplicate"}
    except Exception as e:
        conn.close()
        logger.error(f"Duplicate check failed: {e}")
        raise
    
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                INSERT INTO output_history.activities (
                    member_id, activity_date, activity_type, title, description,
                    blog_url, github_repo_url, aws_services, 
                    aws_level, tags, summary_by_ai
                ) VALUES (
                    %s::uuid, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                RETURNING activity_id
            """, (
                member_id, activity_date, activity_type, title, description,
                blog_url, github_repo_url, 
                json.dumps(aws_services or []),  # JSONとして保存
                aws_level,
                json.dumps(tags or []),  # JSONとして保存
                summary_by_ai
            ))
            conn.commit()
            result = cur.fetchone()
            
        conn.close()
        return {"status": "stored", "activity_id": str(result['activity_id'])}
        
    except Exception as e:
        conn.rollback()
        conn.close()
        logger.error(f"Failed to store activity: {e}")
        return {"status": "error", "message": str(e)}


def store_monthly_report(
    member_id: str,
    report_month: date,
    total_activities: int,
    activities_summary: Dict,
    highlights: Optional[Dict] = None
) -> Dict[str, Any]:
    """
    月次レポートをデータベースに格納
    
    Args:
        member_id: メンバーID
        report_month: レポート対象月（1日）
        total_activities: 総活動件数
        activities_summary: 活動サマリー（タイプ別、レベル別等）
        highlights: ハイライト情報
    
    Returns:
        格納結果
    """
    conn = get_connection()
    
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # 既存チェック（output_historyプレフィックス追加）
            cur.execute("""
                SELECT 1 FROM output_history.monthly_reports 
                WHERE member_id = %s::uuid AND report_month = %s
            """, (member_id, report_month))
            
            if cur.fetchone():
                conn.close()
                return {"status": "exists"}
            
            # 新規作成（year, monthカラムを追加）
            cur.execute("""
                INSERT INTO output_history.monthly_reports (
                    member_id, year, month, report_month, total_activities,
                    activities_summary, highlights
                ) VALUES (
                    %s::uuid, %s, %s, %s, %s, %s, %s
                )
                RETURNING report_id
            """, (
                member_id, 
                report_month.year,  # yearを追加
                report_month.month, # monthを追加
                report_month, 
                total_activities,
                json.dumps(activities_summary),
                json.dumps(highlights or {})
            ))
            conn.commit()
            result = cur.fetchone()
            
        conn.close()
        return {"status": "stored", "report_id": str(result['report_id'])}
        
    except Exception as e:
        conn.rollback()
        conn.close()
        logger.error(f"Failed to store report: {e}")
        return {"status": "error", "message": str(e)}


def record_processing(
    process_type: str,
    status: str = 'success',
    details: Optional[Dict] = None,
    error_message: Optional[str] = None
) -> Dict[str, Any]:
    """
    処理履歴を記録
    
    Args:
        process_type: 処理タイプ（daily_collection, monthly_report等）
        status: 処理ステータス（success, failed, in_progress）
        details: 処理詳細
        error_message: エラーメッセージ（失敗時）
    
    Returns:
        記録結果
    """
    conn = get_connection()
    
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                INSERT INTO output_history.processing_history (
                    process_type, status, details, error_message
                ) VALUES (
                    %s, %s, %s, %s
                )
                RETURNING history_id, process_date
            """, (
                process_type, status,
                json.dumps(details or {}),
                error_message
            ))
            conn.commit()
            result = cur.fetchone()
            
        conn.close()
        return {
            "status": "recorded", 
            "history_id": str(result['history_id']),
            "process_date": result['process_date'].isoformat()
        }
        
    except Exception as e:
        conn.rollback()
        conn.close()
        logger.error(f"Failed to record processing: {e}")
        return {"status": "error", "message": str(e)}


def get_or_create_member(email: str, name: str, github_username: Optional[str] = None) -> str:
    """
    メンバーを取得または作成してIDを返す
    
    Args:
        email: メンバーのメールアドレス（必須・ユニーク）
        name: メンバー名
        github_username: GitHubユーザー名（オプション）
    
    Returns:
        メンバーID（UUID文字列）
    """
    conn = get_connection()
    
    try:
        with conn.cursor() as cur:
            # 既存メンバー確認（output_historyプレフィックス追加）
            cur.execute(
                "SELECT member_id FROM output_history.members WHERE email = %s",
                (email,)
            )
            result = cur.fetchone()
            
            if result:
                member_id = str(result[0])
            else:
                # 新規作成
                cur.execute("""
                    INSERT INTO output_history.members (email, name, github_username)
                    VALUES (%s, %s, %s)
                    RETURNING member_id
                """, (email, name, github_username))
                result = cur.fetchone()
                member_id = str(result[0])
                conn.commit()
        
        conn.close()
        return member_id
        
    except Exception as e:
        conn.rollback()
        conn.close()
        logger.error(f"Failed to get/create member: {e}")
        raise
