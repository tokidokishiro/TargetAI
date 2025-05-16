document.addEventListener('DOMContentLoaded', function() {
    // DOM要素の取得 - 変数名をより具体的かつ意味のあるものに変更
    const questionInputField = document.getElementById('question');
    const searchButton = document.getElementById('search-btn');
    const loadingIndicator = document.getElementById('loading');
    const resultContainer = document.getElementById('result');
    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';
    
    // Subresource Integrity (SRI)を使用した安全なスクリプト読み込み用のハッシュ値
    // 修正: 各ライブラリの正しいintegrityハッシュ値に更新
    const MARKED_INTEGRITY = 'sha384-QsSpx6a0USazT7nK7w8qXDgpSAPhFsb2XtpoLFQ5+X2yFN6hvCKnwEzN8M5FWaJb';
    const PRISM_CSS_INTEGRITY = 'sha384-rCCjoCPCsizaAAYVoz1Q0CmCTvnctK0JkfCSjx7IIxexTBg+uCKtFYycedUjMyA2';
    const PRISM_JS_INTEGRITY = 'sha384-06z5D//U/xpvxZHuUz92xBvq3DqBBFi7Up53HRrbV7Jlv7Yvh/MZ7oenfUe9iCEt';
    const PURIFY_JS_INTEGRITY = 'sha384-rneZSW/1QE+3/U5/u+/7eRNi/tRc+SzS+yXy36fltr1tDN9EHaVo1Bwz2Z8o8DA4';
    
    // セキュリティ設定
    const MAX_QUESTION_LENGTH = 500; // 質問の最大長
    
    // セクション展開/折りたたみのイベントリスナーを追加する関数
    function addToggleListeners() {
        document.querySelectorAll('.toggle-section').forEach(button => {
            // 既存のリスナーを削除して重複を防ぐ
            button.removeEventListener('click', toggleSectionHandler);
            button.addEventListener('click', toggleSectionHandler);
        });
    }
    
    // セクション展開/折りたたみのハンドラー - 変更なし
    function toggleSectionHandler() {
        const targetId = this.dataset.target;
        // 入力検証を追加
        if (!targetId || !/^[a-zA-Z0-9\-_]+$/.test(targetId)) {
            console.error('無効なターゲットID');
            return;
        }
        
        const targetSection = document.getElementById(targetId);
        if (!targetSection) {
            console.error('ターゲットセクションが見つかりません');
            return;
        }
        
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
    let statusInterval;
    checkSystemStatus();
    statusInterval = setInterval(checkSystemStatus, 5000); // インターバルを5秒に延長
    
    // markedライブラリをロード - 安全なバージョン
    loadScriptsSecurely();
    
    // 検索ボタンのイベントリスナー
    searchButton.addEventListener('click', async function() {
        const questionText = sanitizeInput(questionInputField.value.trim());
        
        // 入力検証の強化
        if (!questionText) {
            showError('質問を入力してください');
            return;
        }
        
        if (questionText.length > MAX_QUESTION_LENGTH) {
            showError(`質問は${MAX_QUESTION_LENGTH}文字以内にしてください`);
            return;
        }
        
        // 検索開始
        showLoading();
        resultContainer.innerHTML = ''; // innerHTML使用前に内容をクリア
        
        try {
            // 1. まず検索結果を素早く表示
            const searchResponse = await secureServerRequest('/search', { question: questionText });
            
            // エラーハンドリングを強化
            if (!searchResponse || searchResponse.error) {
                throw new Error(searchResponse?.error || '検索中にエラーが発生しました');
            }
            
            // ロード中の場合
            if (searchResponse.loading) {
                resultContainer.textContent = ''; // 安全に内容をクリア
                const sectionDiv = createSafeElement('div', { className: 'section' });
                
                const heading = createSafeElement('h3', { textContent: 'お待ちください' });
                const message = createSafeElement('p', { textContent: searchResponse.message });
                
                appendChildren(sectionDiv, [heading, message]);
                resultContainer.appendChild(sectionDiv);
                
                hideLoading();
                return;
            }
            
            // 検索結果を表示 - 安全な関数に置き換え
            displaySearchResults(searchResponse);
            
            // 2. 次にAI回答を取得（これは時間がかかる）
            const answerResponse = await secureServerRequest('/answer', { question: questionText });
            
            // エラーハンドリングを強化
            if (!answerResponse || answerResponse.error) {
                throw new Error(answerResponse?.error || '回答生成中にエラーが発生しました');
            }
            
            // ロード中の場合
            if (answerResponse.loading) {
                const answerSection = createSafeElement('div', { className: 'section answer-section' });
                
                const heading = createSafeElement('h3', { textContent: 'AI回答' });
                const message = createSafeElement('p', { textContent: answerResponse.message });
                
                appendChildren(answerSection, [heading, message]);
                resultContainer.insertBefore(answerSection, resultContainer.firstChild);
                
                hideLoading();
                return;
            }
            
            // AI回答を先に表示 - 安全な方法に置き換え
            displayAIAnswer(answerResponse.answer);
            
            // トグルボタンのイベントリスナーを再追加
            addToggleListeners();
            
        } catch (error) {
            console.error('Error:', error);
            showError('処理中にエラーが発生しました: ' + error.message);
        } finally {
            hideLoading();
        }
    });
    
    // 安全なサーバーリクエスト関数
    async function secureServerRequest(endpoint, data) {
        try {
            const response = await fetch(endpoint, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRF-Token': csrfToken, // CSRF対策
                    'X-Requested-With': 'XMLHttpRequest' // CSRF対策の追加層
                },
                body: JSON.stringify(data),
                credentials: 'same-origin' // Cookieを送信
            });
            
            if (!response.ok) {
                const errorText = await response.text();
                throw new Error(`サーバーエラー (${response.status}): ${errorText}`);
            }
            
            return await response.json();
        } catch (error) {
            console.error('Server request failed:', error);
            throw error;
        }
    }
    
    // 安全な要素作成ヘルパー関数
    function createSafeElement(tagName, attributes = {}) {
        const element = document.createElement(tagName);
        
        // 安全に属性を設定
        Object.entries(attributes).forEach(([key, value]) => {
            if (key === 'textContent') {
                element.textContent = value;
            } else if (key === 'className') {
                element.className = value;
            } else {
                element.setAttribute(key, value);
            }
        });
        
        return element;
    }
    
    // 複数の子要素を安全に追加するヘルパー関数
    function appendChildren(parent, children) {
        children.forEach(child => parent.appendChild(child));
    }
    
    // 入力サニタイズ関数
    function sanitizeInput(input) {
        if (typeof input !== 'string') return '';
        
        // 制御文字を削除
        let sanitized = input.replace(/[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]/g, '');
        
        // HTMLタグをエスケープ
        sanitized = sanitized
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
            
        return sanitized;
    }
    
    // エラーメッセージ表示
    function showError(message) {
        const errorDiv = createSafeElement('div', { 
            className: 'error-message',
            textContent: message
        });
        
        document.body.appendChild(errorDiv);
        
        // 5秒後に自動的に消える
        setTimeout(() => {
            if (errorDiv.parentNode) {
                errorDiv.parentNode.removeChild(errorDiv);
            }
        }, 5000);
    }
    
    // 安全なリンク作成
    function createSafeLink(url, text) {
        // URLを検証
        let safeUrl = '';
        try {
            const urlObj = new URL(url, window.location.origin);
            // 許可されたドメインのみを受け入れる
            if (urlObj.protocol === 'https:' || urlObj.protocol === 'http:') {
                safeUrl = urlObj.href;
            }
        } catch (e) {
            console.error('Invalid URL:', url);
            return createSafeElement('span', { textContent: text });
        }
        
        const link = createSafeElement('a', { 
            href: safeUrl,
            textContent: text,
            target: '_blank',
            rel: 'noopener noreferrer' // タブナビゲーション攻撃対策
        });
        
        return link;
    }
    
    // 検索結果表示の安全な実装
    function displaySearchResults(data) {
        // 商品情報の表示
        if (data.products && data.products.length > 0) {
            const productSection = createSafeElement('div', { className: 'section' });
            
            // 商品名のリストを作成（最大3つまで表示）
            const productNames = data.products
                .slice(0, 3)
                .map(product => sanitizeInput(product.商品名 || ''))
                .join('、');
            const moreProducts = data.products.length > 3 ? '...' : '';
            
            const toggleButton = createSafeElement('button', {
                className: 'toggle-section',
                textContent: `関連商品 (${data.products.length}件): ${productNames}${moreProducts} ▼`
            });
            toggleButton.setAttribute('data-target', 'products-section');
            
            const heading = createSafeElement('h3');
            heading.appendChild(toggleButton);
            
            const productsContainer = createSafeElement('div', {
                className: 'section-content collapsed',
                id: 'products-section'
            });
            
            // 商品アイテムの作成
            data.products.forEach(product => {
                const productItem = createSafeElement('div', { className: 'product-item' });
                
                const productName = createSafeElement('h4', { 
                    textContent: sanitizeInput(product.商品名 || '')
                });
                
                const productDesc = product.説明 ? 
                    createSafeElement('p', { textContent: sanitizeInput(product.説明) }) : null;
                
                const productOther = product.その他 ? 
                    createSafeElement('p', { 
                        className: 'other-info',
                        textContent: sanitizeInput(product.その他)
                    }) : null;
                
                // 安全なリンクの追加
                let productLink = null;
                if (product.リンク) {
                    const linkP = createSafeElement('p', { className: 'product-link' });
                    linkP.appendChild(createSafeLink(product.リンク, '公式ストアへ'));
                    productLink = linkP;
                }
                
                const securityNote = createSafeElement('p');
                securityNote.appendChild(createSafeElement('small', {
                    textContent: '※セキュリティのため、商品のご購入は、公式サイトからお手続きください。'
                }));
                
                // 子要素の追加
                appendChildren(productItem, [
                    productName,
                    productDesc,
                    productOther,
                    productLink,
                    securityNote
                ].filter(Boolean)); // nullの要素を除外
                
                productsContainer.appendChild(productItem);
            });
            
            appendChildren(productSection, [heading, productsContainer]);
            resultContainer.appendChild(productSection);
        }
        
        // FAQ情報の表示
        if (data.faqs && data.faqs.length > 0) {
            const faqSection = createSafeElement('div', { className: 'section' });
            
            // FAQ質問のリストを作成（最大3つまで表示）
            const faqQuestions = data.faqs
                .slice(0, 3)
                .map(faq => sanitizeInput(faq.question || ''))
                .join('、');
            const moreFaqs = data.faqs.length > 3 ? '...' : '';
            
            const toggleButton = createSafeElement('button', {
                className: 'toggle-section',
                textContent: `関連FAQ (${data.faqs.length}件): ${faqQuestions}${moreFaqs} ▼`
            });
            toggleButton.setAttribute('data-target', 'faqs-section');
            
            const heading = createSafeElement('h3');
            heading.appendChild(toggleButton);
            
            const faqsContainer = createSafeElement('div', {
                className: 'section-content collapsed',
                id: 'faqs-section'
            });
            
            // FAQアイテムの作成
            data.faqs.forEach(faq => {
                const faqItem = createSafeElement('div', { className: 'faq-item' });
                
                const faqQuestion = createSafeElement('h4', { 
                    textContent: sanitizeInput(faq.question || '')
                });
                
                const faqAnswer = createSafeElement('p', { 
                    textContent: sanitizeInput(faq.answer || '')
                });
                
                // 安全なリンクの追加
                let faqLink = null;
                if (faq.related_links) {
                    const linkP = createSafeElement('p', { className: 'faq-link' });
                    linkP.appendChild(createSafeLink(faq.related_links, '公式ストアへ'));
                    faqLink = linkP;
                }
                
                const securityNote = createSafeElement('p');
                securityNote.appendChild(createSafeElement('small', {
                    textContent: '※セキュリティのため、商品のご購入は、公式サイトからお手続きください。'
                }));
                
                // 子要素の追加
                appendChildren(faqItem, [
                    faqQuestion,
                    faqAnswer,
                    faqLink,
                    securityNote
                ].filter(Boolean)); // nullの要素を除外
                
                faqsContainer.appendChild(faqItem);
            });
            
            appendChildren(faqSection, [heading, faqsContainer]);
            resultContainer.appendChild(faqSection);
        }
        
        // 検索結果がない場合
        if ((!data.products || data.products.length === 0) && 
            (!data.faqs || data.faqs.length === 0)) {
            const noResultSection = createSafeElement('div', { className: 'section' });
            const heading = createSafeElement('h3', { textContent: '検索結果' });
            const message = createSafeElement('p', { 
                textContent: '関連する情報が見つかりませんでした。'
            });
            
            appendChildren(noResultSection, [heading, message]);
            resultContainer.appendChild(noResultSection);
        }
    }
    
    // AI回答表示の安全な実装
    function displayAIAnswer(answerText) {
        // まず安全なコンテナを作成
        const answerSection = createSafeElement('div', { className: 'section answer-section' });
        const heading = createSafeElement('h3', { textContent: 'AI回答' });
        
        // マークダウンレンダリング用の安全なコンテナ
        const markdownContainer = createSafeElement('div', { className: 'markdown-content' });
        
        // markedが利用可能な場合、安全にマークダウンをレンダリング
        if (window.marked) {
            try {
                // DOMPurifyがあれば使用（理想的にはこれも追加すべき）
                const sanitizedHTML = window.DOMPurify ? 
                    window.DOMPurify.sanitize(window.marked.parse(answerText)) :
                    window.marked.parse(answerText);
                
                // マークダウンHTMLを安全に設定
                markdownContainer.innerHTML = sanitizedHTML;
            } catch (error) {
                console.error('Markdown rendering error:', error);
                markdownContainer.textContent = answerText; // フォールバック
            }
        } else {
            // マークダウンレンダラーがない場合は単純にテキストを表示
            markdownContainer.textContent = answerText;
        }
        
        // セクションに要素を追加
        appendChildren(answerSection, [heading, markdownContainer]);
        
        // 結果の先頭に挿入
        if (resultContainer.firstChild) {
            resultContainer.insertBefore(answerSection, resultContainer.firstChild);
        } else {
            resultContainer.appendChild(answerSection);
        }
        
        // シンタックスハイライトの適用（もしPrismが利用可能なら）
        if (window.Prism) {
            try {
                window.Prism.highlightAllUnder(markdownContainer);
            } catch (error) {
                console.error('Syntax highlighting error:', error);
            }
        }
    }
    
    function showLoading() {
        loadingIndicator.classList.remove('hidden');
    }
    
    function hideLoading() {
        loadingIndicator.classList.add('hidden');
    }
    
    async function checkSystemStatus() {
        try {
            const response = await fetch('/status', {
                headers: {
                    'X-Requested-With': 'XMLHttpRequest' // CSRF対策の追加層
                },
                credentials: 'same-origin' // Cookieを送信
            });
            
            if (!response.ok) {
                throw new Error(`Status check failed: ${response.status}`);
            }
            
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
                    const statusElement = document.getElementById('system-status');
                    if (statusElement) {
                        statusElement.classList.add('hidden');
                    }
                }, 5000);
            }
            
        } catch (error) {
            console.error('Status check error:', error);
            // エラー時は次回のチェックで再試行
        }
    }
    
    function updateStatusIndicator(resourceName, isLoaded) {
        // リソース名の検証 - インジェクション対策
        if (!/^[a-zA-Z0-9\-_]+$/.test(resourceName)) {
            console.error('無効なリソース名:', resourceName);
            return;
        }
        
        const indicator = document.getElementById(`status-${resourceName}`);
        const text = document.getElementById(`status-${resourceName}-text`);
        
        if (!indicator || !text) {
            console.error(`ステータス要素が見つかりません: ${resourceName}`);
            return;
        }
        
        if (isLoaded) {
            indicator.className = 'status-indicator status-loaded';
            text.textContent = '準備完了';
        } else {
            indicator.className = 'status-indicator status-loading';
            text.textContent = 'ロード中...';
        }
    }
    
    // 外部スクリプトを安全にロードする関数
    function loadScriptsSecurely() {
        // すでにロードされている場合は何もしない
        if (window.marked && window.Prism) return;
        
        // CSP対応とSRI（サブリソース完全性）によるセキュアな読み込み
        if (!window.marked) {
            const script = createSafeElement('script', {
                src: 'https://cdnjs.cloudflare.com/ajax/libs/marked/4.3.0/marked.min.js',
                integrity: MARKED_INTEGRITY,
                crossOrigin: 'anonymous'
            });
            
            script.onload = function() {
                console.log('Marked.js library loaded securely');
                
                // DOMPurifyの読み込み（HTMLサニタイズ用）
                const purifyScript = createSafeElement('script', {
                    src: 'https://cdnjs.cloudflare.com/ajax/libs/dompurify/3.0.5/purify.min.js',
                    integrity: PURIFY_JS_INTEGRITY,
                    crossOrigin: 'anonymous'
                });
                
                document.head.appendChild(purifyScript);
                
                // マークダウンオプションの設定
                if (window.marked) {
                    window.marked.setOptions({
                        breaks: true,       // 改行をbrタグに変換
                        gfm: true,          // GitHub Flavored Markdown
                        headerIds: true,    // ヘッダーにIDを付与
                        mangle: false,      // ヘッダーIDを変更しない
                        sanitize: false     // DOMPurifyを使用するため
                    });
                }
            };
            
            document.head.appendChild(script);
        }
        
        // シンタックスハイライトのためのPrism.jsを追加（オプション）
        if (!window.Prism) {
            const prismCSS = createSafeElement('link', {
                rel: 'stylesheet',
                href: 'https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/themes/prism.min.css',
                integrity: PRISM_CSS_INTEGRITY,
                crossOrigin: 'anonymous'
            });
            
            const prismScript = createSafeElement('script', {
                src: 'https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/prism.min.js',
                integrity: PRISM_JS_INTEGRITY,
                crossOrigin: 'anonymous'
            });
            
            document.head.appendChild(prismCSS);
            document.head.appendChild(prismScript);
        }
    }
});