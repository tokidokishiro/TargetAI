document.addEventListener('DOMContentLoaded', function() {
    const questionInput = document.getElementById('question');
    const searchBtn = document.getElementById('search-btn');
    const loadingElement = document.getElementById('loading');
    const resultElement = document.getElementById('result');
    
    // システム状態を定期的に確認
    checkSystemStatus();
    const statusInterval = setInterval(checkSystemStatus, 3000);
    
    searchBtn.addEventListener('click', async function() {
        const question = questionInput.value.trim();
        if (!question) {
            alert('質問を入力してください');
            return;
        }
        
        // 検索開始
        showLoading();
        resultElement.innerHTML = '';
        
        try {
            // 1. まず検索結果だけを素早く表示
            const searchResponse = await fetch('/search', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ question })
            });
            
            const searchData = await searchResponse.json();
            
            // ロード中の場合
            if (searchData.loading) {
                resultElement.innerHTML = `
                    <div class="section">
                        <h3>お待ちください</h3>
                        <p>${searchData.message}</p>
                    </div>
                `;
                hideLoading();
                return;
            }
            
            // 検索結果を表示
            displaySearchResults(searchData);
            
            // 2. 次にAI回答を取得（これは時間がかかる）
            const answerResponse = await fetch('/answer', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ question })
            });
            
            const answerData = await answerResponse.json();
            
            // ロード中の場合
            if (answerData.loading) {
                resultElement.innerHTML += `
                    <div class="section answer-section">
                        <h3>AI回答</h3>
                        <p>${answerData.message}</p>
                    </div>
                `;
                hideLoading();
                return;
            }
            
            // AI回答を表示
            displayAnswer(answerData);
            
        } catch (error) {
            console.error('Error:', error);
            resultElement.innerHTML = `
                <div class="section">
                    <h3>エラーが発生しました</h3>
                    <p>申し訳ありませんが、処理中にエラーが発生しました。</p>
                </div>
            `;
        } finally {
            hideLoading();
        }
    });
    
    function displaySearchResults(data) {
        let resultsHTML = '';
        
        // 商品情報の表示
        if (data.products && data.products.length > 0) {
            let productsHTML = '';
            data.products.forEach(product => {
                productsHTML += `
                    <div class="product-item">
                        <h4>${product.商品名}</h4>
                        <p>${product.説明 || ''}</p>
                        ${product.その他 ? `<p><small>${product.その他}</small></p>` : ''}
                    </div>
                `;
            });
            
            resultsHTML += `
                <div class="section">
                    <h3>関連商品</h3>
                    ${productsHTML}
                </div>
            `;
        }
        
        // FAQ情報の表示
        if (data.faqs && data.faqs.length > 0) {
            let faqsHTML = '';
            data.faqs.forEach(faq => {
                faqsHTML += `
                    <div class="faq-item">
                        <h4>${faq.question}</h4>
                        <p>${faq.answer}</p>
                    </div>
                `;
            });
            
            resultsHTML += `
                <div class="section">
                    <h3>関連FAQ</h3>
                    ${faqsHTML}
                </div>
            `;
        }
        
        // 検索結果がない場合
        if (!data.products?.length && !data.faqs?.length) {
            resultsHTML += `
                <div class="section">
                    <h3>検索結果</h3>
                    <p>関連する情報が見つかりませんでした。</p>
                </div>
            `;
        }
        
        resultElement.innerHTML = resultsHTML;
    }
    
    function displayAnswer(data) {
        const answerHTML = `
            <div class="section answer-section">
                <h3>AI回答</h3>
                <p>${data.answer}</p>
            </div>
        `;
        
        resultElement.innerHTML += answerHTML;
    }
    
    function showLoading() {
        loadingElement.classList.remove('hidden');
    }
    
    function hideLoading() {
        loadingElement.classList.add('hidden');
    }
    
    async function checkSystemStatus() {
        try {
            const response = await fetch('/status');
            const statusData = await response.json();
            
            updateStatusIndicator('products', statusData.resources.products);
            updateStatusIndicator('faqs', statusData.resources.faqs);
            updateStatusIndicator('tokenizer', statusData.resources.tokenizer);
            updateStatusIndicator('model', statusData.resources.model);
            
            // すべてのリソースがロードされたらステータスチェックを停止
            if (statusData.ready) {
                clearInterval(statusInterval);
                // 5秒後にステータス表示を非表示にする
                setTimeout(() => {
                    document.getElementById('system-status').classList.add('hidden');
                }, 5000);
            }
            
        } catch (error) {
            console.error('Status check error:', error);
        }
    }
    
    function updateStatusIndicator(resourceName, isLoaded) {
        const indicator = document.getElementById(`status-${resourceName}`);
        const text = document.getElementById(`status-${resourceName}-text`);
        
        if (isLoaded) {
            indicator.className = 'status-indicator status-loaded';
            text.textContent = '準備完了';
        } else {
            indicator.className = 'status-indicator status-loading';
            text.textContent = 'ロード中...';
        }
    }
});