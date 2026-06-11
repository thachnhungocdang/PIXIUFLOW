import re
import unicodedata

from django.db import migrations


def backfill_sku(apps, schema_editor):
    category_prefix_map = {
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

    def remove_vietnamese(text):
        text = unicodedata.normalize("NFD", text)
        text = "".join(char for char in text if unicodedata.category(char) != "Mn")
        return text.replace("đ", "d").replace("Đ", "D")

    def get_prefix(category_name):
        name_lower = category_name.strip().lower()
        if name_lower in category_prefix_map:
            return category_prefix_map[name_lower]
        ascii_name = remove_vietnamese(category_name.strip().upper())
        words = re.sub(r"[^A-Z\s]", "", ascii_name).split()
        if len(words) >= 2:
            prefix = "".join(word[0] for word in words[:3])
        else:
            prefix = re.sub(r"[^A-Z]", "", ascii_name)[:3]
        return (prefix or "SP")[:3]

    Product = apps.get_model("core", "Product")
    user_ids = (
        Product.objects.filter(sku="")
        .values_list("user_id", flat=True)
        .distinct()
    )

    for user_id in user_ids:
        products = Product.objects.filter(user_id=user_id, sku="").order_by(
            "created_at", "id"
        )
        prefix_counters = {}

        for product in products:
            path = (product.category or "").replace(">", "/")
            level_one = path.split("/")[0].strip() or "SP"
            prefix = get_prefix(level_one)

            if prefix not in prefix_counters:
                existing_skus = Product.objects.filter(
                    user_id=user_id,
                    sku__startswith=f"{prefix}-",
                ).values_list("sku", flat=True)
                max_number = 0
                for sku in existing_skus:
                    match = re.search(r"-(\d+)$", sku or "")
                    if match:
                        max_number = max(max_number, int(match.group(1)))
                prefix_counters[prefix] = max_number

            prefix_counters[prefix] += 1
            product.sku = f"{prefix}-{prefix_counters[prefix]:03d}"
            product.save(update_fields=["sku"])


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0013_add_sku_nullable"),
    ]

    operations = [
        migrations.RunPython(backfill_sku, migrations.RunPython.noop),
    ]
