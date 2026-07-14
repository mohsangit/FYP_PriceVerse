import re
from typing import List, Optional, Tuple


def parse_pkr_prices(text: str) -> List[int]:
    """Extract PKR amounts from text like 'Rs 511,999' or 'PKR 62,499'."""
    if not text:
        return []
    amounts = []
    for match in re.finditer(r"(?:Rs\.?|PKR)\s*([\d,]+)", text, re.I):
        try:
            amounts.append(int(match.group(1).replace(",", "")))
        except ValueError:
            continue
    return amounts


def split_current_old_prices(text: str) -> Tuple[int, Optional[int]]:
    prices = parse_pkr_prices(text)
    if not prices:
        return 0, None
    current = min(prices)
    higher = [price for price in prices if price > current]
    old = max(higher) if higher else None
    return current, old


def parse_onsale_discount_pct(text: str) -> int:
    match = re.search(r"-?\s*(\d+)\s*%", text or "")
    return int(match.group(1)) if match else 0


def parse_woocommerce_prices(soup) -> Tuple[int, Optional[int]]:
    price_el = soup.select_one(
        "p.price, .summary .price, .product-summary .price, .wd-single-price .price"
    )
    if not price_el:
        return 0, None

    del_el = price_el.select_one("del .woocommerce-Price-amount, del .amount, del")
    ins_el = price_el.select_one("ins .woocommerce-Price-amount, ins .amount, ins")
    if del_el and ins_el:
        old_prices = parse_pkr_prices(del_el.get_text(" ", strip=True))
        current_prices = parse_pkr_prices(ins_el.get_text(" ", strip=True))
        if current_prices and old_prices:
            current = min(current_prices)
            old = max(old_prices)
            if old > current:
                return current, old

    return split_current_old_prices(price_el.get_text(" ", strip=True))


def parse_priceoye_prices(soup) -> Tuple[int, Optional[int], int]:
    """
    Extract (discounted_price, original_price, discount_pct) from a PriceOye
    product detail page.

    PriceOye structure:
      <div class="po-price-content">
        <span class="summary-price ... bold">Rs 27,099</span>   -> discounted
        <div class="retail-price market-price">Rs 34,999</div>   -> original
        <span class="save-price">23% OFF</span>                  -> discount %
    """
    container = soup.select_one(
        "div.po-price-content, div.product-price.po-price-border, div.product-price"
    )
    if not container:
        return 0, None, 0

    current = 0
    for el in container.select("span.summary-price, .summary-price"):
        classes = el.get("class") or []
        if "line-through" in classes:
            continue
        prices = parse_pkr_prices(el.get_text(" ", strip=True))
        if prices:
            current = prices[0]
            break

    old = None
    old_el = container.select_one(
        ".retail-price, .market-price, span.summary-price.line-through, .summary-price.line-through"
    )
    if old_el:
        prices = parse_pkr_prices(old_el.get_text(" ", strip=True))
        if prices:
            old = prices[0]

    pct = 0
    pct_el = container.select_one(".save-price, .save-price-section")
    if pct_el:
        pct = parse_onsale_discount_pct(pct_el.get_text(" ", strip=True))

    if old and current and old <= current:
        old = None

    return current, old, pct


def parse_fallback_price_from_tables(soup) -> Tuple[int, Optional[int]]:
    for row in soup.select("table tr"):
        text = row.get_text(" ", strip=True)
        if re.search(r"(?:Rs\.?|PKR)\s*[\d,]+", text, re.I):
            current, old = split_current_old_prices(text)
            if current > 0:
                return current, old
    return 0, None


def is_iphone_product(title: str) -> bool:
    t = (title or "").lower()
    if not any(k in t for k in ("iphone", "apple")):
        return False
    blocked = ("macbook", "ipad", "watch", "airpod", "charger", "cable", "case")
    return not any(b in t for b in blocked)


def is_samsung_phone(title: str) -> bool:
    t = (title or "").lower()
    if "samsung" not in t and "galaxy" not in t:
        return False
    blocked = ("tab ", "tablet", "watch", "buds", "charger", "case", "cover")
    return not any(b in t for b in blocked)


def normalize_title(title: str) -> str:
    return re.sub(r"\s+", " ", (title or "").strip())


def parse_priceoye_discontinued(soup) -> bool:
    try:
        for el in soup.select(".ribbon_discontinued, .ribbon.ribbon_discontinued, [class*='discontinued']"):
            text = el.get_text(" ", strip=True).lower()
            if "discontinued" in text:
                return True

        product_root = soup.select_one(
            ".product-detail, .product-summary, .single-product, #product-detail, main"
        )
        scope = product_root if product_root else soup
        if re.search(r"\bdiscontinued\b", scope.get_text(" ", strip=True)[:3000], re.I):
            ribbon = scope.select_one(".ribbon")
            if ribbon and "discontinued" in ribbon.get_text(" ", strip=True).lower():
                return True
            title_area = scope.select_one("h1.product_title, h1")
            if title_area:
                parent = title_area.find_parent(["div", "section"], limit=3)
                if parent and re.search(
                    r"\bdiscontinued\b",
                    parent.get_text(" ", strip=True)[:800],
                    re.I,
                ):
                    return True
    except Exception:
        return False
    return False


def parse_techroid_discontinued(soup) -> bool:
    """Detect discontinued status on Techroid WooCommerce product pages."""
    try:
        for el in soup.select(
            ".ribbon_discontinued, .ribbon.ribbon_discontinued, "
            ".out-of-stock, .stock.out-of-stock, [class*='discontinued']"
        ):
            text = el.get_text(" ", strip=True).lower()
            if "discontinued" in text:
                return True

        stock_el = soup.select_one(".stock, p.stock, .availability")
        if stock_el and "discontinued" in stock_el.get_text(" ", strip=True).lower():
            return True

        summary = soup.select_one(".summary, .product-summary, .product")
        if summary and re.search(r"\bdiscontinued\b", summary.get_text(" ", strip=True)[:2500], re.I):
            return True
    except Exception:
        return False
    return False


def _apply_discontinued_metadata(record: dict, store_label: str) -> None:
    if not record.get("is_discontinued"):
        return
    status_note = f"Discontinued on {store_label}."
    desc = (record.get("description") or "").strip()
    if "discontinued" not in desc.lower():
        record["description"] = f"{desc} {status_note}".strip()
    specs = dict(record.get("specifications") or {})
    if specs.get("Availability") != "Discontinued":
        specs["Availability"] = "Discontinued"
        record["specifications"] = specs
