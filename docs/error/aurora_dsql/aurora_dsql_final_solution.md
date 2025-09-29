# Aurora DSQL権限設定 - 最終解決方法

## 問題の根本原因

`public`スキーマはAurora DSQLではシステムエンティティとして扱われるため、直接権限付与ができません。

```sql
-- ❌ これらはエラーになる
GRANT USAGE ON SCHEMA public TO app_user;  -- ERROR: feature not supported on system entity
```

## 解決方法

AWSドキュメントの例に従い、カスタムスキーマを使用します。

### オプション1: カスタムスキーマを作成（AWSドキュメント準拠）

```sql
-- Step 1: adminユーザーでロールを作成
CREATE ROLE app_user WITH LOGIN;

-- Step 2: IAMロールとマッピング
AWS IAM GRANT app_user TO 'arn:aws:iam::YOUR_ACCOUNT_ID:role/YOUR_IAM_ROLE_NAME';

-- Step 3: カスタムスキーマを作成
CREATE SCHEMA app_schema;

-- Step 4: スキーマへの権限を付与（AWSドキュメントの例と同じ）
GRANT USAGE ON SCHEMA app_schema TO app_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA app_schema TO app_user;

-- Step 5: デフォルト権限設定
ALTER DEFAULT PRIVILEGES FOR ROLE admin IN SCHEMA app_schema 
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_user;
```

#### テーブル作成SQLの修正

`create_tables_dsql_v3.sql`を作成：

```sql
-- スキーマを明示的に指定
SET search_path TO app_schema;

-- メンバー情報テーブル
CREATE TABLE app_schema.members (
    member_id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    github_username VARCHAR(100),
    aws_account_id VARCHAR(12),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 活動記録テーブル
CREATE TABLE app_schema.activities (
    activity_id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    member_id UUID NOT NULL,
    activity_date DATE NOT NULL,
    activity_type VARCHAR(50) NOT NULL,
    title VARCHAR(500) NOT NULL,
    description TEXT,
    aws_services TEXT,
    github_repo_url VARCHAR(500),
    blog_url VARCHAR(500),
    tags TEXT,
    aws_level VARCHAR(50),
    summary_by_ai TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(member_id, activity_date, title)
);

-- 月次レポートテーブル
CREATE TABLE app_schema.monthly_reports (
    report_id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    report_month DATE NOT NULL,
    member_id UUID NOT NULL,
    activities_summary TEXT NOT NULL,
    total_activities INTEGER DEFAULT 0,
    highlights TEXT,
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(report_month, member_id)
);

-- 処理履歴テーブル
CREATE TABLE app_schema.processing_history (
    history_id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    process_type VARCHAR(50) NOT NULL,
    process_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(20) NOT NULL,
    details TEXT,
    error_message TEXT
);

-- インデックス作成
CREATE INDEX ASYNC idx_activities_member_date ON app_schema.activities(member_id, activity_date);
CREATE INDEX ASYNC idx_activities_date ON app_schema.activities(activity_date);
CREATE INDEX ASYNC idx_monthly_reports_month ON app_schema.monthly_reports(report_month);
CREATE INDEX ASYNC idx_members_email ON app_schema.members(email);
CREATE INDEX ASYNC idx_processing_history_date ON app_schema.processing_history(process_date);
```

### オプション2: publicスキーマで個別テーブル権限（既存テーブルがある場合）

既にpublicスキーマにテーブルが作成されている場合：

```sql
-- Step 1: ロール作成とマッピング
CREATE ROLE app_user WITH LOGIN;
AWS IAM GRANT app_user TO 'arn:aws:iam::YOUR_ACCOUNT_ID:role/YOUR_IAM_ROLE_NAME';

-- Step 2: 個別テーブルに権限付与
GRANT SELECT, INSERT, UPDATE, DELETE ON public.members TO app_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.activities TO app_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.monthly_reports TO app_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.processing_history TO app_user;

-- Step 3: 今後作成されるテーブル用のデフォルト権限
ALTER DEFAULT PRIVILEGES FOR ROLE admin IN SCHEMA public 
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_user;
```

## 実装手順

### 1. IAMロールの準備

```bash
# IAMポリシー
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "dsql:DbConnect",
      "Resource": "arn:aws:dsql:us-east-1:*:cluster/4qabuloasdxs36dl2zc6pablbm"
    }
  ]
}
```

### 2. データベース設定（adminユーザーで実行）

```bash
# adminトークン生成
aws dsql generate-db-connect-admin-auth-token \
  --expires-in 3600 \
  --region us-east-1 \
  --hostname 4qabuloasdxs36dl2zc6pablbm.dsql.us-east-1.on.aws

# 接続
PGSSLMODE=require psql \
  --dbname jr_champions_activities \
  --username admin \
  --host 4qabuloasdxs36dl2zc6pablbm.dsql.us-east-1.on.aws
```

### 3. SQLの実行（オプション1を推奨）

```sql
-- カスタムスキーマ方式（推奨）
CREATE SCHEMA app_schema;
CREATE ROLE app_user WITH LOGIN;
AWS IAM GRANT app_user TO 'arn:aws:iam::YOUR_ACCOUNT_ID:role/YOUR_ROLE';
GRANT USAGE ON SCHEMA app_schema TO app_user;
GRANT CREATE ON SCHEMA app_schema TO app_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA app_schema TO app_user;
ALTER DEFAULT PRIVILEGES FOR ROLE admin IN SCHEMA app_schema 
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_user;
```

### 4. Python接続コードの修正

```python
import boto3
import psycopg
from typing import Optional

class DSQLClient:
    def __init__(self, 
                 endpoint: str,
                 database: str = "jr_champions_activities",
                 schema: str = "app_schema",  # スキーマを指定
                 region: str = "us-east-1",
                 use_admin: bool = False):
        self.endpoint = endpoint
        self.database = database
        self.schema = schema
        self.region = region
        self.use_admin = use_admin
        self.username = "admin" if use_admin else "app_user"
        self.connection = None
        
    def connect(self) -> psycopg.Connection:
        """Aurora DSQLに接続"""
        if self.connection and not self.connection.closed:
            return self.connection
        
        try:
            # 認証トークンを生成
            password = self.generate_auth_token()
            
            # 接続
            self.connection = psycopg.connect(
                host=self.endpoint,
                port=5432,
                dbname=self.database,
                user=self.username,
                password=password,
                sslmode='require',
                options=f'-c search_path={self.schema}',  # スキーマを設定
                connect_timeout=30
            )
            print(f"Connected as {self.username} to schema {self.schema}")
            return self.connection
            
        except Exception as e:
            print(f"Connection failed: {e}")
            raise
    
    def execute_sql(self, sql: str, params=None):
        """SQLを実行"""
        with self.connect() as conn:
            with conn.cursor() as cursor:
                # スキーマを明示的に設定
                cursor.execute(f"SET search_path TO {self.schema}")
                cursor.execute(sql, params)
                if cursor.description:
                    return cursor.fetchall()
                conn.commit()
```

### 5. app_userでの接続テスト

```bash
# app_userトークン生成
aws dsql generate-db-connect-auth-token \
  --expires-in 3600 \
  --region us-east-1 \
  --hostname 4qabuloasdxs36dl2zc6pablbm.dsql.us-east-1.on.aws

# 接続テスト
PGSSLMODE=require psql \
  --dbname jr_champions_activities \
  --username app_user \
  --host 4qabuloasdxs36dl2zc6pablbm.dsql.us-east-1.on.aws \
  -c "SELECT current_user, current_schemas(true);"
```

## 比較表

| 方式 | publicスキーマ | カスタムスキーマ |
|------|---------------|-----------------|
| **GRANT USAGE ON SCHEMA** | ❌ エラー | ✅ 可能 |
| **GRANT CREATE ON SCHEMA** | ❌ エラー | ✅ 可能 |
| **app_userでテーブル作成** | ❌ 不可 | ✅ 可能（CREATE権限付与時） |
| **既存テーブルとの互換性** | ✅ 高い | ⚠️ 移行が必要 |
| **AWSドキュメント準拠** | ❌ | ✅ |

## 推奨事項

1. **新規プロジェクト**: カスタムスキーマ（app_schema）を使用
2. **既存プロジェクト**: publicスキーマで個別テーブル権限付与
3. **本番環境**: 最小権限の原則に従い、CREATE権限は付与しない

## まとめ

Aurora DSQLではpublicスキーマがシステムエンティティのため：
- カスタムスキーマを作成して使用（AWSドキュメント推奨）
- またはpublicスキーマの個別テーブルに権限付与

これにより、適切な権限分離とセキュリティを確保できます。
