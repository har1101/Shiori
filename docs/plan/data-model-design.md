# データモデル設計

## データモデル設計の基本的な考え方

データモデル設計では、以下の点を考慮します：

1. **エンティティ（実体）の洗い出し**
   - システムで管理する「もの」を特定する
   - 例：活動、メンバー、レポート

2. **属性の定義**
   - 各エンティティが持つ情報を定義
   - 例：活動には「タイトル」「日時」「種別」がある

3. **関係性の定義**
   - エンティティ間の関連を明確にする
   - 例：「メンバー」は複数の「活動」を持つ（1対多）

4. **検索パターンの考慮**
   - どのような検索が必要かを考える
   - インデックスの設計に影響

## Jr.Champions活動可視化アプリのエンティティ

### 1. メンバー（Members）

```yaml
- member_id: 一意識別子（UUID）
- email: メールアドレス（ユニーク）
- name: 表示名
- slack_user_id: SlackのユーザーID
- created_at: 登録日時
- updated_at: 更新日時
```

### 2. 活動（Activities）

```yaml
- activity_id: 一意識別子（UUID）
- member_id: 投稿したメンバーのID（外部キー）
- activity_type: 活動種別（event_presentation, article, study_group, other）
- title: タイトル
- description: 詳細説明（100-200文字の要約）
- activity_date: 活動日時
- event_name: 参加イベント名（該当する場合）
- participant_count: 参加者数（NULL許可）
- like_count: いいね数（NULL許可）
- resource_url: 資料・記事のURL
- slack_message_id: 元のSlackメッセージID（重複チェック用）
- slack_channel_id: 投稿されたチャンネルID
- slack_timestamp: Slackでの投稿時刻
- created_at: DB登録日時
- updated_at: 更新日時
```

### 3. 月次レポート（MonthlyReports）

```yaml
- report_id: 一意識別子（UUID）
- year: 年（2025など）
- month: 月（1-12）
- total_activities: 総活動数
- activities_by_type: 種別ごとの活動数（JSON）
  例: {"event_presentation": 5, "article": 10, ...}
- total_participants: 総参加者数
- total_likes: 総いいね数
- feedback_content: フィードバック内容（Markdown）
- community_contribution: コミュニティ貢献度分析（Markdown）
- created_at: レポート生成日時
```

### 4. 処理履歴（ProcessingHistory）

```yaml
- history_id: 一意識別子（UUID）
- process_type: 処理種別（slack_fetch, report_generation）
- last_processed_at: 最終処理日時
- last_slack_timestamp: 最後に処理したSlackメッセージの時刻
- status: 処理状態（success, failed）
- error_message: エラーメッセージ（失敗時）
- created_at: 記録日時
```

## 重複チェックの仕組み

あなたの提案通り、最終取得時刻を記録する方法で実装します：

1. **ProcessingHistory**テーブルで`last_slack_timestamp`を管理
2. 次回実行時は、この時刻以降のメッセージのみを取得
3. さらに、**Activities**テーブルの`slack_message_id`でも重複チェック（念のため）

## Aurora DSQLでのテーブル作成時の考慮点

1. **主キー**：各テーブルに一意のIDを設定
2. **インデックス**：検索パターンに応じて設定
   - member_idでの検索（メンバー別一覧）
   - activity_dateでの範囲検索（カレンダー表示）
   - activity_typeでの検索（種別フィルタ）
3. **外部キー制約**：データの整合性を保つ

## 質問

1. この設計で必要な情報は網羅できていますか？
→OKです
2. 活動の「詳細説明（description）」はどの程度の文字数を想定していますか？
→登壇資料・ブログの内容を確認して、簡単に要約するようなイメージです。文字数としては100~200文字くらいで簡潔にまとめたいです。
3. いいね数や参加者数が取得できなかった場合、0として保存？それともNULL？
→Nullか空欄にして、その場合には「未取得」などを表示するようにしたいです(アプリ皮の処理)
4. 将来的に追加したい属性はありますか？（後から追加は可能ですが、初期設計で考慮した方が良いものがあれば）
→ひとまず今はOKです
