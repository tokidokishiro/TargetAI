document.addEventListener('DOMContentLoaded', function() {
    const questionInput = document.getElementById('question');
    const searchBtn = document.getElementById('search-btn');
    const loadingElement = document.getElementById('loading');
    const resultElement = document.getElementById('result');
    
    // セクション展開/折りたたみのイベントリスナーを追加する関数
    function addToggleListeners() {
        document.querySelectorAll('.toggle-section').forEach(button => {
            // 既存のリスナーを削除して重複を防ぐ
            button.removeEventListener('click', toggleSectionHandler);
            button.addEventListener('click', toggleSectionHandler);
        });
    }
    
    // セクション展開/折りたたみのハンドラー
    function toggleSectionHandler() {
        const targetSection = document.getElementById(this.dataset.target);
        const isCollapsed = targetSection.classList.contains('collapsed');
        
        if (isCollapsed) {
            targetSection.classList.remove('collapsed');
            this.textContent = this.textContent.replace('▼', '▲');
        } else {
            targetSection.classList.add('collapsed');
            this.textContent = this.textContent.replace('▲', '▼');
        }
    }
    
    // システム状態を定期的に確認
    checkSystemStatus();
    const statusInterval = setInterval(checkSystemStatus, 3000);
    
    // markedライブラリをロード
    loadMarkedLibrary();
    
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
            // 1. まず検索結果を素早く表示
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
                // 既存の結果の上に追加
                const currentContent = resultElement.innerHTML;
                resultElement.innerHTML = `
                    <div class="section answer-section">
                        <h3>AI回答</h3>
                        <p>${answerData.message}</p>
                    </div>
                    ${currentContent}
                `;
                hideLoading();
                return;
            }
            
            // マークダウンをHTMLに変換
            const convertedAnswer = window.marked ? window.marked.parse(answerData.answer) : answerData.answer;
            
            // AI回答を先に表示
            const currentContent = resultElement.innerHTML;
            resultElement.innerHTML = `
                <div class="section answer-section">
                    <h3>AI回答</h3>
                    <div class="markdown-content">${convertedAnswer}</div>
                </div>
                ${currentContent}
            `;
            
            // シンタックスハイライトの適用（もしPrismを使用する場合）
            if (window.Prism) {
                Prism.highlightAllUnder(document.querySelector('.markdown-content'));
            }
            
            // トグルボタンのイベントリスナーを再追加
            addToggleListeners();
            
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
                        ${product.その他 ? `<p class="other-info"><small>${product.その他}</small></p>` : ''}
                        ${product.リンク ? `<p class="product-link"><a href="${product.リンク}" target="_blank">公式ストアへ遷移</a></p>` : ''}
                    </div>
                `;
            });
            
            // 商品名のリストを作成（最大3つまで表示）
            const productNames = data.products.map(product => product.商品名).slice(0, 3).join('、');
            const moreProducts = data.products.length > 3 ? '...' : '';
            
            resultsHTML += `
                <div class="section">
                    <h3>
                        <button class="toggle-section" data-target="products-section">
                            関連商品 (${data.products.length}件): ${productNames}${moreProducts} ▼
                        </button>
                    </h3>
                    <div id="products-section" class="section-content collapsed">
                        ${productsHTML}
                    </div>
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
                        ${faq.related_links ? `<p class="faq-link"><a href="${faq.related_links}" target="_blank">公式ストアへ遷移</a></p>` : ''}
                    </div>
                `;
            });
            
            // FAQ質問のリストを作成（最大3つまで表示）
            const faqQuestions = data.faqs.map(faq => faq.question).slice(0, 3).join('、');
            const moreFaqs = data.faqs.length > 3 ? '...' : '';
            
            resultsHTML += `
                <div class="section">
                    <h3>
                        <button class="toggle-section" data-target="faqs-section">
                            関連FAQ (${data.faqs.length}件): ${faqQuestions}${moreFaqs} ▼
                        </button>
                    </h3>
                    <div id="faqs-section" class="section-content collapsed">
                        ${faqsHTML}
                    </div>
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
        
        resultElement.innerHTML += resultsHTML;
        
        // 初回のトグルボタンイベントリスナー追加
        addToggleListeners();
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
    
    // marked.jsライブラリをロードする関数
    function loadMarkedLibrary() {
        if (window.marked) return; // 既にロードされている場合は何もしない
        
        const script = document.createElement('script');
        script.src = 'https://cdnjs.cloudflare.com/ajax/libs/marked/4.3.0/marked.min.js';
        script.onload = function() {
            console.log('Marked.js library loaded');
            // マークダウンオプションの設定
            window.marked.setOptions({
                breaks: true,       // 改行をbrタグに変換
                gfm: true,          // GitHub Flavored Markdown
                headerIds: true,    // ヘッダーにIDを付与
                sanitize: false     // sanitizeはdeprecatedだが、念のため明示的に無効化
            });
        };
        document.head.appendChild(script);
        
        // シンタックスハイライトのためのPrism.jsを追加（オプション）
        const prismCSS = document.createElement('link');
        prismCSS.rel = 'stylesheet';
        prismCSS.href = 'https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/themes/prism.min.css';
        document.head.appendChild(prismCSS);
        
        const prismScript = document.createElement('script');
        prismScript.src = 'https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/prism.min.js';
        document.head.appendChild(prismScript);
        
        // マークダウンのスタイルを追加
        addMarkdownStyles();
    }
    
    // マークダウンコンテンツのスタイルを追加
    function addMarkdownStyles() {
        // styleタグではなく既存CSSに統合するため、不要になりました
        // マークダウンのスタイルはCSSに統合済みです
    }
});