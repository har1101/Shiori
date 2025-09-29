# Aurora DSQL スキーマ確認コマンド集

## 前提条件
```bash
export DSQL_ENDPOINT="4qabuloasdxs36dl2zc6pablbm.dsql.us-east-1.on.aws"
export DB_NAME="jr_champions_activities"
export AWS_REGION="us-east-1"
export PGSSLMODE=require
```

## 1. スキーマの確認

### 全スキーマを表示
```bash
psql -h $DSQL_ENDPOINT -U admin -d $DB_NAME -c "\dn"
```

### 特定スキーマの詳細を表示
```bash
psql -h $DSQL_ENDPOINT -U admin -d $DB_NAME -c "\dn+ app_schema"
```

## 2. テーブルの確認

### publicスキーマのテーブル（デフォルト）
```bash
# publicスキーマのテーブル一覧
psql -h $DSQL_ENDPOINT -U admin -d $DB_NAME -c "\dt"

# または明示的に指定
psql -h $DSQL_ENDPOINT -U admin -d $DB_NAME -c "\dt public.*"
```

### app_schemaのテーブル
```bash
# app_schemaのテーブル一覧
psql -h $DSQL_ENDPOINT -U admin -d $DB_NAME -c "\dt app_schema.*"

# または、search_pathを変更してから表示
psql -h $DSQL_ENDPOINT -U admin -d $DB_NAME -c "SET search_path TO app_schema; \dt"
```

### 全スキーマのテーブルを表示
```bash
psql -h $DSQL_ENDPOINT -U admin -d $DB_NAME -c "\dt *.*"
```

## 3. テーブル構造の確認

### publicスキーマのテーブル構造
```bash
# membersテーブル（publicスキーマ）
psql -h $DSQL_ENDPOINT -U admin -d $DB_NAME -c "\d+ public.members"
```

### app_schemaのテーブル構造
```bash
# membersテーブル（app_schemaスキーマ）
psql -h $DSQL_ENDPOINT -U admin -d $DB_NAME -c "\d+ app_schema.members"

# activitiesテーブル
psql -h $DSQL_ENDPOINT -U admin -d $DB_NAME -c "\d+ app_schema.activities"

# monthly_reportsテーブル
psql -h $DSQL_ENDPOINT -U admin -d $DB_NAME -c "\d+ app_schema.monthly_reports"

# processing_historyテーブル
psql -h $DSQL_ENDPOINT -U admin -d $DB_NAME -c "\d+ app_schema.processing_history"
```

## 4. インデックスの確認

### app_schemaのインデックス
```bash
# app_schemaのインデックス一覧
psql -h $DSQL_ENDPOINT -U admin -d $DB_NAME -c "\di app_schema.*"

# 非同期インデックスの状態確認
psql -h $DSQL_ENDPOINT -U admin -d $DB_NAME -c "SELECT * FROM sys.jobs WHERE job_type = 'CREATE_INDEX';"
```

## 5. 権限の確認

### ロールのマッピング確認
```bash
# IAMロールとデータベースロールのマッピング
psql -h $DSQL_ENDPOINT -U admin -d $DB_NAME -c "SELECT * FROM sys.iam_pg_role_mappings;"
```

### テーブル権限の確認
```bash
# app_schemaのテーブル権限
psql -h $DSQL_ENDPOINT -U admin -d $DB_NAME -c "\dp app_schema.*"

# 特定テーブルの権限詳細
psql -h $DSQL_ENDPOINT -U admin -d $DB_NAME -c "\dp app_schema.members"
```

### スキーマ権限の確認
```bash
# スキーマレベルの権限
psql -h $DSQL_ENDPOINT -U admin -d $DB_NAME -c "\
SELECT n.nspname AS schema,
       u.usename AS owner,
       has_schema_privilege('app_user', n.nspname, 'USAGE') AS app_user_usage,
       has_schema_privilege('app_user', n.nspname, 'CREATE') AS app_user_create
FROM pg_namespace n
JOIN pg_user u ON n.nspowner = u.usesysid
WHERE n.nspname IN ('public', 'app_schema');"
```

## 6. 現在の設定確認

### search_pathの確認
```bash
psql -h $DSQL_ENDPOINT -U admin -d $DB_NAME -c "SHOW search_path;"
```

### 現在のユーザーとデータベース
```bash
psql -h $DSQL_ENDPOINT -U admin -d $DB_NAME -c "SELECT current_user, current_database(), current_schemas(true);"
```

## 7. データ確認

### app_schemaのテーブルデータ確認
```bash
# membersテーブルのレコード数
psql -h $DSQL_ENDPOINT -U admin -d $DB_NAME -c "SELECT COUNT(*) FROM app_schema.members;"

# activitiesテーブルのレコード数
psql -h $DSQL_ENDPOINT -U admin -d $DB_NAME -c "SELECT COUNT(*) FROM app_schema.activities;"
```

## 8. 複合コマンド

### スキーマとテーブルの一括確認
```bash
psql -h $DSQL_ENDPOINT -U admin -d $DB_NAME <<EOF
\echo '=== スキーマ一覧 ==='
\dn
\echo ''
\echo '=== publicスキーマのテーブル ==='
\dt public.*
\echo ''
\echo '=== app_schemaのテーブル ==='
\dt app_schema.*
\echo ''
\echo '=== 権限マッピング ==='
SELECT * FROM sys.iam_pg_role_mappings;
EOF
```

## トラブルシューティング

### "Did not find any relations"エラーの対処

1. **データベース名を確認**
   ```bash
   # 正しいデータベースを指定
   psql -h $DSQL_ENDPOINT -U admin -d jr_champions_activities -c "\dt"
   ```

2. **スキーマを明示的に指定**
   ```bash
   # app_schemaのテーブルを確認
   psql -h $DSQL_ENDPOINT -U admin -d jr_champions_activities -c "\dt app_schema.*"
   ```

3. **全スキーマを確認**
   ```bash
   # 全スキーマの全テーブル
   psql -h $DSQL_ENDPOINT -U admin -d jr_champions_activities -c "\dt *.*"
   ```

4. **search_pathを設定してから確認**
   ```bash
   psql -h $DSQL_ENDPOINT -U admin -d jr_champions_activities <<EOF
   SET search_path TO app_schema, public;
   \dt
   EOF
   ```

## 注意事項

- Aurora DSQLではデータベース名は`postgres`固定の場合があります
- カスタムスキーマ（app_schema）を使用している場合、明示的にスキーマを指定する必要があります
- `\dt`コマンドはデフォルトでpublicスキーマのみを表示します
