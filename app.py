from flask import Flask, render_template, request, jsonify
import json
from janome.tokenizer import Tokenizer
import google.generativeai as genai
import os
from dotenv import load_dotenv

app = Flask(__name__)

# .env ファイルをロード
load_dotenv()

# 環境変数から Gemini APIキーを読み込む
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# APIキーが存在しない場合はエラーメッセージを用意
if not GEMINI_API_KEY:
    print("警告: .env ファイルに GEMINI_API_KEY が設定されていません。")

# Gemini APIの設定（APIキーがある場合のみ）
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('models/gemini-2.5-pro-exp-03-25')

# --- 関数定義 ---

# ① ユーザーの質問からキーワードを抽出
def extract_keywords(text):
    t = Tokenizer()
    return list({token.surface for token in t.tokenize(text)
                    if token.part_of_speech.split(',')[0] in ["名詞", "形容詞"]})

# ② 商品群から関連性の高い商品を抽出
def find_related_products(user_question, products, score_threshold=2, top_n=3):
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

# ③ JSONファイルから商品データを読み込み
def load_products_from_file(filename):
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"商品データ読み込みエラー: {e}")
        return []

# ④ FAQデータから関連Q&Aを抽出
def find_related_faqs(user_question, faqs, score_threshold=5, top_n=2, score_gap_threshold=5):
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

# FAQデータ読み込み
def load_faqs_from_file(filename):
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"FAQデータ読み込みエラー: {e}")
        return []

# --- Geminiを使用した回答生成関数 ---
def generate_answer_gemini(question, related_items):
    if not GEMINI_API_KEY:
        return "Gemini APIキーが設定されていないため、回答を生成できません。"
        
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

# データファイルのパス設定
PRODUCTS_FILE = "G&D.json"
FAQS_FILE = "Q&A.json"

# アプリケーション初期化時にデータを読み込む
products = load_products_from_file(PRODUCTS_FILE)
faqs = load_faqs_from_file(FAQS_FILE)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/search', methods=['POST'])
def search():
    """関連商品とFAQだけを高速に返すエンドポイント"""
    data = request.get_json()
    user_question = data.get('question', '')
    
    if not user_question:
        return jsonify({
            'error': '質問が入力されていません。'
        })
    
    # 関連商品と関連FAQを検索
    related_products = find_related_products(user_question, products)
    related_faqs = find_related_faqs(user_question, faqs)
    
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
    
    # 関連情報を再度取得（または前のステップの結果をキャッシュしてもよい）
    related_products = find_related_products(user_question, products)
    related_faqs = find_related_faqs(user_question, faqs)
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
    
    # 関連商品と関連FAQを検索
    related_products = find_related_products(user_question, products)
    related_faqs = find_related_faqs(user_question, faqs)
    
    # Geminiによる回答生成
    all_related = related_products + related_faqs
    ai_answer = generate_answer_gemini(user_question, all_related)
    
    return jsonify({
        'products': related_products,
        'faqs': related_faqs,
        'answer': ai_answer
    })

if __name__ == '__main__':
    if not products:
        print(f"警告: 商品データファイル '{PRODUCTS_FILE}' が読み込めませんでした。")
    if not faqs:
        print(f"警告: FAQデータファイル '{FAQS_FILE}' が読み込めませんでした。")
    
    # デバッグモードで実行（本番環境では debug=False にすること）
    app.run(debug=True)