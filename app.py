from flask import Flask, render_template, request, jsonify, session
import json
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
import gc  # ガベージコレクションを明示的に呼び出すため

app = Flask(__name__)

# セキュリティ設定
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', secrets.token_hex(32))  # 強力な秘密鍵を設定
csrf = CSRFProtect(app)  # CSRF保護を有効化

# キャッシュ制御 - 使用しないリソースをすぐに解放
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

# レート制限の設定
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["100 per day", "20 per hour", "5 per minute"],
    storage_uri="memory://",
)

# ロギングの設定 - ファイルサイズを小さく保つ
if not app.debug:
    if not os.path.exists('logs'):
        os.mkdir('logs')
    file_handler = RotatingFileHandler('logs/app.log', maxBytes=5120, backupCount=3)  # サイズと保持数を削減
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    file_handler.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)
    app.logger.setLevel(logging.INFO)
    app.logger.info('アプリケーションの起動')

# データファイルのパス設定 - パスインジェクション対策
PRODUCTS_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "G&D.json"))
FAQS_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "Q&A.json"))

# キャッシュとリソース管理
_cache = {
    'products': None,
    'faqs': None,
    'tokenizer': None,
    'model': None,
    'last_used': {
        'products': 0,
        'faqs': 0,
        'tokenizer': 0,
        'model': 0
    }
}

# 最大キャッシュ寿命（秒）
CACHE_TTL = 300  # 5分

# キャッシュ管理関数
def get_cached_resource(resource_name, loader_func):
    """タイムアウト付きキャッシュからリソースを取得する"""
    current_time = time.time()
    
    # TTLを超えたら自動でキャッシュを解放
    if _cache[resource_name] is not None:
        if current_time - _cache['last_used'][resource_name] > CACHE_TTL:
            app.logger.info(f"{resource_name}のキャッシュを解放します（TTL超過）")
            _cache[resource_name] = None
            gc.collect()  # メモリ解放を促進
    
    # 必要なら再ロード
    if _cache[resource_name] is None:
        try:
            _cache[resource_name] = loader_func()
            _cache['last_used'][resource_name] = current_time
        except Exception as e:
            app.logger.error(f"{resource_name}のロードに失敗: {e}")
            return None
    else:
        # 使用時刻を更新
        _cache['last_used'][resource_name] = current_time
    
    return _cache[resource_name]

# プロダクトデータをロードする関数
def load_products():
    try:
        with open(PRODUCTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        app.logger.error(f"商品データ読み込みエラー: {e}")
        return []

# FAQデータをロードする関数
def load_faqs():
    try:
        with open(FAQS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        app.logger.error(f"FAQデータ読み込みエラー: {e}")
        return []

# トークナイザーをロードする関数
def load_tokenizer():
    try:
        # 遅延インポート
        from janome.tokenizer import Tokenizer
        # メモリ効率化のため軽量モードで初期化
        return Tokenizer(mmap=True)
    except Exception as e:
        app.logger.error(f"トークナイザー初期化エラー: {e}")
        return None

# Geminiモデルをロードする関数
def load_model():
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
    if not GEMINI_API_KEY:
        app.logger.warning("警告: .env ファイルに GEMINI_API_KEY が設定されていません。")
        return None
        
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        # APIクライアント参照だけを保持
        return genai.GenerativeModel('models/gemma-3-27b-it')
    except Exception as e:
        app.logger.error(f"Geminiモデル初期化エラー: {e}")
        return None

# 必要なときだけデータを取得する関数
def get_products():
    return get_cached_resource('products', load_products)

def get_faqs():
    return get_cached_resource('faqs', load_faqs)

def get_tokenizer():
    return get_cached_resource('tokenizer', load_tokenizer)

def get_model():
    return get_cached_resource('model', load_model)

# メモリを解放する関数
def release_resources():
    """アイドル状態の時にメモリを解放するヘルパー関数"""
    global _cache
    
    for resource in ['products', 'faqs', 'tokenizer', 'model']:
        _cache[resource] = None
    
    gc.collect()
    app.logger.info("未使用リソースを解放しました")

# 入力検証関数 - インジェクション攻撃対策
def validate_user_input(text):
    """ユーザー入力を検証し、安全な形に変換する"""
    if not text or not isinstance(text, str):
        return ""
    
    # 不要な文字を削除
    text = text.strip()
    
    # 長さ制限 (1000文字まで - 元の制限に戻す)
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

# キーワード抽出の軽量実装
def extract_keywords_light(text):
    """トークナイザーを使わない軽量なキーワード抽出"""
    if not text:
        return []
    
    # ストップワード（日本語の一般的な助詞・助動詞など）
    stop_words = set(['は', 'を', 'が', 'の', 'に', 'と', 'で', 'した', 'です', 'ます', 'から', 'まで', 'など'])
    
    # 単語分割して、短すぎるものやストップワードを除外
    words = []
    for word in text.split():
        word = word.strip('.,!?()[]{}":;')
        if len(word) > 1 and word not in stop_words:
            words.append(word)
    
    # 重複を排除
    return list(set(words))

# ユーザーの質問からキーワードを抽出 - 遅延ロードと軽量実装
def extract_keywords(text):
    # 入力検証
    text = validate_user_input(text)
    if not text:
        return []
    
    # まず軽量実装を試す
    tokenizer = get_tokenizer()
    if tokenizer is None:
        return extract_keywords_light(text)
    
    # Janomeでキーワード抽出（名詞と形容詞のみ）
    keywords = []
    token_iter = tokenizer.tokenize(text)
    
    # イテレータを使って最大100トークンまでに制限
    count = 0
    for token in token_iter:
        count += 1
        if count > 100:  # トークン数制限
            break
            
        pos = token.part_of_speech.split(',')[0]
        if pos in ["名詞", "形容詞"] and len(token.surface) > 1:
            keywords.append(token.surface)
    
    # 結果をセットにして重複排除してからリストに変換（最大20キーワードまで）
    return list(set(keywords))[:20]  # キーワード数に上限を設定

# 商品群から関連性の高い商品を抽出 - 同スコアを含む抽出
def find_related_products(user_question, score_threshold=2, top_n=3):  # トップ商品数を3に戻す
    # 入力検証
    user_question = validate_user_input(user_question)
    if not user_question:
        return []
    
    keywords = extract_keywords(user_question)
    products_data = get_products()
    
    if not products_data or not keywords:
        return []
    
    results = []
    
    # 最大100商品までに制限
    product_count = 0
    for product in products_data:
        product_count += 1
        if product_count > 100:  # 商品数制限
            break
            
        # 必要な情報だけを抽出して処理
        product_name = product.get('商品名', '')
        product_desc = product.get('説明', '')
        product_other = product.get('その他', '')
        combined_text = f"{product_name} {product_desc} {product_other}"

        score = 0
        for kw in keywords:
            if kw in product_name:
                score += 5
            elif kw in combined_text:
                score += 2

        if score >= score_threshold:
            # 必要な情報だけをコピーしてメモリ使用量を削減
            results.append({
                "商品名": product_name,
                "説明": product_desc,
                "その他": product_other,
                "リンク": product.get("リンク", ""),
                "スコア": score
            })

    # スコア順に並べて上位top_n＋同スコアまで抽出
    sorted_results = sorted(results, key=lambda x: x["スコア"], reverse=True)
    if not sorted_results:
        return []
    
    # top_n個目までの最低スコアを取得
    if len(sorted_results) > top_n:
        min_top_score = sorted_results[top_n-1]["スコア"]
        final_results = [r for r in sorted_results if r["スコア"] >= min_top_score]
    else:
        final_results = sorted_results
    
    # メモリクリア
    results = None
    sorted_results = None
    gc.collect()
    
    return final_results

# FAQデータから関連Q&Aを抽出 - 同スコアを含む抽出
def find_related_faqs(user_question, score_threshold=5, top_n=2, score_gap_threshold=5):  # トップFAQ数を2に戻す
    # 入力検証
    user_question = validate_user_input(user_question)
    if not user_question:
        return []
    
    keywords = extract_keywords(user_question)
    faqs_data = get_faqs()
    
    if not faqs_data or not keywords:
        return []
    
    results = []
    
    # 最大50FAQまでに制限
    faq_count = 0
    for faq in faqs_data:
        faq_count += 1
        if faq_count > 50:  # FAQ数制限
            break
            
        # 必要な情報だけを抽出
        question = faq.get('question', '')
        answer = faq.get('answer', '')
        related_word = ' '.join(faq.get('related_word', []))
        related_links = faq.get('related_links', '')
        combined_text = f"{question} {answer} {related_word} {related_links}"

        score = 0
        for kw in keywords:
            if kw in question:
                score += 5
            if kw in answer:
                score += 4
            elif kw in combined_text:
                score += 3

        if score >= score_threshold:
            # 必要な情報だけをコピー
            results.append({
                "question": question,
                "answer": answer,
                "related_links": related_links,
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
            final_results = [sorted_results[0]]
        else:
            # そうでなければ、上位top_n＋同スコアまで抽出
            if len(sorted_results) > top_n:
                min_top_score = sorted_results[top_n-1]["スコア"]
                final_results = [r for r in sorted_results if r["スコア"] >= min_top_score]
            else:
                final_results = sorted_results
    else:
        final_results = sorted_results
    
    # メモリクリア
    results = None
    sorted_results = None
    gc.collect()
    
    return final_results

# Geminiを使用した回答生成関数 - テキスト長制限を解除
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
    # 最大8つの関連アイテムを使用
    for item in related_items[:8]:
        if "商品名" in item:
            context += f"商品: {html.escape(item.get('商品名', ''))}, "
            context += f"説明: {html.escape(item.get('説明', ''))}, "
            context += f"その他: {html.escape(item.get('その他', ''))}\n"
        elif "question" in item:
            context += f"質問: {html.escape(item.get('question', ''))}, "
            context += f"回答: {html.escape(item.get('answer', ''))}\n"

    # プロンプト
    safe_prompt = f"""以下の情報に基づいて「{question}」への回答を生成してください。\n\n{context}\n\n回答:"""

    try:
        # メモリ使用量を減らすためにストリーミング処理は避ける
        response = model_instance.generate_content(safe_prompt)
        result = response.text.strip()
        return result
    except Exception as e:
        app.logger.error(f"回答生成中にエラーが発生しました: {e}")
        return "回答の生成中にエラーが発生しました。しばらく経ってからもう一度お試しください。"
    finally:
        # 明示的なガベージコレクションを促す
        response = None
        gc.collect()

@app.before_request
def before_request():
    """リクエスト前の共通処理 - セキュリティヘッダーの設定など"""
    # 初回アクセス時にセッション初期化
    if 'visits' not in session:
        session['visits'] = 0
    session['visits'] += 1
    
    # 500回のリクエストごとにメモリリリースをトリガー
    if session['visits'] % 500 == 0:
        release_resources()

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
    # 現在のメモリ状態を確認
    resource_status = {
        'products': _cache['products'] is not None,
        'faqs': _cache['faqs'] is not None,
        'tokenizer': _cache['tokenizer'] is not None,
        'model': _cache['model'] is not None
    }
    
    return jsonify({
        'ready': True,  # 常にTrueを返す（遅延ロード方式）
        'resources': resource_status,
        'memory_management': 'active'
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
        
        processing_time = time.time() - start_time
        app.logger.info(f"検索処理時間: {processing_time:.2f}秒")
        
        # 処理時間が長すぎる場合、ガベージコレクションを実行
        if processing_time > 2.0:
            gc.collect()
        
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
        related_products = find_related_products(user_question, top_n=3)
        related_faqs = find_related_faqs(user_question, top_n=2)
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
        related_products = find_related_products(user_question, top_n=3)
        related_faqs = find_related_faqs(user_question, top_n=2)
        
        # Geminiによる回答生成
        all_related = related_products + related_faqs
        ai_answer = generate_answer_gemini(user_question, all_related)
        
        # 明示的なガベージコレクション
        gc.collect()
        
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

# メモリリリースエンドポイント - 管理用
@app.route('/memory/release', methods=['POST'])
@csrf.exempt
@limiter.limit("5 per minute")
def release_memory():
    """明示的にメモリを解放するエンドポイント"""
    try:
        release_resources()
        return jsonify({
            'status': 'success',
            'message': 'メモリを解放しました'
        })
    except Exception as e:
        app.logger.error(f"メモリ解放エラー: {e}")
        return jsonify({
            'error': 'メモリ解放中にエラーが発生しました'
        }), 500

# エラーハンドラー
@app.errorhandler(404)
def not_found_error(error):
    return jsonify({'error': 'ページが見つかりません'}), 404

@app.errorhandler(500)
def internal_error(error):
    app.logger.error(f"内部サーバーエラー: {error}")
    # エラー時にメモリを解放
    release_resources()
    return jsonify({'error': 'サーバー内部エラーが発生しました'}), 500

@app.errorhandler(429)
def ratelimit_error(error):
    app.logger.warning(f"レート制限超過: {error}")
    return jsonify({'error': 'リクエスト頻度が高すぎます。しばらく経ってからもう一度お試しください。'}), 429

if __name__ == '__main__':
    # 本番環境のセキュリティ設定
    port = int(os.environ.get('PORT', 5000))
    #production, development
    is_debug = os.environ.get('FLASK_ENV') == 'development'  # 修正：production でないときのみデバッグモード
    
    # より安全な設定で起動
    if not is_debug:
        app.config['SESSION_COOKIE_SECURE'] = True  # HTTPS接続のみでクッキーを送信
        app.config['SESSION_COOKIE_HTTPONLY'] = True  # JavaScriptからのクッキーアクセスを防止
        app.config['PERMANENT_SESSION_LIFETIME'] = 1800  # セッションの有効期限を30分に設定
    
    app.run(host="0.0.0.0", port=port, debug=is_debug)