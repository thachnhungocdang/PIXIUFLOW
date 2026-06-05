window.pixiuAnalyticsCharts = window.pixiuAnalyticsCharts || [];

const pixiuMoney = value => new Intl.NumberFormat('vi-VN', {
    style: 'currency',
    currency: 'VND',
    maximumFractionDigits: 0
}).format(value || 0);

const pixiuJson = id => {
    const node = document.getElementById(id);
    if (!node) return [];
    try { return JSON.parse(node.textContent || '[]'); }
    catch (error) { return []; }
};

const pixiuLabels = labels => labels.map(label => {
    const parts = String(label).split('-');
    return parts.length === 2 ? `T${parts[1]}/${parts[0]}` : label;
});

const pixiuAxis = value => {
    if (value === 0) return '0 đ';
    if (Math.abs(value) >= 1000000) return `${value / 1000000}M`;
    if (Math.abs(value) >= 1000) return `${value / 1000}k`;
    return value;
};

function loadChartJs() {
    if (window.Chart) return Promise.resolve();
    if (window.pixiuChartJsLoading) return window.pixiuChartJsLoading;
    window.pixiuChartJsLoading = new Promise((resolve, reject) => {
        const script = document.createElement('script');
        const timeout = setTimeout(() => reject(new Error('Chart.js load timeout')), 4000);
        script.src = 'https://cdn.jsdelivr.net/npm/chart.js@4.4.9/dist/chart.umd.min.js';
        script.onload = () => { clearTimeout(timeout); resolve(); };
        script.onerror = error => { clearTimeout(timeout); reject(error); };
        document.head.appendChild(script);
    });
    return window.pixiuChartJsLoading;
}

function baseOptions(minMax = {}) {
    return {
        responsive: true,
        maintainAspectRatio: false,
        devicePixelRatio: window.devicePixelRatio > 1 ? window.devicePixelRatio : 2,
        interaction: { mode: 'index', intersect: false },
        plugins: {
            legend: {
                position: 'top',
                labels: {
                    usePointStyle: true,
                    padding: 18,
                    font: { family: "'Inter', Arial, sans-serif", size: 13, weight: '600' },
                    color: '#1f2937'
                }
            },
            tooltip: {
                backgroundColor: '#ffffff',
                titleColor: '#171717',
                bodyColor: '#1f2937',
                borderColor: '#f2bf4b',
                borderWidth: 1,
                padding: 12
            }
        },
        scales: {
            x: { grid: { display: false }, ticks: { color: '#9aa2af' } },
            y: {
                beginAtZero: false,
                suggestedMin: minMax.min,
                suggestedMax: minMax.max,
                grid: { color: 'rgba(148, 163, 184, 0.2)' },
                ticks: { color: '#9aa2af', callback: pixiuAxis }
            }
        }
    };
}

function makeCashChart() {
    const canvas = document.getElementById('cashFlowChart');
    if (!canvas) return;
    const labels = pixiuLabels(pixiuJson('cash-chart-labels'));
    const cashIn = pixiuJson('cash-chart-in');
    const cashOut = pixiuJson('cash-chart-out');
    const cashNet = pixiuJson('cash-chart-net');
    const outNegative = cashOut.map(value => -Math.abs(value));
    const options = baseOptions({
        min: Math.min(...cashNet, ...outNegative, 0),
        max: Math.max(...cashNet, ...cashIn, 0)
    });
    options.plugins.tooltip.callbacks = {
        label: context => {
            const value = context.dataset.label === 'Tiền ra' ? Math.abs(context.parsed.y) : context.parsed.y;
            return `${context.dataset.label}: ${pixiuMoney(value)}`;
        }
    };
    window.pixiuAnalyticsCharts.push(new Chart(canvas.getContext('2d'), {
        data: {
            labels,
            datasets: [
                { type: 'bar', label: 'Tiền vào', data: cashIn, backgroundColor: '#26a949', borderRadius: 4, maxBarThickness: 34 },
                { type: 'bar', label: 'Tiền ra', data: outNegative, backgroundColor: '#d92d20', borderRadius: 4, maxBarThickness: 34 },
                {
                    type: 'line',
                    label: 'Dòng tiền thuần',
                    data: cashNet,
                    borderColor: '#8b1010',
                    backgroundColor: 'rgba(139, 16, 16, 0.12)',
                    borderWidth: 2,
                    tension: 0.35,
                    pointBackgroundColor: '#ffffff',
                    pointBorderColor: '#8b1010',
                    pointBorderWidth: 2,
                    pointRadius: 4
                }
            ]
        },
        options
    }));
}

function makeExpenseChart() {
    const canvas = document.getElementById('expenseChart');
    const labels = pixiuJson('expense-labels');
    const values = pixiuJson('expense-values');
    if (!canvas || !labels.length || !values.length) return;
    window.pixiuAnalyticsCharts.push(new Chart(canvas.getContext('2d'), {
        type: 'doughnut',
        data: {
            labels,
            datasets: [{
                data: values,
                backgroundColor: ['#8b1010', '#f4a261', '#e9c45d', '#32aaa0', '#173d4d', '#26a949', '#d92d20'],
                borderWidth: 2,
                borderColor: '#ffffff',
                hoverOffset: 6
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '75%',
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: '#ffffff',
                    titleColor: '#171717',
                    bodyColor: '#1f2937',
                    borderColor: '#f2bf4b',
                    borderWidth: 1,
                    padding: 12,
                    callbacks: { label: context => `${context.label}: ${pixiuMoney(context.parsed)}` }
                }
            }
        }
    }));
}

window.initAnalyticsCharts = function () {
    if (!window.Chart) {
        loadChartJs().then(window.initAnalyticsCharts).catch(error => console.error(error));
        return;
    }
    window.pixiuAnalyticsCharts.forEach(chart => chart.destroy());
    window.pixiuAnalyticsCharts = [];
    makeCashChart();
    makeExpenseChart();
};

document.addEventListener('DOMContentLoaded', window.initAnalyticsCharts);
