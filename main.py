from flask import Flask, request, jsonify, make_response
import requests
import json
import os

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
# Fetches retailreport/operations and filters only Golib aka sht items
@app.route('/bonasera', methods=['POST'])
def bonasera_proxy():
    body = request.get_json()
    endpoint = body.get('endpoint')
    payload = body.get('payload', {})

    # Fetch with large limit to get all in one request
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

    # Filter only Golib aka sht items on server side
    all_items = data.get('result', [])
    filtered = []
    for item in all_items:
        item_data = item.get('item', {})
        group = item_data.get('group', {})
        path = group.get('path', '').lower()
        if 'голиб ака шт' in path:
            filtered.append(item)

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

# ── HEALTH ────────────────────────────────────────────────────────────────────
@app.route('/health', methods=['GET'])
def health():
    return jsonify({"ok": True})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
