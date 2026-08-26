// static/js/market.js

const socket = io();

// Chart.js setup
const ctx = document.getElementById('chart').getContext('2d');
const chartData = { labels: [], datasets: [{ label: 'Price', data: [], borderColor: 'blue', tension: 0.2 }] };
const chart = new Chart(ctx, { type: 'line', data: chartData, options: { scales: { x: { type: 'time', time: { unit: 'minute' } } } } });

async function loadSymbols() {
  try {
    const res = await fetch('/api/bot/status');
    const json = await res.json();
    const sel = document.getElementById('symbol');
    sel.innerHTML = '';
    (json.watchlist || []).forEach(s => {
      const opt = document.createElement('option');
      opt.value = s;
      opt.text = s;
      sel.appendChild(opt);
    });
  } catch (e) {
    console.warn('Failed to load symbols', e);
  }
}

document.getElementById('subscribe').addEventListener('click', () => {
  const symbol = document.getElementById('symbol').value;
  if (!symbol) return;
  fetch('/api/bot/start', { method: 'POST' }).catch(()=>{});
  socket.emit('subscribe', { symbol });
});

document.getElementById('unsubscribe').addEventListener('click', () => {
  const symbol = document.getElementById('symbol').value;
  if (!symbol) return;
  socket.emit('unsubscribe', { symbol });
});

// socket handlers
socket.on('connect', () => console.log('socket connected'));
socket.on('market_tick', payload => {
  const ticks = payload.ticks || [];
  ticks.forEach(t => {
    const ts = new Date(t.timestamp || Date.now());
    const price = t.last_price || t.price || t.close;
    if (!price) return;
    chart.data.labels.push(ts);
    chart.data.datasets[0].data.push(price);
    // keep last 200 points
    if (chart.data.labels.length > 200) {
      chart.data.labels.shift();
      chart.data.datasets[0].data.shift();
    }
    chart.update('none');
  });
});

loadSymbols();
