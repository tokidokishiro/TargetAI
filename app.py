from flask import Flask, render_template, request, jsonify
import json
from dotenv import load_dotenv
import os
import time

app = Flask(__name__)

# グローバル変数 - メモリ使用量を最小化するため必要なときだけロード
products = None
faqs = None
tokenizer = None
model = None

# .env ファイルをロード
load_dotenv()

# データファイルのパス設定
PRODUCTS_FILE = "G&D.json"
FAQS_FILE = "Q&A.json"

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
            print(f"商品データ読み込みエラー: {e}")
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
            print(f"FAQデータ読み込みエラー: {e}")
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
            print(f"トークナイザー初期化エラー: {e}")
            
    return tokenizer

# 必要なときだけGeminiモデルを初期化
def get_model():
    global model, resources_initialized
    
    if model is None and not resources_initialized['model']:
        GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
        if GEMINI_API_KEY:
            try:
                import google.generativeai as genai
                genai.configure(api_key=GEMINI_API_KEY)
                # API呼び出しのみを行うため、モデル参照だけを保持（メモリ効率化）
                model = genai.GenerativeModel('models/gemini-2.5-pro-exp-03-25')
                resources_initialized['model'] = True
            except Exception as e:
                print(f"Geminiモデル初期化エラー: {e}")
        else:
            print("警告: .env ファイルに GEMINI_API_KEY が設定されていません。")
            
    return model

# ユーザーの質問からキーワードを抽出 - メモリ使用量を削減
def extract_keywords(text):
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
    keywords = extract_keywords(user_question)
    products_data = get_products()
    results = []

    for product in products_data:
        combined_text = (
            f"{product.get('商品名', '')} "
            f"{product.get('説明', '')} "
            f"{product.get('その他', '')}"
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
    keywords = extract_keywords(user_question)
    faqs_data = get_faqs()
    results = []

    for faq in faqs_data:
        combined_text = (
            f"{faq.get('question', '')} "
            f"{faq.get('answer', '')} "
            f"{' '.join(faq.get('related_word', []))}"
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
    model_instance = get_model()
    
    if model_instance is None:
        return "AIモデルがロードされていないため、回答を生成できません。"
        
    if not related_items:
        return "関連情報が見つかりませんでした。"

    context = ""
    for item in related_items:
        if "商品名" in item:
            context += f"商品名: {item['商品名']}, 説明: {item.get('説明', '')}, その他: {item.get('その他', '')}\n"
        elif "question" in item:
            context += f"質問: {item['question']}, 回答: {item['answer']}\n"

    prompt = f"""以下の関連情報に基づいて、質問「{question}」への回答を生成してください。\n\n{context}\n\n回答:"""

    try:
        # メモリ使用量を減らすためにストリーミング処理は避ける
        response = model_instance.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        return f"回答生成中にエラーが発生しました: {e}"

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/status')
def status():
    """リソースのロード状態を確認するAPI"""
    global resources_initialized
    
    return jsonify({
        'ready': True,  # 常にTrueを返す（遅延ロード方式に変更）
        'resources': resources_initialized
    })

@app.route('/search', methods=['POST'])
def search():
    """関連商品とFAQだけを返すエンドポイント"""
    data = request.get_json()
    user_question = data.get('question', '')
    
    if not user_question:
        return jsonify({
            'error': '質問が入力されていません。'
        })
    
    # 関連商品と関連FAQを検索
    start_time = time.time()
    related_products = find_related_products(user_question)
    related_faqs = find_related_faqs(user_question)
    
    print(f"検索処理時間: {time.time() - start_time:.2f}秒")
    
    return jsonify({
        'products': related_products,
        'faqs': related_faqs
    })

@app.route('/answer', methods=['POST'])
def get_answer():
    """AIの回答を生成するエンドポイント"""
    data = request.get_json()
    user_question = data.get('question', '')
    
    if not user_question:
        return jsonify({
            'error': '質問が入力されていません。'
        })
    
    # 関連情報を取得
    related_products = find_related_products(user_question)
    related_faqs = find_related_faqs(user_question)
    all_related = related_products + related_faqs
    
    # Geminiによる回答生成
    ai_answer = generate_answer_gemini(user_question, all_related)
    
    return jsonify({
        'answer': ai_answer
    })

@app.route('/ask', methods=['POST'])
def ask_question():
    data = request.get_json()
    user_question = data.get('question', '')
    
    if not user_question:
        return jsonify({
            'error': '質問が入力されていません。'
        })
    
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

if __name__ == '__main__':
    # ポート設定（環境変数から取得、なければデフォルト5000）
    port = int(os.environ.get('PORT', 5000))
    
    # 本番環境ではデバッグモードをオフに
    is_debug = os.environ.get('FLASK_ENV') == 'development'
    
    app.run(host="0.0.0.0", port=port, debug=is_debug)