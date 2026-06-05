import sys
import re

file_path = 'core/templates/core/report.html'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

start_marker = '<div class="analytics-tabs" data-profit-tabs>'
end_marker = '</section>\n            </div>\n\n            <div class="analytics-main-pane" data-main-pane="expense" hidden>'

start_idx = content.find(start_marker)
end_idx = content.find(end_marker)

if start_idx == -1 or end_idx == -1:
    print('Could not find markers')
    sys.exit(1)

with open('new_block.html', 'r', encoding='utf-8') as f:
    new_content = f.read()
    
# Append the end marker back since we use it to construct the final string.
new_content += '</section>\n            </div>\n\n            <div class="analytics-main-pane" data-main-pane="expense" hidden>'

final_content = content[:start_idx] + new_content + content[end_idx + len(end_marker):]

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(final_content)
print("Updated successfully")
