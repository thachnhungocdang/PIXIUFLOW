import re
import unicodedata


CATEGORY_PREFIX_MAP = {
    "cà phê": "CF",
    "thức uống": "TH",
    "thực phẩm": "TP",
    "điện tử": "DT",
    "quần áo": "QA",
    "giày dép": "GD",
    "mỹ phẩm": "MP",
    "văn phòng phẩm": "VP",
    "đồ gia dụng": "DG",
    "bánh kẹo": "BK",
    "đồ uống": "DU",
}


def remove_vietnamese(text: str) -> str:
    text = unicodedata.normalize("NFD", text)
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    return text.replace("đ", "d").replace("Đ", "D")


def generate_prefix(category_name: str) -> str:
    """Convert a level-one category name to a two or three-letter prefix."""
    name_lower = category_name.strip().lower()
    if name_lower in CATEGORY_PREFIX_MAP:
        return CATEGORY_PREFIX_MAP[name_lower]

    ascii_name = remove_vietnamese(category_name.strip().upper())
    words = re.sub(r"[^A-Z\s]", "", ascii_name).split()
    if len(words) >= 2:
        prefix = "".join(word[0] for word in words[:3])
    else:
        prefix = re.sub(r"[^A-Z]", "", ascii_name)[:3]
    return (prefix or "SP")[:3]


def category_level_one(category_path: str) -> str:
    path = (category_path or "").replace(">", "/")
    return path.split("/")[0].strip() or "SP"


def generate_product_sku(user, category_path: str) -> str:
    """Generate the next available per-user SKU for a category prefix."""
    from core.models import Product

    prefix = generate_prefix(category_level_one(category_path))
    existing_skus = Product.objects.filter(
        user=user,
        sku__startswith=f"{prefix}-",
    ).values_list("sku", flat=True)

    max_number = 0
    for sku in existing_skus:
        match = re.search(r"-(\d+)$", sku or "")
        if match:
            max_number = max(max_number, int(match.group(1)))

    return f"{prefix}-{max_number + 1:03d}"
