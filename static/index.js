document.addEventListener('DOMContentLoaded', function() {
    const questionInput = document.getElementById('question');
    const submitBtn = document.getElementById('submit-btn');
    const loading = document.querySelector('.loading');
    const results = document.getElementById('results');
    const errorMessage = document.getElementById('error-message');
    const aiAnswer = document.getElementById('ai-answer');
    const productsList = document.getElementById('products-list');
    const faqsList = document.getElementById('faqs-list');
    const productsSection = document.getElementById('products-section');
    const faqsSection = document.getElementById('faqs-section');
    const aiAnswerSection = document.getElementById('ai-answer-section');
    
    // Enterキーで送信
    questionInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            submitQuestion();
        }
    });
    
    // ボタンクリックで送信
    submitBtn.addEventListener('click', submitQuestion);
    
    function submitQuestion() {
        const question = questionInput.value.trim();
        
        if (!question) {
            showError('質問を入力してください。');
            return;
        }
        
        // UI更新: ローディング表示
        submitBtn.disabled = true;
        loading.style.display = 'block';
        errorMessage.style.display = 'none';
        
        // すべてのセクションを一度リセット
        results.style.display = 'none';
        aiAnswerSection.style.display = 'none';
        productsSection.style.display = 'none';
        faqsSection.style.display = 'none';
        
        // ステップ1: 関連商品とFAQを先に取得（高速）
        fetch('/search', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ question: question })
        })
        .then(response => {
            if (!response.ok) {
                throw new Error('商品とFAQの検索中にエラーが発生しました。');
            }
            return response.json();
        })
        .then(data => {
            // UI更新: 結果の一部表示
            results.style.display = 'flex';
            
            // AI回答部分にローディング表示
            aiAnswer.innerHTML = '<div class="ai-loading"><i class="fas fa-spinner"></i> AIが回答を生成中...</div>';
            aiAnswerSection.style.display = 'block';
            
            // 商品リスト表示
            if (data.products && data.products.length > 0) {
                displayProducts(data.products);
                productsSection.style.display = 'block';
            } else {
                productsSection.style.display = 'none';
            }
            
            // FAQリスト表示
            if (data.faqs && data.faqs.length > 0) {
                displayFAQs(data.faqs);
                faqsSection.style.display = 'block';
            } else {
                faqsSection.style.display = 'none';
            }
            
            // ステップ2: AIの回答を取得（時間がかかる処理）
            return fetch('/answer', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ question: question })
            });
        })
        .then(response => {
            if (!response.ok) {
                throw new Error('AI回答の生成中にエラーが発生しました。');
            }
            return response.json();
        })
        .then(data => {
            // AIの回答を表示
            aiAnswer.textContent = data.answer || 'AIからの回答がありません。';
            
            // ローディング完了
            loading.style.display = 'none';
            submitBtn.disabled = false;
        })
        .catch(error => {
            loading.style.display = 'none';
            submitBtn.disabled = false;
            showError(error.message);
        });
    }
    
    function displayProducts(products) {
        productsList.innerHTML = '';
        if (!products || products.length === 0) return;
        
        products.forEach(product => {
            const productItem = document.createElement('div');
            productItem.className = 'result-item';
            
            const name = document.createElement('div');
            name.className = 'product-name';
            name.textContent = product.商品名;
            
            const description = document.createElement('div');
            description.className = 'product-description';
            description.textContent = product.説明 || '説明がありません';
            
            const score = document.createElement('div');
            score.className = 'score';
            score.textContent = `関連スコア: ${product.スコア}`;
            
            productItem.appendChild(name);
            productItem.appendChild(description);
            productItem.appendChild(score);
            productsList.appendChild(productItem);
        });
    }
    
    function displayFAQs(faqs) {
        faqsList.innerHTML = '';
        if (!faqs || faqs.length === 0) return;
        
        faqs.forEach(faq => {
            const faqItem = document.createElement('div');
            faqItem.className = 'result-item';
            
            const question = document.createElement('div');
            question.className = 'faq-question';
            question.textContent = `Q: ${faq.question}`;
            
            const answer = document.createElement('div');
            answer.className = 'faq-answer';
            answer.textContent = `A: ${faq.answer}`;
            
            const score = document.createElement('div');
            score.className = 'score';
            score.textContent = `関連スコア: ${faq.スコア}`;
            
            faqItem.appendChild(question);
            faqItem.appendChild(answer);
            faqItem.appendChild(score);
            faqsList.appendChild(faqItem);
        });
    }
    
    function showError(message) {
        errorMessage.textContent = message;
        errorMessage.style.display = 'block';
        loading.style.display = 'none';
        submitBtn.disabled = false;
    }
});