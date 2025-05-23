# AI搭載 商品・FAQ検索システム

## はじめに

- 本アプリは、無印良品のコスメケア商品に関する情報を効率的に学習・比較できるように設計された **商品情報、FAQにおいてのAI回答システム** です。  
- アプリURL
  - https://target-ai-424163415875.asia-northeast1.run.app

## コンセプト

- 特定ブランド（無印良品）に特化することで、より高精度・高品質な回答を生成するシステムをつくること
- 商品データを差し替えることで、他ブランドへの転用も可能な汎用構成
- 個人的な学習目的としてスタートし、AIのニッチ領域への応用を検証

## アプリの流れ

- 質問を送信
- pythonで類似商品、類似FAQのスコア化
- スコア上位をユーザーとAIに提示
  - ユーザーはスコア上位結果を閲覧可能に
  - AIはこの間に質問とスコア上位結果をもとに回答を作成
- AIの回答作成後、ユーザーに提示



https://github.com/user-attachments/assets/058d9f70-663a-4065-910e-9c8032ff1c11






2025年5月16日撮影（コードの更新により、少し構成が変わっていることがあります。）

## 技術スタック

### バックエンド
- **Python 3.9** - コアプログラミング言語
- **Flask** - 軽量Webフレームワーク
- **Janome** - 日本語形態素解析器
- **Google Gemini AI** - 自然言語処理・回答生成

### フロントエンド
- **HTML5/CSS3** - レスポンシブUI設計
- **JavaScript (ES6+)** - フロントエンド制御
- **Font Awesome** - アイコンライブラリ

### セキュリティ対策
- **Flask-WTF** - CSRF保護
- **Flask-Limiter** - レート制限 (DDoS対策)
- **Content Security Policy** - XSS攻撃対策
- **入力検証システム** - インジェクション攻撃対策

### デプロイ・インフラ
- **Google Cloud Run** - コンテナベースの自動スケーリング運用・デプロイ
- **Docker** - アプリケーションのコンテナ化

## データソース

- 無印良品公式サイトより取得した商品情報を元に、独自に構造化（JSON形式）して使用

## 備考
このアプリは、AIの支援を受けながら個人で設計・開発・運用を行ったプロジェクトです。就職活動のポートフォリオとしても活用しています。

## 主な機能

### 1. インテリジェント検索システム
- 形態素解析を使用した高精度なキーワード抽出
- スコアリングアルゴリズムによる関連度の高い情報提示
- 商品情報・FAQ情報の統合検索

### 2. AIによる自然言語回答生成
- Google Geminiモデルを活用した高品質な回答生成
- ユーザー質問の意図理解と適切な情報提供

### 3. 最適化されたシステム設計
- 遅延ローディングによるメモリ使用量の最小化
- 段階的データ取得によるUXの向上
- スケーラブルな設計思想

### 4. セキュリティ強化機能
- 全ユーザー入力に対する厳格な検証と無害化
- XSS、CSRFなどの一般的な攻撃からの保護
- APIエンドポイント別レート制限による乱用防止

### 5. インタラクティブUI
- 折りたたみ式セクションによる情報の整理
- リアルタイムシステムステータス表示
- 非同期データ取得による高速レスポンス

## パフォーマンス最適化

- **リソースの遅延初期化**: 必要になるまでリソースをロードしないことでメモリ使用量を削減
- **2段階検索プロセス**: 高速検索結果の即時表示と詳細AI回答の段階的取得
- **効率的なデータ構造**: 必要な情報のみをクライアントに送信
- **キャッシュ戦略**: システムリソースの効率的な管理

## セキュリティ対策

- **入力検証システム**: 特殊文字のエスケープ処理と危険なパターンの検出
- **コンテンツセキュリティポリシー**: 許可されたソースからのリソースのみ読み込み
- **セキュアなセッション管理**: HTTPSによる暗号化とセッションタイムアウト
- **包括的なエラーハンドリング**: セキュリティ情報の漏洩防止
- **レート制限**: DDoS攻撃やブルートフォース攻撃からの保護

## システムアーキテクチャ

```
クライアント <--> Flask Webサーバー <--> データソース (JSON) <--> Google Gemini API
                       |
                       ↓
                 形態素解析エンジン
```

## 開発における工夫

1. **メモリ効率**: Google Cloudの無料枠でも効率的に動作するよう、必要なときだけリソースをロードする設計を採用しました。これにより、サーバーのメモリ使用量を大幅に削減しています。

2. **ユーザー体験の向上**: ユーザーが質問を入力してから回答が得られるまでの体験を最適化するため、まず関連情報を素早く表示し、その後AIによる詳細な回答を取得する2段階プロセスを実装しました。

3. **セキュリティ重視の設計**: すべてのユーザー入力に対して厳格な検証を行い、XSS、CSRF、インジェクション攻撃などから保護する包括的なセキュリティ対策を実装しました。

4. **エラー耐性**: 例外処理とログ記録を徹底し、予期せぬエラーが発生しても適切に対応できるロバストなシステムを構築しました。

## 今後の展望

- スコアの最適化による検索精度の継続的改善
  - この検索結果によってＡＩの回答精度が変わるため
  - 具体的にはスコアのつけ方の改善
- 質問の保存
  - ユーザーの質問を知ることによって、表示方法の改善が見込めるため
- AI回答の確認
  - AI回答の正当性を提示するため

## 開発者情報

**メール**: kojimadaichi27@gmail.com
**アプリURL**: https://target-ai-424163415875.asia-northeast1.run.app



---

本プロジェクトは、効率的なデータ処理、高度な自然言語処理、セキュアなWebアプリケーション開発のスキルを実証するものです。特に、限られたリソースで最大のパフォーマンスを発揮できるよう、多角的な最適化を行っている点が特徴です。
