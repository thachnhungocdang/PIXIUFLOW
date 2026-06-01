window.pixiuAnalyticsCharts = window.pixiuAnalyticsCharts || [];

window.initAnalyticsCharts = function () {
    window.pixiuAnalyticsCharts.forEach(chart => chart.destroy());
    window.pixiuAnalyticsCharts = [];

    const money = value => new Intl.NumberFormat('vi-VN', {
        style: 'currency',
        currency: 'VND',
        maximumFractionDigits: 0
    }).format(value || 0);

    function formatPeriodLabels(rawLabels) {
        return rawLabels.map(label => {
            const parts = String(label).split('-');
            if (parts.length === 2) return `T${parts[1]}/${parts[0]}`;
            return label;
        });
    }

    function axisLabel(value) {
        if (value === 0) return '0 đ';
        if (Math.abs(value) >= 1000000) return `${value / 1000000}M`;
        if (Math.abs(value) >= 1000) return `${value / 1000}k`;
        return value;
    }

    const chartLabelsEl = document.getElementById('chart-labels');
    const canvas = document.getElementById('reportChart');
    if (canvas && chartLabelsEl) {
        const labels = formatPeriodLabels(JSON.parse(chartLabelsEl.textContent));
        const incomeData = JSON.parse(document.getElementById('chart-income').textContent);
        const profitData = JSON.parse(document.getElementById('chart-profit').textContent);
        const ctx = canvas.getContext('2d');
        const incomeGradient = ctx.createLinearGradient(0, 0, 0, 400);
        incomeGradient.addColorStop(0, 'rgba(139, 16, 16, 0.4)');
        incomeGradient.addColorStop(1, 'rgba(139, 16, 16, 0)');

        window.pixiuAnalyticsCharts.push(new Chart(ctx, {
            data: {
                labels,
                datasets: [
                    {
                        type: 'line',
                        label: 'Doanh thu ghi nhận',
                        data: incomeData,
                        borderColor: '#8b1010',
                        backgroundColor: incomeGradient,
                        borderWidth: 2,
                        fill: 'origin',
                        tension: 0.35,
                        pointBackgroundColor: '#ffffff',
                        pointBorderColor: '#8b1010',
                        pointBorderWidth: 2,
                        pointRadius: 4,
                        pointHoverRadius: 6,
                        order: 1
                    },
                    {
                        type: 'bar',
                        label: 'Lợi nhuận ghi nhận',
                        data: profitData,
                        backgroundColor: profitData.map(value => value >= 0 ? '#26a949' : '#d92d20'),
                        borderRadius: 4,
                        barPercentage: 0.58,
                        maxBarThickness: 42,
                        order: 2
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                devicePixelRatio: window.devicePixelRatio > 1 ? window.devicePixelRatio : 2,
                interaction: { mode: 'index', intersect: false },
                plugins: {
                    legend: {
                        position: 'top',
                        labels: {
                            usePointStyle: true,
                            padding: 20,
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
                        padding: 12,
                        callbacks: {
                            label: context => `${context.dataset.label}: ${money(context.parsed.y)}`
                        }
                    }
                },
                scales: {
                    x: { grid: { display: false }, ticks: { color: '#9aa2af' } },
                    y: {
                        beginAtZero: false,
                        suggestedMin: Math.min(...incomeData, ...profitData, 0),
                        suggestedMax: Math.max(...incomeData, ...profitData, 0),
                        grid: { color: 'rgba(148, 163, 184, 0.2)' },
                        border: { dash: [4, 4] },
                        ticks: { color: '#9aa2af', callback: axisLabel }
                    }
                }
            }
        }));
    }

    const cashCanvas = document.getElementById('cashFlowChart');
    if (cashCanvas) {
        const cashLabels = formatPeriodLabels(JSON.parse(document.getElementById('cash-chart-labels').textContent));
        const cashIn = JSON.parse(document.getElementById('cash-chart-in').textContent);
        const cashOut = JSON.parse(document.getElementById('cash-chart-out').textContent);
        const cashNet = JSON.parse(document.getElementById('cash-chart-net').textContent);
        const cashCtx = cashCanvas.getContext('2d');

        window.pixiuAnalyticsCharts.push(new Chart(cashCtx, {
            data: {
                labels: cashLabels,
                datasets: [
                    {
                        type: 'bar',
                        label: 'Tiền vào',
                        data: cashIn,
                        backgroundColor: '#26a949',
                        borderRadius: 4,
                        maxBarThickness: 34
                    },
                    {
                        type: 'bar',
                        label: 'Tiền ra',
                        data: cashOut.map(value => -Math.abs(value)),
                        backgroundColor: '#d92d20',
                        borderRadius: 4,
                        maxBarThickness: 34
                    },
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
            options: {
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
                        padding: 12,
                        callbacks: {
                            label: context => {
                                const value = context.dataset.label === 'Tiền ra'
                                    ? Math.abs(context.parsed.y)
                                    : context.parsed.y;
                                return `${context.dataset.label}: ${money(value)}`;
                            }
                        }
                    }
                },
                scales: {
                    x: { grid: { display: false }, ticks: { color: '#9aa2af' } },
                    y: {
                        beginAtZero: false,
                        suggestedMin: Math.min(...cashNet, ...cashOut.map(value => -Math.abs(value)), 0),
                        suggestedMax: Math.max(...cashNet, ...cashIn, 0),
                        grid: { color: 'rgba(148, 163, 184, 0.2)' },
                        ticks: { color: '#9aa2af', callback: axisLabel }
                    }
                }
            }
        }));
    }

    const expenseCanvas = document.getElementById('expenseChart');
    if (expenseCanvas) {
        const expenseLabelsText = document.getElementById('expense-labels')?.textContent;
        const expenseValuesText = document.getElementById('expense-values')?.textContent;
        if (!expenseLabelsText || !expenseValuesText) return;
        const expenseCtx = expenseCanvas.getContext('2d');
        const expLabels = JSON.parse(expenseLabelsText);
        const expValues = JSON.parse(expenseValuesText);

        window.pixiuAnalyticsCharts.push(new Chart(expenseCtx, {
            type: 'doughnut',
            data: {
                labels: expLabels,
                datasets: [{
                    data: expValues,
                    backgroundColor: ['#8b1010', '#f4a261', '#e9c45d', '#32aaa0', '#173d4d', '#26a949', '#d92d20'],
                    borderWidth: 2,
                    borderColor: '#ffffff',
                    hoverOffset: 6
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                devicePixelRatio: window.devicePixelRatio > 1 ? window.devicePixelRatio : 2,
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
                        callbacks: {
                            label: context => `${context.label}: ${money(context.parsed)}`
                        }
                    }
                }
            }
        }));
    }
};

document.addEventListener('DOMContentLoaded', window.initAnalyticsCharts);
