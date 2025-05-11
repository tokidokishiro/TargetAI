from flask import Flask, render_template, request, jsonify
import json
from dotenv import load_dotenv
import os
import threading

app = Flask(__name__)

# グローバル変数
products = []
faqs = []
tokenizer = None
model = None

# .env ファイルをロード
load_dotenv()

# データファイルのパス設定
PRODUCTS_FILE = "G&D.json"
FAQS_FILE = "Q&A.json"

# バックグラウンドで重い処理を行うための関数
def load_resources():
    global products, faqs, tokenizer, model
    
    # 1. データファイルの読み込み
    products = load_products_from_file(PRODUCTS_FILE)
    faqs = load_faqs_from_file(FAQS_FILE)
    
    # 2. Janomeのトークナイザーを遅延ロード
    from janome.tokenizer import Tokenizer
    tokenizer = Tokenizer()
    
    # 3. Gemini APIの設定
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
    if GEMINI_API_KEY:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('models/gemini-2.5-pro-exp-03-25')
    else:
        print("警告: .env ファイルに GEMINI_API_KEY が設定されていません。")

# JSONファイルから商品データを読み込み
def load_products_from_file(filename):
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"商品データ読み込みエラー: {e}")
        return []

# FAQデータ読み込み
def load_faqs_from_file(filename):
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"FAQデータ読み込みエラー: {e}")
        return []

# ユーザーの質問からキーワードを抽出
def extract_keywords(text):
    global tokenizer
    
    # トークナイザーが読み込まれていない場合
    if tokenizer is None:
        # 簡易的なキーワード抽出（緊急時用）
        return [word for word in text.split() if len(word) > 1]
    
    return list({token.surface for token in tokenizer.tokenize(text)
                if token.part_of_speech.split(',')[0] in ["名詞", "形容詞"]})

# 商品群から関連性の高い商品を抽出
def find_related_products(user_question, score_threshold=2, top_n=3):
    global products
    keywords = extract_keywords(user_question)
    results = []

    for product in products:
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
            results.append({**product, "スコア": score})

    # スコア順に並べて上位top_n＋同スコアまで抽出
    sorted_results = sorted(results, key=lambda x: x["スコア"], reverse=True)
    if not sorted_results:
        return []

    top_score = sorted_results[min(top_n - 1, len(sorted_results) - 1)]["スコア"]
    return [r for r in sorted_results if r["スコア"] >= top_score]

# FAQデータから関連Q&Aを抽出
def find_related_faqs(user_question, score_threshold=5, top_n=2, score_gap_threshold=5):
    global faqs
    keywords = extract_keywords(user_question)
    results = []

    for faq in faqs:
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
            results.append({**faq, "スコア": score})

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
    global model
    
    if model is None:
        return "AIモデルがロードされていないため、回答を生成できません。しばらくお待ちください。"
        
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
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        return f"回答生成中にエラーが発生しました: {e}"

# アプリの準備状態を示す変数
app_ready = False

# Flask 2.3.0以降では before_first_request が削除されたため、
# 代わりに with app.app_context() を使用するか、別の方法を採用します
# 以下のコードは特定のBlueprint用ではなく、アプリ全体に適用されます

def init_app(app):
    global app_ready
    # アプリが初期化されるときに呼ばれる関数
    if not app_ready:
        app_ready = True
        # バックグラウンドスレッドで重い処理を実行
        threading.Thread(target=load_resources, daemon=True).start()

@app.route('/')
def index():
    global app_ready, products, faqs
    
    # リソースがまだロードされていない場合
    if not app_ready and not products and not faqs:
        init_app(app)
    
    return render_template('index.html')

@app.route('/status')
def status():
    """リソースのロード状態を確認するAPI"""
    global tokenizer, model, products, faqs
    
    resources_loaded = {
        'tokenizer': tokenizer is not None,
        'model': model is not None,
        'products': len(products) > 0,
        'faqs': len(faqs) > 0
    }
    
    all_loaded = all(resources_loaded.values())
    
    return jsonify({
        'ready': all_loaded,
        'resources': resources_loaded
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
    
    # リソースがまだロードされていない場合
    global products, faqs
    if not products or not faqs:
        return jsonify({
            'loading': True,
            'message': 'データをロード中です。しばらくお待ちください。'
        })
    
    # 関連商品と関連FAQを検索
    related_products = find_related_products(user_question)
    related_faqs = find_related_faqs(user_question)
    
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
    
    # リソースがまだロードされていない場合
    global model
    if model is None:
        return jsonify({
            'loading': True,
            'message': 'AIモデルをロード中です。しばらくお待ちください。'
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

# 元のエンドポイントも残しておく（互換性のため）
@app.route('/ask', methods=['POST'])
def ask_question():
    data = request.get_json()
    user_question = data.get('question', '')
    
    if not user_question:
        return jsonify({
            'error': '質問が入力されていません。'
        })
    
    # リソースがまだロードされていない場合
    global model, products, faqs
    if model is None or not products or not faqs:
        return jsonify({
            'loading': True,
            'message': 'システムをロード中です。しばらくお待ちください。'
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
    # アプリケーション起動前に非同期でリソースのロードを開始
    init_app(app)
    
    # デバッグモードで実行（本番環境では debug=False にすること、でないときはTrue）
    app.run(debug=True)
    #app.run(host="0.0.0.0", debug=False)