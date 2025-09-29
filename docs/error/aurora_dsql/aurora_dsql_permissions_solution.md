# Aurora DSQL権限設定の最終解決策

## エラーの詳細

以下のコマンドはすべてエラーになります：

```sql
-- ❌ エラー: unsupported object type in GRANT
GRANT CONNECT ON DATABASE postgres TO app_user;

-- ❌ エラー: feature not supported on system entity
GRANT USAGE ON SCHEMA public TO app_user;
```

## 根本原因

Aurora DSQLには以下の制限があります：

1. **GRANT ON DATABASE**: 完全に非サポート
2. **publicスキーマ**: システムエンティティとして扱われ、権限付与不可
3. **非adminユーザー**: publicスキーマへのCREATE権限を持てない

## 解決策

### 方法1: adminユーザーでテーブル作成後、個別に権限付与（推奨）

```sql
-- Step 1: adminユーザーでロールを作成
CREATE ROLE app_user WITH LOGIN;

-- Step 2: IAMロールとマッピング
AWS IAM GRANT app_user TO 'arn:aws:iam::YOUR_ACCOUNT_ID:role/YOUR_IAM_ROLE_NAME';

-- Step 3: adminユーザーでテーブルを作成
-- （create_tables_dsql_v2.sqlを実行）

-- Step 4: 作成済みのテーブルに対して権限を付与
GRANT SELECT, INSERT, UPDATE, DELETE ON members TO app_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON activities TO app_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON monthly_reports TO app_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON processing_history TO app_user;

-- Step 5: 今後作成されるテーブルへのデフォルト権限（adminが作成するテーブルのみ）
ALTER DEFAULT PRIVILEGES FOR ROLE admin IN SCHEMA public 
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_user;
```

### 方法2: 別スキーマを使用（代替案）

```sql
-- Step 1: adminユーザーで新しいスキーマを作成
CREATE SCHEMA app_schema;

-- Step 2: ロールを作成してマッピング
CREATE ROLE app_user WITH LOGIN;
AWS IAM GRANT app_user TO 'arn:aws:iam::YOUR_ACCOUNT_ID:role/YOUR_IAM_ROLE_NAME';

-- Step 3: スキーマに対する権限を付与
GRANT USAGE ON SCHEMA app_schema TO app_user;
GRANT CREATE ON SCHEMA app_schema TO app_user;

-- Step 4: app_schemaにテーブルを作成
-- （SQLファイルを修正してapp_schemaを使用）
```

## 実装手順

### 1. IAMロール作成

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

### 2. adminとして接続

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

### 3. 権限設定（方法1を使用）

```sql
-- ロール作成
CREATE ROLE app_user WITH LOGIN;

-- IAMマッピング
AWS IAM GRANT app_user TO 'arn:aws:iam::YOUR_ACCOUNT_ID:role/YOUR_ROLE';

-- テーブル作成（別途SQLファイル実行）
-- その後、個別に権限付与
GRANT SELECT, INSERT, UPDATE, DELETE ON members TO app_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON activities TO app_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON monthly_reports TO app_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON processing_history TO app_user;

-- デフォルト権限設定
ALTER DEFAULT PRIVILEGES FOR ROLE admin IN SCHEMA public 
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_user;
```

### 4. app_userとして接続テスト

```bash
# app_userトークン生成（注: admin用ではない）
aws dsql generate-db-connect-auth-token \
  --expires-in 3600 \
  --region us-east-1 \
  --hostname 4qabuloasdxs36dl2zc6pablbm.dsql.us-east-1.on.aws

# 接続テスト
PGSSLMODE=require psql \
  --dbname jr_champions_activities \
  --username app_user \
  --host 4qabuloasdxs36dl2zc6pablbm.dsql.us-east-1.on.aws \
  -c "SELECT current_user, current_database();"
```

## Python実装の修正

```python
class DSQLClient:
    def __init__(self, 
                 endpoint: str,
                 database: str = "jr_champions_activities",
                 region: str = "us-east-1",
                 use_admin: bool = False):
        self.endpoint = endpoint
        self.database = database
        self.region = region
        self.use_admin = use_admin
        self.username = "admin" if use_admin else "app_user"
        
    def generate_auth_token(self) -> str:
        client = boto3.client("dsql", region_name=self.region)
        
        if self.use_admin:
            # admin用
            token = client.generate_db_connect_admin_auth_token(
                Hostname=self.endpoint,
                Region=self.region
            )
        else:
            # app_user用
            token = client.generate_db_connect_auth_token(
                Hostname=self.endpoint,
                Region=self.region
            )
        return token
```

## 重要な注意事項

1. **publicスキーマの制限**
   - `GRANT USAGE ON SCHEMA public`は使用不可
   - publicスキーマのテーブルに個別に権限付与が必要

2. **デフォルト権限の設定**
   - `ALTER DEFAULT PRIVILEGES FOR ROLE admin`を使用
   - adminが作成するテーブルのみに適用される

3. **テーブル作成**
   - 必ずadminユーザーで実行
   - app_userではテーブル作成不可

4. **接続の分離**
   - テーブル管理: admin
   - データ操作: app_user

## トラブルシューティング

| エラー | 原因 | 解決策 |
|--------|------|--------|
| `unsupported object type in GRANT` | GRANT ON DATABASE使用 | 削除（不要） |
| `feature not supported on system entity` | GRANT USAGE ON SCHEMA public使用 | 削除（個別テーブルに権限付与） |
| `permission denied for database` | 非adminでスキーマ作成 | adminで実行 |
| `permission denied for table` | テーブル権限なし | 個別にGRANT実行 |

## まとめ

Aurora DSQLの権限管理は標準PostgreSQLと大きく異なります：

1. データベースレベルの権限付与は不要（IAM認証で制御）
2. publicスキーマへの権限付与は不可（個別テーブルに付与）
3. 非adminユーザーは読み書きのみ（CREATE権限なし）
4. 権限の分離を明確に（admin = DDL、app_user = DML）

この制限を理解して設計することが重要です。
