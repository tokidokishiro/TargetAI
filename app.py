from flask import Flask, render_template, request, jsonify, session
import json
from dotenv import load_dotenv
import os
import time
import secrets
import logging
import re
from logging.handlers import RotatingFileHandler
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import html

app = Flask(__name__)

# セキュリティ設定
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', secrets.token_hex(32))  # 強力な秘密鍵を設定
csrf = CSRFProtect(app)  # CSRF保護を有効化

# レート制限の設定
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["100 per day", "20 per hour", "5 per minute"],
    storage_uri="memory://",
)

# ロギングの設定
if not app.debug:
    if not os.path.exists('logs'):
        os.mkdir('logs')
    file_handler = RotatingFileHandler('logs/app.log', maxBytes=10240, backupCount=10)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    file_handler.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)
    app.logger.setLevel(logging.INFO)
    app.logger.info('アプリケーションの起動')

# グローバル変数 - メモリ使用量を最小化するため必要なときだけロード
products = None
faqs = None
tokenizer = None
model = None

# .env ファイルをロード
load_dotenv()

# データファイルのパス設定 - パスインジェクション対策
PRODUCTS_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "G&D.json"))
FAQS_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "Q&A.json"))

# アプリの準備状態 - lazily initialize resources
resources_initialized = {
    'products': False,
    'faqs': False,
    'tokenizer': False,
    'model': False
}

# メモリ効率のため、必要なときだけJSONファイルから商品データを読み込み
def get_products():
    global products, resources_initialized
    
    if products is None and not resources_initialized['products']:
        try:
            with open(PRODUCTS_FILE, "r", encoding="utf-8") as f:
                products = json.load(f)
            resources_initialized['products'] = True
        except Exception as e:
            app.logger.error(f"商品データ読み込みエラー: {e}")
            products = []
            
    return products or []

# メモリ効率のため、必要なときだけFAQデータ読み込み
def get_faqs():
    global faqs, resources_initialized
    
    if faqs is None and not resources_initialized['faqs']:
        try:
            with open(FAQS_FILE, "r", encoding="utf-8") as f:
                faqs = json.load(f)
            resources_initialized['faqs'] = True
        except Exception as e:
            app.logger.error(f"FAQデータ読み込みエラー: {e}")
            faqs = []
            
    return faqs or []

# 必要なときだけトークナイザーを初期化
def get_tokenizer():
    global tokenizer, resources_initialized
    
    if tokenizer is None and not resources_initialized['tokenizer']:
        try:
            # ライブラリのインポートを遅延させてメモリ使用量を削減
            from janome.tokenizer import Tokenizer
            # メモリ効率化のためユーザー辞書なしの軽量モードで初期化
            tokenizer = Tokenizer(mmap=True)
            resources_initialized['tokenizer'] = True
        except Exception as e:
            app.logger.error(f"トークナイザー初期化エラー: {e}")
            
    return tokenizer

# 必要なときだけGeminiモデルを初期化
def get_model():
    global model, resources_initialized
    
    if model is None and not resources_initialized['model']:
        # APIキーをより安全に取得
        GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
        if GEMINI_API_KEY:
            try:
                import google.generativeai as genai
                genai.configure(api_key=GEMINI_API_KEY)
                # API呼び出しのみを行うため、モデル参照だけを保持（メモリ効率化）
                model = genai.GenerativeModel('models/gemma-3-27b-it')
                resources_initialized['model'] = True
            except Exception as e:
                app.logger.error(f"Geminiモデル初期化エラー: {e}")
        else:
            app.logger.warning("警告: .env ファイルに GEMINI_API_KEY が設定されていません。")
            
    return model

# 入力検証関数 - インジェクション攻撃対策
def validate_user_input(text):
    """ユーザー入力を検証し、安全な形に変換する"""
    if not text or not isinstance(text, str):
        return ""
    
    # 不要な文字を削除
    text = text.strip()
    
    # 長さ制限 (1000文字まで)
    if len(text) > 1000:
        text = text[:1000]
    
    # HTMLエスケープ処理
    text = html.escape(text)
    
    # コマンドインジェクション対策のパターン検出
    dangerous_patterns = [
        r';.*',           # セミコロン以降のコマンド
        r'`.*`',          # バッククォートコマンド
        r'\$\(.*\)',      # $(コマンド)
        r'\|.*',          # パイプ以降のコマンド
        r'&&.*',          # 論理AND以降のコマンド
        r'>.*',           # リダイレクト
        r'<.*',           # 入力リダイレクト
    ]
    
    for pattern in dangerous_patterns:
        if re.search(pattern, text):
            app.logger.warning(f"危険な入力パターンを検出: {text}")
            return ""
    
    return text

# ユーザーの質問からキーワードを抽出 - メモリ使用量を削減
def extract_keywords(text):
    # 入力検証
    text = validate_user_input(text)
    if not text:
        return []
    
    # トークナイザーが使えない場合はシンプルな方法で
    tokenizer = get_tokenizer()
    if tokenizer is None:
        # 簡易的なキーワード抽出（軽量実装）
        important_words = []
        for word in text.split():
            if len(word) > 1:  # 短すぎる単語を除外
                important_words.append(word)
        return important_words
    
    # Janomeでキーワード抽出（名詞と形容詞のみ）
    keywords = []
    for token in tokenizer.tokenize(text):
        pos = token.part_of_speech.split(',')[0]
        if pos in ["名詞", "形容詞"] and len(token.surface) > 1:
            keywords.append(token.surface)
    
    # 結果をセットにして重複排除してからリストに変換
    return list(set(keywords))

# 商品群から関連性の高い商品を抽出
def find_related_products(user_question, score_threshold=2, top_n=3):
    # 入力検証
    user_question = validate_user_input(user_question)
    if not user_question:
        return []
    
    keywords = extract_keywords(user_question)
    products_data = get_products()
    results = []

    for product in products_data:
        combined_text = (
            f"{product.get('商品名', '')} "
            f"{product.get('説明', '')} "
            f"{product.get('その他', '')}"
            f"{product.get('リンク', '')}"
        )

        score = 0
        for kw in keywords:
            if kw in product.get('商品名', ''):
                score += 5
            elif kw in combined_text:
                score += 2

        if score >= score_threshold:
            # 必要な情報だけをコピーしてメモリ使用量を削減
            results.append({
                "商品名": product.get("商品名", ""),
                "説明": product.get("説明", ""),
                "その他": product.get("その他", ""),
                "リンク": product.get("リンク", ""),  # リンクを結果に含める
                "スコア": score
            })

    # スコア順に並べて上位top_n＋同スコアまで抽出
    sorted_results = sorted(results, key=lambda x: x["スコア"], reverse=True)
    if not sorted_results:
        return []

    top_score = sorted_results[min(top_n - 1, len(sorted_results) - 1)]["スコア"]
    return [r for r in sorted_results if r["スコア"] >= top_score]

# FAQデータから関連Q&Aを抽出
def find_related_faqs(user_question, score_threshold=5, top_n=2, score_gap_threshold=5):
    # 入力検証
    user_question = validate_user_input(user_question)
    if not user_question:
        return []
    
    keywords = extract_keywords(user_question)
    faqs_data = get_faqs()
    results = []

    for faq in faqs_data:
        combined_text = (
            f"{faq.get('question', '')} "
            f"{faq.get('answer', '')} "
            f"{' '.join(faq.get('related_word', []))}"
            f"{faq.get('related_links', '')} "
        )

        score = 0
        for kw in keywords:
            if kw in faq.get("question", ""):
                score += 5
            if kw in faq.get("answer", ""):
                score += 4
            elif kw in combined_text:
                score += 3

        if score >= score_threshold:
            # 必要な情報だけをコピーしてメモリ使用量を削減
            results.append({
                "question": faq.get("question", ""),
                "answer": faq.get("answer", ""),
                "related_links": faq.get("related_links", ""),  # 関連リンクを結果に含める
                "スコア": score
            })

    # スコア順に並べる
    sorted_results = sorted(results, key=lambda x: x["スコア"], reverse=True)
    if not sorted_results:
        return []
    
    # 最高スコアと2番目のスコアの差を確認
    if len(sorted_results) > 1:
        top_score = sorted_results[0]["スコア"]
        second_score = sorted_results[1]["スコア"]
        
        # スコアの差が閾値を超えている場合、最高スコアのみを返す
        if (top_score - second_score) >= score_gap_threshold:
            return [sorted_results[0]]
    
    # そうでなければ、元の処理を行う
    top_score = sorted_results[min(top_n - 1, len(sorted_results) - 1)]["スコア"]
    return [r for r in sorted_results if r["スコア"] >= top_score]

# Geminiを使用した回答生成関数
def generate_answer_gemini(question, related_items):
    # 入力検証
    question = validate_user_input(question)
    if not question:
        return "無効な質問入力です。"
    
    model_instance = get_model()
    
    if model_instance is None:
        return "AIモデルがロードされていないため、回答を生成できません。"
        
    if not related_items:
        return "関連情報が見つかりませんでした。"

    # 関連情報をサニタイズして前処理
    context = ""
    for item in related_items:
        if "商品名" in item:
            context += f"商品名: {html.escape(item.get('商品名', ''))}, "
            context += f"説明: {html.escape(item.get('説明', ''))}, "
            context += f"その他: {html.escape(item.get('その他', ''))}\n"
        elif "question" in item:
            context += f"質問: {html.escape(item.get('question', ''))}, "
            context += f"回答: {html.escape(item.get('answer', ''))}\n"

    # プロンプトインジェクション対策
    safe_prompt = f"""以下の関連情報に基づいて、質問「{question}」への回答を生成してください。\n\n{context}\n\n回答:"""

    try:
        # メモリ使用量を減らすためにストリーミング処理は避ける
        response = model_instance.generate_content(safe_prompt)
        return response.text.strip()
    except Exception as e:
        app.logger.error(f"回答生成中にエラーが発生しました: {e}")
        return "回答の生成中にエラーが発生しました。しばらく経ってからもう一度お試しください。"

@app.before_request
def before_request():
    """リクエスト前の共通処理 - セキュリティヘッダーの設定など"""
    # 初回アクセス時にセッション初期化
    if 'visits' not in session:
        session['visits'] = 0
    session['visits'] += 1

@app.after_request
def after_request(response):
    """レスポンス後の共通処理 - セキュリティヘッダーの設定"""
    # セキュリティヘッダー設定
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    # CDNJSからのリソース読み込みを許可するようにCSPを修正
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com; style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com; font-src 'self' https://cdnjs.cloudflare.com"
    return response

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/status')
@limiter.limit("30 per minute")  # レート制限
def status():
    """リソースのロード状態を確認するAPI"""
    global resources_initialized
    
    return jsonify({
        'ready': True,  # 常にTrueを返す（遅延ロード方式に変更）
        'resources': resources_initialized
    })

@app.route('/search', methods=['POST'])
@csrf.exempt  # API呼び出しはCSRF対策を免除
@limiter.limit("10 per minute")  # レート制限
def search():
    """関連商品とFAQだけを返すエンドポイント"""
    # Content-Typeの検証
    if not request.is_json:
        app.logger.warning("不正なContent-Type")
        return jsonify({
            'error': '無効なリクエスト形式です。JSON形式でリクエストしてください。'
        }), 400
    
    data = request.get_json()
    if not data:
        return jsonify({
            'error': '無効なJSONデータです。'
        }), 400
    
    user_question = data.get('question', '')
    
    # 入力検証
    user_question = validate_user_input(user_question)
    if not user_question:
        return jsonify({
            'error': '質問が入力されていないか、無効な入力です。'
        }), 400
    
    try:
        # 関連商品と関連FAQを検索
        start_time = time.time()
        related_products = find_related_products(user_question)
        related_faqs = find_related_faqs(user_question)
        
        app.logger.info(f"検索処理時間: {time.time() - start_time:.2f}秒")
        
        return jsonify({
            'products': related_products,
            'faqs': related_faqs
        })
    except Exception as e:
        app.logger.error(f"検索処理エラー: {e}")
        return jsonify({
            'error': '検索処理中にエラーが発生しました。'
        }), 500

@app.route('/answer', methods=['POST'])
@csrf.exempt  # API呼び出しはCSRF対策を免除
@limiter.limit("5 per minute")  # レート制限
def get_answer():
    """AIの回答を生成するエンドポイント"""
    # Content-Typeの検証
    if not request.is_json:
        app.logger.warning("不正なContent-Type")
        return jsonify({
            'error': '無効なリクエスト形式です。JSON形式でリクエストしてください。'
        }), 400
    
    data = request.get_json()
    if not data:
        return jsonify({
            'error': '無効なJSONデータです。'
        }), 400
    
    user_question = data.get('question', '')
    
    # 入力検証
    user_question = validate_user_input(user_question)
    if not user_question:
        return jsonify({
            'error': '質問が入力されていないか、無効な入力です。'
        }), 400
    
    try:
        # 関連情報を取得
        related_products = find_related_products(user_question)
        related_faqs = find_related_faqs(user_question)
        all_related = related_products + related_faqs
        
        # Geminiによる回答生成
        ai_answer = generate_answer_gemini(user_question, all_related)
        
        return jsonify({
            'answer': ai_answer
        })
    except Exception as e:
        app.logger.error(f"回答生成エラー: {e}")
        return jsonify({
            'error': '回答生成中にエラーが発生しました。'
        }), 500

@app.route('/ask', methods=['POST'])
@csrf.exempt  # API呼び出しはCSRF対策を免除
@limiter.limit("5 per minute")  # レート制限
def ask_question():
    # Content-Typeの検証
    if not request.is_json:
        app.logger.warning("不正なContent-Type")
        return jsonify({
            'error': '無効なリクエスト形式です。JSON形式でリクエストしてください。'
        }), 400
    
    data = request.get_json()
    if not data:
        return jsonify({
            'error': '無効なJSONデータです。'
        }), 400
    
    user_question = data.get('question', '')
    
    # 入力検証
    user_question = validate_user_input(user_question)
    if not user_question:
        return jsonify({
            'error': '質問が入力されていないか、無効な入力です。'
        }), 400
    
    try:
        # 関連商品と関連FAQを検索
        related_products = find_related_products(user_question)
        related_faqs = find_related_faqs(user_question)
        
        # Geminiによる回答生成
        all_related = related_products + related_faqs
        ai_answer = generate_answer_gemini(user_question, all_related)
        
        return jsonify({
            'products': related_products,
            'faqs': related_faqs,
            'answer': ai_answer
        })
    except Exception as e:
        app.logger.error(f"質問処理エラー: {e}")
        return jsonify({
            'error': '質問処理中にエラーが発生しました。'
        }), 500

# エラーハンドラー
@app.errorhandler(404)
def not_found_error(error):
    return jsonify({'error': 'ページが見つかりません'}), 404

@app.errorhandler(500)
def internal_error(error):
    app.logger.error(f"内部サーバーエラー: {error}")
    return jsonify({'error': 'サーバー内部エラーが発生しました'}), 500

@app.errorhandler(429)
def ratelimit_error(error):
    app.logger.warning(f"レート制限超過: {error}")
    return jsonify({'error': 'リクエスト頻度が高すぎます。しばらく経ってからもう一度お試しください。'}), 429

if __name__ == '__main__':
    # 本番環境のセキュリティ設定
    port = int(os.environ.get('PORT', 5000))
    #production, development
    is_debug = os.environ.get('FLASK_ENV') == 'development'
    
    # より安全な設定で起動
    if not is_debug:
        app.config['SESSION_COOKIE_SECURE'] = True  # HTTPS接続のみでクッキーを送信
        app.config['SESSION_COOKIE_HTTPONLY'] = True  # JavaScriptからのクッキーアクセスを防止
        app.config['PERMANENT_SESSION_LIFETIME'] = 1800  # セッションの有効期限を30分に設定
    
    app.run(host="0.0.0.0", port=port, debug=is_debug)