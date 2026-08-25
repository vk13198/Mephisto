const socket = io();
let pnlChart = null;

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    initChart();
    loadPortfolio();
    loadTrades();
    loadNews();
    loadStatus();
    
    // Event listeners
    document.getElementById('btn-start').addEventListener('click', startBot);
    document.getElementById('btn-stop').addEventListener('click', stopBot);
    document.getElementById('btn-refresh').addEventListener('click', refreshAll);
    document.getElementById('btn-ask').addEventListener('click', askAI);
    document.getElementById('ai-question').addEventListener('keypress', (e) => {
        if (e.key === 'Enter') askAI();
    });
    document.getElementById('manual-trade-form').addEventListener('submit', placeManualTrade);
});

// Socket events
socket.on('connect', () => {
    console.log('Connected to server');
    addChatMessage('system', 'Connected to trading server');
});

socket.on('market_tick', (data) => {
    updateMarketTicks(data.ticks);
});

socket.on('portfolio_update', (data) => {
    updatePortfolio(data);
});

socket.on('new_trade', (data) => {
    addChatMessage('system', `New ${data.signal.type} signal on ${data.signal.symbol} @ ₹${data.signal.price}`);
    loadTrades();
    loadOpenPositions();
});

socket.on('trade_closed', (data) => {
    addChatMessage('system', `Trade closed: ${data.reason} @ ₹${data.exit_price}`);
    loadTrades();
    loadOpenPositions();
});

socket.on('news_update', (news) => {
    updateNews(news);
});

// Bot controls
async function startBot() {
    try {
        const res = await fetch('/api/bot/start', { method: 'POST' });
        const data = await res.json();
        if (data.status === 'started') {
            document.getElementById('bot-status').textContent = 'RUNNING';
            document.getElementById('bot-status').className = 'badge running';
            document.getElementById('btn-start').disabled = true;
            document.getElementById('btn-stop').disabled = false;
            addChatMessage('system', 'Bot started! Monitoring: ' + data.symbols.join(', '));
        }
    } catch (e) {
        alert('Failed to start bot: ' + e.message);
    }
}

async function stopBot() {
    try {
        const res = await fetch('/api/bot/stop', { method: 'POST' });
        const data = await res.json();
        if (data.status === 'stopped') {
            document.getElementById('bot-status').textContent = 'STOPPED';
            document.getElementById('bot-status').className = 'badge stopped';
            document.getElementById('btn-start').disabled = false;
            document.getElementById('btn-stop').disabled = true;
        }
    } catch (e) {
        alert('Failed to stop bot: ' + e.message);
    }
}

// Data loading
async function loadPortfolio() {
    try {
        const res = await fetch('/api/portfolio');
        const data = await res.json();
        updatePortfolio(data);
    } catch (e) { console.error(e); }
}

async function loadTrades() {
    try {
        const res = await fetch('/api/trades');
        const data = await res.json();
        renderTrades(data.trades);
    } catch (e) { console.error(e); }
}

async function loadOpenPositions() {
    try {
        const res = await fetch('/api/open_positions');
        const data = await res.json();
        renderPositions(data);
    } catch (e) { console.error(e); }
}

async function loadNews() {
    try {
        const res = await fetch('/api/news');
        const data = await res.json();
        updateNews(data.news);
        if (data.sentiment) {
            const badge = document.getElementById('sentiment-badge');
            badge.textContent = data.sentiment.sentiment;
            badge.className = 'badge ' + data.sentiment.sentiment.toLowerCase();
        }
    } catch (e) { console.error(e); }
}

async function loadStatus() {
    try {
        const res = await fetch('/api/bot/status');
        const data = await res.json();
        document.getElementById('bot-status').textContent = data.running ? 'RUNNING' : 'STOPPED';
        document.getElementById('bot-status').className = 'badge ' + (data.running ? 'running' : 'stopped');
        document.getElementById('trading-mode').textContent = data.mode;
        document.getElementById('trading-mode').className = 'badge ' + (data.mode === 'PAPER' ? 'paper' : 'live');
    } catch (e) { console.error(e); }
}

// Rendering
function updatePortfolio(data) {
    document.getElementById('total-value').textContent = '₹' + data.total_value.toLocaleString('en-IN');
    document.getElementById('cash').textContent = '₹' + data.cash.toLocaleString('en-IN');
    document.getElementById('day-pnl').textContent = '₹' + data.day_pnl.toLocaleString('en-IN');
    document.getElementById('day-pnl').className = 'value ' + (data.day_pnl >= 0 ? 'positive' : 'negative');
    document.getElementById('returns-pct').textContent = data.returns_pct + '%';
    document.getElementById('returns-pct').className = 'value ' + (data.returns_pct >= 0 ? 'positive' : 'negative');
    document.getElementById('open-positions').textContent = data.open_positions;
    document.getElementById('today-trades').textContent = data.today_trades + '/4';
    document.getElementById('display-capital').textContent = data.initial_capital.toLocaleString('en-IN');
}

function updateMarketTicks(ticks) {
    const container = document.getElementById('market-ticks');
    if (container.querySelector('.empty')) container.innerHTML = '';
    
    ticks.forEach(tick => {
        const div = document.createElement('div');
        div.className = 'tick-item';
        div.innerHTML = `
            <span><strong>${tick.instrument_token}</strong></span>
            <span>₹${tick.last_price.toFixed(2)}</span>
            <span class="${tick.change > 0 ? 'positive' : 'negative'}">
                ${tick.change > 0 ? '+' : ''}${tick.change?.toFixed(2) || '0.00'}
            </span>
        `;
        container.prepend(div);
        if (container.children.length > 20) container.lastChild.remove();
    });
}

function renderPositions(positions) {
    const container = document.getElementById('positions-list');
    if (!positions.length) {
        container.innerHTML = '<p class="empty">No open positions</p>';
        return;
    }
    container.innerHTML = positions.map(p => `
        <div class="position-item">
            <div><strong>${p.symbol}</strong> ${p.trade_type}</div>
            <div>Entry: ₹${p.entry_price}</div>
            <div>Qty: ${p.quantity}</div>
            <div>SL: ₹${p.stop_loss}</div>
            <div>TP1: ₹${p.take_profit_1}</div>
        </div>
    `).join('');
}

function renderTrades(trades) {
    const container = document.getElementById('trades-list');
    if (!trades.length) {
        container.innerHTML = '<p class="empty">No trades yet</p>';
        return;
    }
    container.innerHTML = trades.map(t => `
        <div class="trade-item">
            <span><strong>${t.symbol}</strong></span>
            <span class="${t.trade_type === 'LONG' ? 'positive' : 'negative'}">${t.trade_type}</span>
            <span>₹${t.net_pnl.toFixed(2)}</span>
            <span class="${t.net_pnl >= 0 ? 'positive' : 'negative'}">${t.status}</span>
        </div>
    `).join('');
}

function updateNews(news) {
    const container = document.getElementById('news-list');
    if (!news.length) {
        container.innerHTML = '<p class="empty">No news available</p>';
        return;
    }
    container.innerHTML = news.slice(0, 10).map(n => `
        <div class="news-item">
            <h4><a href="${n.url}" target="_blank">${n.title}</a></h4>
            <p>${n.description || ''}</p>
            <div class="meta">${n.source} • ${new Date(n.published).toLocaleString()}</div>
        </div>
    `).join('');
}

// AI Assistant
async function askAI() {
    const input = document.getElementById('ai-question');
    const question = input.value.trim();
    if (!question) return;
    
    addChatMessage('user', question);
    input.value = '';
    
    try {
        const res = await fetch('/api/ask', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ question })
        });
        const data = await res.json();
        addChatMessage('assistant', data.answer);
    } catch (e) {
        addChatMessage('assistant', 'Sorry, I am unable to answer right now.');
    }
}

function addChatMessage(role, text) {
    const container = document.getElementById('chat-history');
    const div = document.createElement('div');
    div.className = 'chat-message ' + role;
    div.innerHTML = `<p>${text.replace(/\n/g, '<br>')}</p>`;
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
}

// Manual Trade
async function placeManualTrade(e) {
    e.preventDefault();
    const data = {
        symbol: document.getElementById('manual-symbol').value,
        type: document.getElementById('manual-type').value,
        price: parseFloat(document.getElementById('manual-price').value),
        quantity: parseInt(document.getElementById('manual-qty').value),
        stop_loss: parseFloat(document.getElementById('manual-sl').value),
        take_profit_1: parseFloat(document.getElementById('manual-tp1').value)
    };
    
    try {
        const res = await fetch('/api/manual_trade', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        const result = await res.json();
        if (result.status === 'success') {
            alert('Manual trade placed successfully!');
            loadOpenPositions();
        } else {
            alert('Error: ' + (result.error || 'Unknown error'));
        }
    } catch (e) {
        alert('Failed to place trade: ' + e.message);
    }
}

// Chart
function initChart() {
    const ctx = document.getElementById('pnl-chart').getContext('2d');
    pnlChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: 'Portfolio Value',
                data: [],
                borderColor: '#3b82f6',
                backgroundColor: 'rgba(59, 130, 246, 0.1)',
                fill: true,
                tension: 0.4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                y: { grid: { color: '#334155' }, ticks: { color: '#94a3b8' } },
                x: { grid: { color: '#334155' }, ticks: { color: '#94a3b8' } }
            }
        }
    });
}

function refreshAll() {
    loadPortfolio();
    loadTrades();
    loadOpenPositions();
    loadNews();
    loadStatus();
}
