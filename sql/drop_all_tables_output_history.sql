-- ================================================================================
-- output_historyスキーマのテーブルとロールを削除するSQL
-- ================================================================================
-- 注意: このスクリプトはデータベースの全データを削除します
-- 実行前に必ずバックアップを取得してください
-- ================================================================================

-- インデックスの削除（存在する場合）
DROP INDEX IF EXISTS output_history.idx_activities_member_id;
DROP INDEX IF EXISTS output_history.idx_activities_activity_date;
DROP INDEX IF EXISTS output_history.idx_activities_activity_type;
DROP INDEX IF EXISTS output_history.idx_activities_date_type;
DROP INDEX IF EXISTS output_history.idx_activities_aws_level;
DROP INDEX IF EXISTS output_history.idx_monthly_reports_member_id;
DROP INDEX IF EXISTS output_history.idx_monthly_reports_year_month;
DROP INDEX IF EXISTS output_history.idx_processing_history_process_type;
DROP INDEX IF EXISTS output_history.idx_processing_history_status;
DROP INDEX IF EXISTS output_history.idx_processing_history_process_date;

-- テーブルの削除（外部キー制約の依存関係順）
DROP TABLE IF EXISTS output_history.processing_history CASCADE;
DROP TABLE IF EXISTS output_history.monthly_reports CASCADE;
DROP TABLE IF EXISTS output_history.activities CASCADE;
DROP TABLE IF EXISTS output_history.members CASCADE;

-- スキーマの削除
DROP SCHEMA IF EXISTS output_history CASCADE;

-- ロールの削除
DROP ROLE IF EXISTS agent_graph;

-- 実行完了メッセージ
-- 削除完了: output_historyスキーマとagent_graphロール、および関連する全てのオブジェクトが削除されました
