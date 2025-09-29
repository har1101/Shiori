# SQL定義

## Aurora DSQLでのテーブル作成

Aurora DSQLはPostgreSQL互換なので、PostgreSQLの構文で記述します。

### 1. データベース作成

```sql
-- データベースの作成（必要に応じて）
CREATE DATABASE jr_champions_activities;
```

### 2. テーブル作成

#### Members（メンバー）テーブル

```sql
CREATE TABLE members (
    member_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    slack_user_id VARCHAR(50) UNIQUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- インデックス
CREATE INDEX idx_members_email ON members(email);
CREATE INDEX idx_members_slack_user_id ON members(slack_user_id);
```

#### Activities（活動）テーブル

```sql
CREATE TABLE activities (
    activity_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    member_id UUID NOT NULL,
    activity_type VARCHAR(20) NOT NULL CHECK (activity_type IN ('event_presentation', 'article', 'study_group', 'other')),
    title VARCHAR(255) NOT NULL,
    description TEXT,
    activity_date DATE NOT NULL,
    event_name VARCHAR(255),
    participant_count INTEGER,
    like_count INTEGER,
    resource_url TEXT,
    slack_message_id VARCHAR(100) UNIQUE,
    slack_channel_id VARCHAR(50),
    slack_timestamp TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    -- 外部キー制約
    CONSTRAINT fk_activities_member 
        FOREIGN KEY (member_id) 
        REFERENCES members(member_id) 
        ON DELETE CASCADE
);

-- インデックス
CREATE INDEX idx_activities_member_id ON activities(member_id);
CREATE INDEX idx_activities_activity_date ON activities(activity_date DESC);
CREATE INDEX idx_activities_activity_type ON activities(activity_type);
CREATE INDEX idx_activities_slack_message_id ON activities(slack_message_id);

-- カレンダー表示用の複合インデックス
CREATE INDEX idx_activities_date_type ON activities(activity_date, activity_type);
```

#### MonthlyReports（月次レポート）テーブル

```sql
CREATE TABLE monthly_reports (
    report_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    year INTEGER NOT NULL,
    month INTEGER NOT NULL CHECK (month >= 1 AND month <= 12),
    total_activities INTEGER NOT NULL DEFAULT 0,
    activities_by_type JSONB NOT NULL DEFAULT '{}',
    total_participants INTEGER DEFAULT 0,
    total_likes INTEGER DEFAULT 0,
    feedback_content TEXT,
    community_contribution TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    -- 年月の組み合わせをユニークに
    CONSTRAINT unique_year_month UNIQUE (year, month)
);

-- インデックス
CREATE INDEX idx_monthly_reports_year_month ON monthly_reports(year DESC, month DESC);
```

#### ProcessingHistory（処理履歴）テーブル

```sql
CREATE TABLE processing_history (
    history_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    process_type VARCHAR(20) NOT NULL CHECK (process_type IN ('slack_fetch', 'report_generation')),
    last_processed_at TIMESTAMP WITH TIME ZONE NOT NULL,
    last_slack_timestamp TIMESTAMP WITH TIME ZONE,
    status VARCHAR(20) NOT NULL CHECK (status IN ('success', 'failed')),
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- インデックス
CREATE INDEX idx_processing_history_process_type ON processing_history(process_type, created_at DESC);
```

### 3. 更新日時の自動更新トリガー

```sql
-- 更新日時を自動的に更新する関数
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- membersテーブルのトリガー
CREATE TRIGGER update_members_updated_at BEFORE UPDATE ON members
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- activitiesテーブルのトリガー
CREATE TRIGGER update_activities_updated_at BEFORE UPDATE ON activities
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
```

### 4. サンプルデータ（開発時のテスト用）

```sql
-- サンプルメンバー
INSERT INTO members (email, name, slack_user_id) VALUES
('test1@example.com', 'テストユーザー1', 'U123456789'),
('test2@example.com', 'テストユーザー2', 'U987654321');

-- サンプル活動
INSERT INTO activities (
    member_id, 
    activity_type, 
    title, 
    description,
    activity_date, 
    event_name,
    participant_count,
    like_count,
    resource_url,
    slack_message_id
) VALUES (
    (SELECT member_id FROM members WHERE email = 'test1@example.com'),
    'event_presentation',
    'AWS初心者向けハンズオン講師',
    'EC2とVPCの基本的な使い方について、初心者向けにハンズオン形式で解説しました。参加者からは分かりやすいと好評でした。',
    '2025-01-15',
    'AWS Beginners Hands-on',
    25,
    10,
    'https://speakerdeck.com/example/aws-beginners-handson',
    '1234567890.123456'
);
```

## 注意事項

1. **UUID型の使用**
   - PostgreSQLのUUID型を使用しています
   - `gen_random_uuid()`関数でランダムなUUIDを生成

2. **タイムゾーン対応**
   - `TIMESTAMP WITH TIME ZONE`を使用して、タイムゾーンを考慮した日時を保存

3. **NULL許可**
   - `participant_count`と`like_count`はNULL許可（未取得の場合）
   - アプリ側で「未取得」と表示する処理が必要

4. **インデックス設計**
   - 検索パフォーマンスを考慮したインデックスを設定
   - 特にカレンダー表示用の日付インデックスは重要

5. **データ整合性**
   - 外部キー制約で参照整合性を保証
   - CHECK制約で不正な値の挿入を防止
