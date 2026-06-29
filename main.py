from flask import Flask, request, jsonify, make_response
import requests
import json
import os
from datetime import datetime, timezone, timedelta

app = Flask(__name__)
DATA_FILE = '/tmp/suppliers.json'

def add_cors(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'POST, GET, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response

@app.after_request
def after_request(response):
    return add_cors(response)

@app.route('/', methods=['OPTIONS'])
@app.route('/suppliers', methods=['OPTIONS'])
@app.route('/bonasera', methods=['OPTIONS'])
@app.route('/supplier-report', methods=['OPTIONS'])
def options():
    return make_response('', 204)

# ── REGOS PROXY ───────────────────────────────────────────────────────────────
@app.route('/', methods=['POST'])
def proxy():
    body = request.get_json()
    endpoint = body.get('endpoint')
    payload = body.get('payload', {})
    response = requests.post(
        endpoint,
        json=payload,
        headers={"Content-Type": "application/json;charset=utf-8"}
    )
    return make_response(response.text, 200, {'Content-Type': 'application/json'})

# ── BONASERA FILTERED PROXY ───────────────────────────────────────────────────
@app.route('/bonasera', methods=['POST'])
def bonasera_proxy():
    body = request.get_json()
    endpoint = body.get('endpoint')
    payload = body.get('payload', {})

    payload['limit'] = 1000
    payload['offset'] = payload.get('offset', 0)

    response = requests.post(
        endpoint + '/v1/retailreport/operations',
        json=payload,
        headers={"Content-Type": "application/json;charset=utf-8"}
    )
    data = response.json()

    if not data.get('ok'):
        return make_response(json.dumps(data), 200, {'Content-Type': 'application/json'})

    all_items = data.get('result', [])
    filtered = [item for item in all_items
                if 'голиб ака шт' in (item.get('item', {}).get('group', {}).get('path', '')).lower()]

    result = {
        'ok': True,
        'result': filtered,
        'total_all': len(all_items),
        'total_filtered': len(filtered),
        'next_offset': data.get('next_offset', 0)
    }
    return make_response(json.dumps(result, ensure_ascii=False), 200, {'Content-Type': 'application/json'})

# ── SUPPLIERS STORAGE ─────────────────────────────────────────────────────────
@app.route('/suppliers', methods=['GET'])
def get_suppliers():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return jsonify({"ok": True, "suppliers": data})
    return jsonify({"ok": True, "suppliers": []})

@app.route('/suppliers', methods=['POST'])
def save_suppliers():
    data = request.get_json()
    suppliers = data.get('suppliers', [])
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(suppliers, f, ensure_ascii=False, indent=2)
    return jsonify({"ok": True})

# ── SUPPLIER REPORT ───────────────────────────────────────────────────────────
# GET /supplier-report?start=2026-06-25&end=2026-06-27
# Возвращает расчёт по поставщикам за указанный период.
# Работает с любого устройства — компьютер не нужен.

_EP_T = "https://integration.regos.uz/gateway/out/e731e8c647b7455381ee73cae0696265"
_EP_S = "https://integration.regos.uz/gateway/out/7e05c8de1e0544f4b9577038e95cd007"
_EP_B = "https://integration.regos.uz/gateway/out/9011d723112b4dfe86f41839fdf603f7"
_TZ   = timezone(timedelta(hours=5))

_SUPPLIERS = [
    {"name": "Али ака", "items": [
        {"code":"000237","cost":65000},{"code":"000314","cost":60000},{"code":"000350","cost":50000},
        {"code":"000418","cost":70000},{"code":"000419","cost":55000},{"code":"000420","cost":45000},
        {"code":"000491","cost":55000},{"code":"000519","cost":55000},{"code":"000538","cost":65000},
        {"code":"000545","cost":60000},{"code":"000573","cost":75000},{"code":"000574","cost":65000},
        {"code":"000632","cost":95000},{"code":"000638","cost":115000},{"code":"000649","cost":93000},
        {"code":"000683","cost":85000},{"code":"000711","cost":165000},{"code":"000712","cost":19000},
        {"code":"000722","cost":220000},{"code":"000724","cost":180000},{"code":"000763","cost":85000},
        {"code":"000770","cost":60000},{"code":"000771","cost":90000},{"code":"000777","cost":105000},
        {"code":"000790","cost":80000},{"code":"000791","cost":185000},{"code":"000857","cost":230000},
        {"code":"000956","cost":90000},{"code":"000998","cost":70000},{"code":"001025","cost":16000},
        {"code":"001054","cost":65000},{"code":"003504","cost":55000},{"code":"003552","cost":70000},
        {"code":"003602","cost":70000},{"code":"003629","cost":19000},{"code":"003630","cost":61000},
        {"code":"003647","cost":55000},{"code":"003653","cost":70000},{"code":"003668","cost":60000},
        {"code":"003669","cost":85000},{"code":"003909","cost":70000},{"code":"003978","cost":75000},
        {"code":"003996","cost":55000},
    ]},
    {"name":"Шавкат ака постель","items":[
        {"code":"000444","cost":68000},{"code":"000445","cost":53000},
        {"code":"003910","cost":68000},{"code":"003911","cost":53000},
    ]},
    {"name":"Шавкат ака сочик","items":[
        {"code":"001096","cost":113000},{"code":"004004","cost":113000},
    ]},
    {"name":"Шим чорсу","items":[
        {"code":"000938","cost":155000},{"code":"000939","cost":155000},{"code":"000940","cost":130000},
        {"code":"000941","cost":130000},{"code":"000942","cost":140000},{"code":"000943","cost":150000},
        {"code":"000944","cost":150000},{"code":"000945","cost":150000},{"code":"000946","cost":150000},
        {"code":"000947","cost":150000},{"code":"000948","cost":165000},{"code":"000949","cost":165000},
        {"code":"000950","cost":165000},{"code":"000951","cost":165000},{"code":"000952","cost":155000},
        {"code":"000953","cost":155000},{"code":"000954","cost":155000},{"code":"001026","cost":70000},
    ]},
    {"name":"Хасанбой","items":[
        {"code":"000639","cost":120000},{"code":"000650","cost":120000},{"code":"000756","cost":120000},
    ]},
    {"name":"Жавлон ака Селаник","items":[
        {"code":"000865","cost":70000},{"code":"000866","cost":75000},{"code":"000957","cost":58000},
    ]},
    {"name":"Азиз ака Корея","items":[
        {"code":"001015","cost":40000},{"code":"001024","cost":35000},
        {"code":"001027","cost":25000},{"code":"001028","cost":20000},
    ]},
    {"name":"Комил ака Самарканд","items":[
        {"code":"001022","cost":80000},{"code":"001023","cost":115000},
    ]},
    {"name":"Носиржон ака","items":[
        {"code":"001038","cost":105000},
    ]},
    {"name":"Шоира опа паплин","items":[
        {"code":"001057","cost":60000},{"code":"001058","cost":35000},{"code":"001059","cost":18000},
        {"code":"001060","cost":28000},{"code":"001061","cost":75000},{"code":"001062","cost":35000},
        {"code":"001088","cost":30000},{"code":"001106","cost":25000},{"code":"001107","cost":30000},
        {"code":"003960","cost":60000},{"code":"003961","cost":35000},{"code":"003962","cost":28000},
        {"code":"003963","cost":18000},{"code":"003964","cost":75000},{"code":"003965","cost":35000},
    ]},
]

def _norm(code):
    return str(code or "").strip().lstrip("0").zfill(6)

def _lookup():
    m = {}
    for s in _SUPPLIERS:
        for it in s["items"]:
            m[_norm(it["code"])] = {"supplier": s["name"], "cost": it["cost"]}
    return m

def _fetch(ep, start_ts, end_ts, extra=None):
    base = {"start_date": start_ts, "end_date": end_ts, "limit": 100}
    if extra:
        base.update(extra)
    items, offset = [], 0
    while True:
        r = requests.post(ep + "/v1/retailreport/operations",
                          json={**base, "offset": offset},
                          headers={"Content-Type": "application/json;charset=utf-8"},
                          timeout=30)
        d = r.json()
        if not d.get("ok"):
            break
        batch = d.get("result", [])
        items.extend(batch)
        if len(batch) < 100:
            break
        offset += 100
    return items

@app.route('/supplier-report', methods=['GET'])
def supplier_report():
    start_str = request.args.get('start', '')
    end_str   = request.args.get('end', '')
    if not start_str or not end_str:
        return jsonify({"ok": False, "error": "Укажи start и end (YYYY-MM-DD)"}), 400
    try:
        start_ts = int(datetime.strptime(start_str, "%Y-%m-%d")
                       .replace(hour=0,  minute=0,  second=0,  tzinfo=_TZ).timestamp())
        end_ts   = int(datetime.strptime(end_str,   "%Y-%m-%d")
                       .replace(hour=23, minute=59, second=59, tzinfo=_TZ).timestamp())
    except ValueError:
        return jsonify({"ok": False, "error": "Формат даты: YYYY-MM-DD"}), 400

    chorsu    = _fetch(_EP_T, start_ts, end_ts, {"operating_cash_ids": [3, 4]})
    kadysheva = _fetch(_EP_T, start_ts, end_ts, {"operating_cash_ids": [1, 2]})
    samarkand = _fetch(_EP_S, start_ts, end_ts)

    lk = _lookup()
    result = {s["name"]: {"Чорсу": 0, "Кадышева": 0, "Самарканд": 0, "total": 0}
              for s in _SUPPLIERS}

    for shop, items in [("Чорсу", chorsu), ("Кадышева", kadysheva), ("Самарканд", samarkand)]:
        for item in items:
            code = _norm((item.get("item") or {}).get("code", ""))
            if code not in lk:
                continue
            qty = (item.get("sale_quantity") or 0) - (item.get("return_quantity") or 0)
            if qty <= 0:
                continue
            sup, cost = lk[code]["supplier"], lk[code]["cost"]
            result[sup][shop]    += qty * cost
            result[sup]["total"] += qty * cost

    grand_total = sum(v["total"] for v in result.values())
    return make_response(
        json.dumps({
            "ok": True,
            "period": {"start": start_str, "end": end_str},
            "result": result,
            "grand_total": grand_total,
            "counts": {"chorsu": len(chorsu), "kadysheva": len(kadysheva), "samarkand": len(samarkand)},
        }, ensure_ascii=False),
        200, {"Content-Type": "application/json"})


# ── REVENUE REPORT ───────────────────────────────────────────────────────────
# GET /revenue-report?date=YYYY-MM-DD   (default: вчера)
# Возвращает выручку по 7 магазинам + топ-5 товаров по количеству.

_STORES_REV = [
    {"id": "kadysh",  "name": "Кадышева",      "src": "tashkent",
     "match": lambda s: "kilo" in s or "кило" in s or "кадыш" in s},
    {"id": "chorsu",  "name": "Чорсу",          "src": "tashkent",
     "match": lambda s: "yoyo" in s or "йойо" in s or "чорсу" in s},
    {"id": "aziz",    "name": "Азиз бозор",     "src": "samarkand",
     "match": lambda s: "гагарин" in s},
    {"id": "marhabo", "name": "Мархабо",        "src": "samarkand",
     "match": lambda s: "мархабо" in s},
    {"id": "sogd",    "name": "Согдиана",       "src": "bonasera", "cashIds": [4, 5, 17, 18]},
    {"id": "uzbek",   "name": "Узбекистанский", "src": "bonasera", "cashIds": [6, 13, 14, 15]},
    {"id": "bonmen",  "name": "Bonasera Men",   "src": "bonasera", "cashIds": [10, 12, 16]},
]

def _get_cashes(ep):
    try:
        r = requests.post(ep + "/v1/operatingcash/get", json={},
                          headers={"Content-Type": "application/json;charset=utf-8"}, timeout=15)
        return r.json().get("result", [])
    except Exception:
        return []

@app.route('/revenue-report', methods=['GET'])
def revenue_report():
    # Поддерживает два режима:
    #   ?date=YYYY-MM-DD          — один день
    #   ?start=YYYY-MM-DD&end=... — диапазон
    start_str = request.args.get('start', '')
    end_str   = request.args.get('end', '')
    date_str  = request.args.get('date', '')

    if start_str and end_str:
        date_start, date_end = start_str, end_str
    else:
        if not date_str:
            date_str = (datetime.now(_TZ) - timedelta(days=1)).strftime("%Y-%m-%d")
        date_start = date_end = date_str

    try:
        start_day = datetime.strptime(date_start, "%Y-%m-%d").replace(tzinfo=_TZ)
        end_day   = datetime.strptime(date_end,   "%Y-%m-%d").replace(tzinfo=_TZ)
    except ValueError:
        return jsonify({"ok": False, "error": "Format: YYYY-MM-DD"}), 400

    start_ts = int(start_day.replace(hour=0,  minute=0,  second=0).timestamp())
    end_ts   = int(end_day.replace(hour=23, minute=59, second=59).timestamp())

    cash_map = {}
    for c in _get_cashes(_EP_T):
        sn = ((c.get("stock") or {}).get("name") or c.get("name") or "").lower()
        for st in _STORES_REV:
            if st["src"] == "tashkent" and st["match"](sn):
                cash_map.setdefault(st["id"], []).append(c["id"])
    for c in _get_cashes(_EP_S):
        sn = ((c.get("stock") or {}).get("name") or c.get("name") or "").lower()
        for st in _STORES_REV:
            if st["src"] == "samarkand" and st["match"](sn):
                cash_map.setdefault(st["id"], []).append(c["id"])

    revenue  = {}
    item_qty = {}

    for st in _STORES_REV:
        if st["src"] == "bonasera":
            ep, ids = _EP_B, st["cashIds"]
        elif st["src"] == "tashkent":
            ep, ids = _EP_T, cash_map.get(st["id"], [])
        else:
            ep, ids = _EP_S, cash_map.get(st["id"], [])

        ops = _fetch(ep, start_ts, end_ts, {"operating_cash_ids": ids}) if ids else []

        store_rev = 0
        for op in ops:
            net_rev = (op.get("sale_amount") or 0) - (op.get("return_amount") or 0)
            net_qty = (op.get("sale_quantity") or 0) - (op.get("return_quantity") or 0)
            if net_rev > 0:
                store_rev += net_rev
            name = ((op.get("item") or {}).get("name") or "").strip()
            if name and net_qty > 0:
                item_qty[name] = item_qty.get(name, 0) + net_qty

        revenue[st["name"]] = store_rev

    top5 = sorted(item_qty.items(), key=lambda x: x[1], reverse=True)[:5]

    return make_response(
        json.dumps({
            "ok": True,
            "date": date_start,
            "date_start": date_start,
            "date_end":   date_end,
            "revenue": revenue,
            "grand_total": sum(revenue.values()),
            "top5_qty": [{"name": n, "qty": q} for n, q in top5],
        }, ensure_ascii=False),
        200, {"Content-Type": "application/json"})

@app.route('/revenue-report', methods=['OPTIONS'])
def revenue_report_options():
    return make_response('', 204)

# ── ITEM NAMES ───────────────────────────────────────────────────────────────
# GET /item-names?ids=237,314,350,...
# Возвращает {code: name} для указанных ID товаров.
@app.route('/item-names', methods=['GET'])
def item_names():
    ids_str = request.args.get('ids', '')
    if not ids_str:
        return jsonify({"ok": False, "error": "ids required"}), 400
    try:
        ids = [int(x.strip()) for x in ids_str.split(',') if x.strip()]
    except ValueError:
        return jsonify({"ok": False, "error": "ids must be integers"}), 400

    id_set = set(ids)
    names = {}

    def fetch_range(ep, offset, limit):
        r = requests.post(ep + "/v1/item/get",
                          json={"limit": limit, "offset": offset},
                          headers={"Content-Type": "application/json;charset=utf-8"},
                          timeout=30)
        return r.json().get("result", [])

    if not ids:
        return jsonify({"ok": True, "names": {}})

    min_id, max_id = min(ids), max(ids)

    # Tashkent endpoint covers low IDs
    for item in fetch_range(_EP_T, min_id - 1, max_id - min_id + 1):
        if item.get("id") in id_set:
            names[str(item["id"]).zfill(6)] = item.get("name", "")

    # Samarkand endpoint covers high IDs (3500+)
    high_ids = [i for i in ids if i >= 3500 and str(i).zfill(6) not in names]
    if high_ids:
        hi_min, hi_max = min(high_ids), max(high_ids)
        for item in fetch_range(_EP_S, hi_min - 1, hi_max - hi_min + 1):
            if item.get("id") in id_set:
                names[str(item["id"]).zfill(6)] = item.get("name", "")

    return make_response(
        json.dumps({"ok": True, "names": names, "found": len(names)}, ensure_ascii=False),
        200, {"Content-Type": "application/json"})

@app.route('/item-names', methods=['OPTIONS'])
def item_names_options():
    return make_response('', 204)

# ── HEALTH ────────────────────────────────────────────────────────────────────
@app.route('/health', methods=['GET'])
def health():
    return jsonify({"ok": True})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

# ── REPORT0021 with cost dat