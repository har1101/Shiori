-- =================================================
-- Aurora DSQL 強制クリーンアップスクリプト
-- すべてのスキーマとオブジェクトを削除
-- =================================================

-- 1. output_historyスキーマのすべてのテーブルを削除（存在する場合）
DROP TABLE IF EXISTS output_history.processing_history CASCADE;
DROP TABLE IF EXISTS output_history.monthly_reports CASCADE;
DROP TABLE IF EXISTS output_history.activities CASCADE;
DROP TABLE IF EXISTS output_history.members CASCADE;

-- 2. app_schemaスキーマのすべてのテーブルを削除（古いスキーマ）
DROP TABLE IF EXISTS app_schema.processing_history CASCADE;
DROP TABLE IF EXISTS app_schema.monthly_reports CASCADE;
DROP TABLE IF EXISTS app_schema.activities CASCADE;
DROP TABLE IF EXISTS app_schema.members CASCADE;

-- 3. output_historyスキーマを削除
DROP SCHEMA IF EXISTS output_history CASCADE;

-- 4. app_schemaスキーマを削除（古いスキーマ）
DROP SCHEMA IF EXISTS app_schema CASCADE;

-- 5. agent_graphロールを削除
DROP ROLE IF EXISTS agent_graph;

-- 6. app_userロールを削除（古いロール）
DROP ROLE IF EXISTS app_user;

-- 7. publicスキーマのテーブルを個別に削除（もし存在すれば）
-- Aurora DSQLでは動的SQLが使えないため、手動でリストアップ
DROP TABLE IF EXISTS public.members CASCADE;
DROP TABLE IF EXISTS public.activities CASCADE;
DROP TABLE IF EXISTS public.monthly_reports CASCADE;
DROP TABLE IF EXISTS public.processing_history CASCADE;

-- 8. 完了メッセージ（Aurora DSQLではRAISE NOTICEが使えないためコメントで代替）
-- ======================================
-- クリーンアップ完了
-- ======================================
-- すべてのカスタムスキーマ、テーブル、ロールが削除されました。
-- データベースは初期状態に戻りました。
