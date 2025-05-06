
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
        results.style.display = 'none';
        errorMessage.style.display = 'none';
        
        // APIリクエスト
        fetch('/ask', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ question: question })
        })
        .then(response => {
            if (!response.ok) {
                throw new Error('サーバーエラーが発生しました。');
            }
            return response.json();
        })
        .then(data => {
            // UI更新: 結果表示
            loading.style.display = 'none';
            submitBtn.disabled = false;
            results.style.display = 'block';
            
            // AI回答表示
            aiAnswer.textContent = data.answer;
            
            // 商品リスト表示
            if (data.products && data.products.length > 0) {
                productsSection.style.display = 'block';
                displayProducts(data.products);
            } else {
                productsSection.style.display = 'none';
            }
            
            // FAQリスト表示
            if (data.faqs && data.faqs.length > 0) {
                faqsSection.style.display = 'block';
                displayFAQs(data.faqs);
            } else {
                faqsSection.style.display = 'none';
            }
        })
        .catch(error => {
            loading.style.display = 'none';
            submitBtn.disabled = false;
            showError(error.message);
        });
    }
    
    function displayProducts(products) {
        productsList.innerHTML = '';
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