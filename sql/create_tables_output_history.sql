-- ================================================================================
-- Jr.Champions 活動記録システム - Aurora DSQL テーブル定義
-- ================================================================================
-- スキーマ: output_history
-- ロール: agent_graph (SELECT, INSERT, UPDATE権限のみ、DELETE権限なし)
-- 
-- Aurora DSQL制約への対応:
-- - JSON/JSONB型 → TEXT型で代替
-- - CREATE INDEX → CREATE INDEX ASYNC使用
-- - PL/pgSQL関数・トリガー → アプリケーション層で実装
-- ================================================================================

-- ================================================================================
-- 1. スキーマとロールの作成
-- ================================================================================

-- スキーマの作成
CREATE SCHEMA IF NOT EXISTS output_history;

-- データベースロールの作成
CREATE ROLE agent_graph WITH LOGIN;

-- スキーマに対する基本権限付与
GRANT USAGE ON SCHEMA output_history TO agent_graph;

-- ================================================================================
-- 2. テーブル定義
-- ================================================================================

-- --------------------------------------------------------------------------------
-- 2.1 members (メンバー) テーブル
-- --------------------------------------------------------------------------------
-- Slack統合のユーザー情報を格納（slack_agent_factory.pyのJSONL出力に対応）
-- フィールド対応:
--   slack_user_id -> slack_user_id
--   slack_user_name -> slack_user_name
--   slack_user_email -> slack_user_email
CREATE TABLE output_history.members (
    slack_user_id VARCHAR(50) PRIMARY KEY,  -- SlackのユーザーID（例: U123ABC）
    slack_user_name VARCHAR(100),  -- Slackの表示名（NULL許容）
    slack_user_email VARCHAR(255) UNIQUE,  -- Slackのメール（NULL許容）
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- agent_graphロールへの権限付与（SELECT, INSERT, UPDATE のみ）
GRANT SELECT, INSERT, UPDATE ON output_history.members TO agent_graph;

-- --------------------------------------------------------------------------------
-- 2.2 activities (活動) テーブル
-- --------------------------------------------------------------------------------
-- Slack経由で収集した活動データ（slack_agent_factory.pyのJSONL出力に対応）
-- フィールド対応:
--   slack_user_id -> slack_user_id（membersテーブルの主キーを参照）
--   url -> url（活動のURL）
--   slack_upload_time -> slack_upload_time（YYYYMMDD形式を変換して格納）
--   slack_channel -> slack_channel
CREATE TABLE output_history.activities (
    activity_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slack_user_id VARCHAR(50) NOT NULL,  -- membersテーブルのslack_user_idを参照
    activity_type VARCHAR(20) NOT NULL CHECK (
        activity_type IN ('presentation', 'article', 'other')
    ),
    title VARCHAR(255) NOT NULL,
    description TEXT,  -- 100-200文字の要約
    summary_by_ai TEXT,  -- AI生成の詳細要約
    activity_date DATE NOT NULL,  -- slack_upload_timeから変換
    event_name VARCHAR(255),
    participant_count INTEGER,
    like_count INTEGER,
    url TEXT NOT NULL,  -- slack_agent_factory.pyの"url"フィールドに対応
    aws_services TEXT,  -- JSONとしてAWSサービスリストを格納
    aws_level VARCHAR(10) CHECK (aws_level IN ('100', '200', '300', '400')),
    tags TEXT,  -- JSONとして技術タグを格納
    slack_message_id VARCHAR(100) UNIQUE,
    slack_channel VARCHAR(50),  -- slack_agent_factory.pyの"slack_channel"フィールドに対応
    slack_upload_time VARCHAR(8),  -- slack_agent_factory.pyの"slack_upload_time"フィールド（YYYYMMDD形式）
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    
    -- Aurora DSQLは外部キー制約をサポートしていないため削除
    -- アプリケーション層でデータ整合性を管理
);

-- agent_graphロールへの権限付与（SELECT, INSERT, UPDATE のみ）
GRANT SELECT, INSERT, UPDATE ON output_history.activities TO agent_graph;

-- --------------------------------------------------------------------------------
-- 2.3 monthly_reports (月次レポート) テーブル
-- --------------------------------------------------------------------------------
CREATE TABLE output_history.monthly_reports (
    report_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slack_user_id VARCHAR(50) NOT NULL,  -- membersテーブルのslack_user_idを参照
    year INTEGER NOT NULL,
    month INTEGER NOT NULL CHECK (month >= 1 AND month <= 12),
    report_month DATE NOT NULL,  -- dsql_client.pyの定義に対応
    total_activities INTEGER NOT NULL DEFAULT 0,
    activities_by_type TEXT NOT NULL DEFAULT '{}',  -- JSONとして種別ごとの活動数を格納
    activities_summary TEXT NOT NULL DEFAULT '{}',  -- JSONとして活動サマリーを格納
    highlights TEXT DEFAULT '{}',  -- JSONとしてハイライト情報を格納
    total_participants INTEGER DEFAULT 0,
    total_likes INTEGER DEFAULT 0,
    feedback_content TEXT,  -- Markdown形式
    community_contribution TEXT,  -- Markdown形式
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT unique_user_year_month UNIQUE (slack_user_id, year, month)
    -- Aurora DSQLは外部キー制約をサポートしていないため削除
    -- アプリケーション層でデータ整合性を管理
);

-- agent_graphロールへの権限付与（SELECT, INSERT, UPDATE のみ）
GRANT SELECT, INSERT, UPDATE ON output_history.monthly_reports TO agent_graph;

-- --------------------------------------------------------------------------------
-- 2.4 processing_history (処理履歴) テーブル
-- --------------------------------------------------------------------------------
CREATE TABLE output_history.processing_history (
    history_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    process_type VARCHAR(50) NOT NULL CHECK (
        process_type IN ('slack_fetch', 'report_generation', 'daily_collection', 'monthly_report')
    ),
    process_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,  -- dsql_client.pyの定義に対応
    last_processed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_slack_timestamp TIMESTAMP WITH TIME ZONE,
    status VARCHAR(20) NOT NULL CHECK (status IN ('success', 'failed', 'in_progress')),
    details TEXT DEFAULT '{}',  -- JSONとして処理詳細を格納
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- agent_graphロールへの権限付与（SELECT, INSERT, UPDATE のみ）
GRANT SELECT, INSERT, UPDATE ON output_history.processing_history TO agent_graph;

-- ================================================================================
-- 3. インデックス作成（非同期）
-- ================================================================================

-- activities テーブルのインデックス
CREATE INDEX ASYNC idx_activities_slack_user_id ON output_history.activities(slack_user_id);
CREATE INDEX ASYNC idx_activities_activity_date ON output_history.activities(activity_date);  -- DESCを削除
CREATE INDEX ASYNC idx_activities_activity_type ON output_history.activities(activity_type);
CREATE INDEX ASYNC idx_activities_date_type ON output_history.activities(activity_date, activity_type);
CREATE INDEX ASYNC idx_activities_aws_level ON output_history.activities(aws_level);

-- monthly_reports テーブルのインデックス
CREATE INDEX ASYNC idx_monthly_reports_slack_user_id ON output_history.monthly_reports(slack_user_id);
CREATE INDEX ASYNC idx_monthly_reports_year_month ON output_history.monthly_reports(year, month);

-- processing_history テーブルのインデックス
CREATE INDEX ASYNC idx_processing_history_process_type ON output_history.processing_history(process_type);
CREATE INDEX ASYNC idx_processing_history_status ON output_history.processing_history(status);
CREATE INDEX ASYNC idx_processing_history_process_date ON output_history.processing_history(process_date);  -- DESCを削除

-- ================================================================================
-- 4. 権限の最終確認
-- ================================================================================

-- Aurora DSQLはシーケンスへの権限付与をサポートしていないため削除
-- gen_random_uuid()はシーケンスを使用しないため、この権限は不要

-- Aurora DSQLはALTER DEFAULT PRIVILEGESをサポートしていないため削除
-- 新しいテーブルが追加された場合は、個別にGRANT文を実行する必要があります

-- ================================================================================
-- 実行完了メッセージ
-- ================================================================================
-- このSQLスクリプトにより、以下が作成されます：
-- 1. output_historyスキーマ
-- 2. agent_graphロール（SELECT, INSERT, UPDATE権限のみ）
-- 3. 4つのテーブル（members, activities, monthly_reports, processing_history）
-- 4. パフォーマンス最適化のための非同期インデックス
--
-- 注意事項:
-- - agent_graphロールにはDELETE権限は付与されていません
-- - JSON型の代わりにTEXT型を使用（Aurora DSQLの制約）
-- - インデックスは非同期で作成（CREATE INDEX ASYNC）
-- ================================================================================
