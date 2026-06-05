import re

html_path = r"c:\Users\ADM\Desktop\config\core\templates\core\report.html"

with open(html_path, 'r', encoding='utf-8') as f:
    html = f.read()

def get_tag(html, tag_name, class_name):
    # simple balancer
    start_idx = html.find(f'class="{class_name}"')
    if start_idx == -1:
        start_idx = html.find(f"class='{class_name}'")
        if start_idx == -1:
            start_idx = html.find(class_name)
            if start_idx == -1: return None
    
    # backtrack to <tag
    start_tag_idx = html.rfind(f'<{tag_name}', 0, start_idx)
    
    depth = 0
    end_idx = start_tag_idx
    tag_re = re.compile(rf'<\s*(/?)\s*{tag_name}[^>]*>', re.IGNORECASE)
    for m in tag_re.finditer(html, start_tag_idx):
        if m.group(1) == '/':
            depth -= 1
        else:
            depth += 1
        if depth == 0:
            end_idx = m.end()
            return html[start_tag_idx:end_idx]
    return None

cash_acc = get_tag(html, 'section', 'analytics-cash-accounting-card')
revenue = get_tag(html, 'section', 'analytics-revenue-card')
profit_sum = get_tag(html, 'section', 'analytics-profit-summary-card')
cashflow = get_tag(html, 'section', 'analytics-cashflow-card')
expense = get_tag(html, 'section', 'analytics-expense-card')

bottom_grid = get_tag(html, 'div', 'analytics-bottom-grid')
# split bottom grid into profit and inventory
profit_margin = get_tag(bottom_grid, 'section', 'analytics-profit-card')
inventory_idx = bottom_grid.find('<section class="analytics-card">')
inventory_card = get_tag(bottom_grid[inventory_idx:], 'section', 'analytics-card')

# Now replace the entire <main class="analytics-main">
main_tag = get_tag(html, 'main', 'analytics-main')

new_main = f'''<main class="analytics-main">
            <div class="analytics-main-tabs" role="tablist" aria-label="Phân tích chuyên sâu">
                <button type="button" class="analytics-main-tab is-active" data-main-tab="revenue">
                    <span><i data-lucide="trending-up"></i></span> Doanh thu
                </button>
                <button type="button" class="analytics-main-tab" data-main-tab="profit">
                    <span><i data-lucide="line-chart"></i></span> Lợi nhuận
                </button>
                <button type="button" class="analytics-main-tab" data-main-tab="expense">
                    <span><i data-lucide="bar-chart-3"></i></span> Chi phí
                </button>
                <button type="button" class="analytics-main-tab" data-main-tab="cashflow">
                    <span><i data-lucide="banknote"></i></span> Dòng tiền
                </button>
                <button type="button" class="analytics-main-tab" data-main-tab="inventory">
                    <span><i data-lucide="package"></i></span> Tồn kho
                </button>
            </div>

            <div class="analytics-main-pane is-active" data-main-pane="revenue">
                {revenue}
            </div>

            <div class="analytics-main-pane" data-main-pane="profit" hidden>
                {profit_sum}
                {profit_margin}
            </div>

            <div class="analytics-main-pane" data-main-pane="expense" hidden>
                {expense}
            </div>

            <div class="analytics-main-pane" data-main-pane="cashflow" hidden>
                {cash_acc}
                {cashflow}
            </div>

            <div class="analytics-main-pane" data-main-pane="inventory" hidden>
                {inventory_card}
            </div>
        </main>'''

new_html = html.replace(main_tag, new_main)

# Add JS logic to the script tag
js_logic = """
    function initMainTabs(root = document) {
        const tabs = Array.from(root.querySelectorAll('[data-main-tab]'));
        const panes = Array.from(root.querySelectorAll('[data-main-pane]'));
        
        tabs.forEach(tab => {
            tab.addEventListener('click', () => {
                const target = tab.dataset.mainTab;
                
                tabs.forEach(t => t.classList.toggle('is-active', t === tab));
                
                panes.forEach(pane => {
                    const active = pane.dataset.mainPane === target;
                    pane.hidden = !active;
                    pane.classList.toggle('is-active', active);
                });
            });
        });
    }
"""

if 'function initReportInteractions(root = document) {' in new_html:
    new_html = new_html.replace('function initReportInteractions(root = document) {', 'function initReportInteractions(root = document) {\n        initMainTabs(root);')
    new_html = new_html.replace('function initCashCharts(root = document) {', js_logic + '\n    function initCashCharts(root = document) {')

with open(html_path, 'w', encoding='utf-8') as f:
    f.write(new_html)

print("Updated report.html")
