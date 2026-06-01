from django import template

register = template.Library()


@register.filter
def vnd(value):
    try:
        num = float(value)
        formatted = "{:,.0f}".format(num).replace(",", ".")
        return f"{formatted} đ"
    except (ValueError, TypeError):
        return value


@register.filter
def fix_mojibake(value):
    if value is None:
        return ''
    text = str(value)
    if not any(marker in text for marker in ('Ã', 'Â', 'Ä')):
        return text
    try:
        return text.encode('latin1').decode('utf-8')
    except UnicodeError:
        return text


@register.filter
def percentage_of(value, total):
    try:
        total_num = float(total)
        if total_num == 0:
            return '--'
        return f"{(float(value) / total_num * 100):.1f}%"
    except (ValueError, TypeError, ZeroDivisionError):
        return '--'
