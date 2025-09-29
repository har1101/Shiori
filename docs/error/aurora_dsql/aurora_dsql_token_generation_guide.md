# Aurora DSQL トークン生成コマンドの正しい使い分け

## エラーの原因

「Wrong user to action mapping」エラーは、ユーザーとトークン生成コマンドの組み合わせが間違っている場合に発生します。

### エラーパターン

| ユーザー | 使用したコマンド | エラーメッセージ |
|---------|-----------------|-----------------|
| admin | generate-db-connect-auth-token | `Wrong user to action mapping. user: admin, action: DbConnect` |
| app_user | generate-db-connect-admin-auth-token | `Wrong user to action mapping. user: app_user, action: DbConnectAdmin` |

## 正しい使い分け

### 重要なルール

1. **adminユーザー** → `generate-db-connect-admin-auth-token` を使用
2. **カスタムロール（app_user等）** → `generate-db-connect-auth-token` を使用

### コマンドの違い

| コマンド | 用途 | 対象ユーザー | IAMアクション |
|---------|------|------------|---------------|
| `generate-db-connect-admin-auth-token` | 管理者用トークン生成 | adminのみ | dsql:DbConnectAdmin |
| `generate-db-connect-auth-token` | 一般用トークン生成 | カスタムロール | dsql:DbConnect |

## 正しいコマンド例

### 1. adminユーザーで接続する場合

```bash
# adminユーザー用トークン生成（DbConnectAdmin権限必要）
aws dsql generate-db-connect-admin-auth-token \
  --expires-in 3600 \
  --region us-east-1 \
  --hostname 4qabuloasdxs36dl2zc6pablbm.dsql.us-east-1.on.aws

# psqlで接続
PGSSLMODE=require psql \
  --dbname jr_champions_activities \
  --username admin \
  --host 4qabuloasdxs36dl2zc6pablbm.dsql.us-east-1.on.aws
```

### 2. app_userで接続する場合

```bash
# app_user用トークン生成（DbConnect権限必要）
aws dsql generate-db-connect-auth-token \
  --expires-in 3600 \
  --region us-east-1 \
  --hostname 4qabuloasdxs36dl2zc6pablbm.dsql.us-east-1.on.aws

# psqlで接続
PGSSLMODE=require psql \
  --dbname jr_champions_activities \
  --username app_user \
  --host 4qabuloasdxs36dl2zc6pablbm.dsql.us-east-1.on.aws
```

## IAM権限の要件

### adminユーザー用IAMポリシー

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "dsql:DbConnectAdmin",
      "Resource": "arn:aws:dsql:us-east-1:*:cluster/4qabuloasdxs36dl2zc6pablbm"
    }
  ]
}
```

### app_user用IAMポリシー

```json
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

## Python実装での使い分け

```python
import boto3
import psycopg

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
        """IAM認証トークンを生成（正しいコマンドを使い分け）"""
        client = boto3.client("dsql", region_name=self.region)
        
        if self.use_admin:
            # adminユーザー用（DbConnectAdmin）
            token = client.generate_db_connect_admin_auth_token(
                Hostname=self.endpoint,
                Region=self.region,
                ExpiresIn=3600  # オプション
            )
        else:
            # カスタムロール用（DbConnect）
            token = client.generate_db_connect_auth_token(
                Hostname=self.endpoint,
                Region=self.region,
                ExpiresIn=3600  # オプション
            )
        
        return token
```

## トラブルシューティング

### よくある間違い

1. **adminユーザーで通常トークンを使用**
   ```bash
   # ❌ 間違い
   aws dsql generate-db-connect-auth-token ... 
   psql --username admin ...
   # Error: Wrong user to action mapping. user: admin, action: DbConnect
   ```

2. **app_userで管理者トークンを使用**
   ```bash
   # ❌ 間違い
   aws dsql generate-db-connect-admin-auth-token ...
   psql --username app_user ...
   # Error: Wrong user to action mapping. user: app_user, action: DbConnectAdmin
   ```

### デバッグ手順

1. **現在のIAMロールを確認**
   ```bash
   aws sts get-caller-identity
   ```

2. **IAMロールのマッピングを確認**
   ```sql
   SELECT * FROM sys.iam_pg_role_mappings;
   ```

3. **正しいトークン生成コマンドを選択**
   - adminなら → `generate-db-connect-admin-auth-token`
   - app_userなら → `generate-db-connect-auth-token`

4. **環境変数で自動化**
   ```bash
   # adminユーザー用
   export PGPASSWORD=$(aws dsql generate-db-connect-admin-auth-token \
     --expires-in 3600 \
     --region us-east-1 \
     --hostname $DSQL_ENDPOINT)
   
   # app_user用
   export PGPASSWORD=$(aws dsql generate-db-connect-auth-token \
     --expires-in 3600 \
     --region us-east-1 \
     --hostname $DSQL_ENDPOINT)
   ```

## まとめ

| 項目 | admin | app_user |
|-----|-------|----------|
| **データベースユーザー名** | admin | app_user |
| **トークン生成コマンド** | generate-db-connect-admin-auth-token | generate-db-connect-auth-token |
| **必要なIAMアクション** | dsql:DbConnectAdmin | dsql:DbConnect |
| **主な用途** | DDL操作、ロール管理 | DML操作、アプリケーション接続 |

**重要**: ユーザー名とトークン生成コマンドは必ず一致させる必要があります。
