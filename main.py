from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

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
    
    resp = jsonify(response.json())
    resp.headers['Access-Control-Allow-Origin'] = '*'
    return resp

@app.route('/', methods=['OPTIONS'])
def options():
    resp = app.make_default_options_response()
    resp.headers['Access-Control-Allow-Origin'] = '*'
    resp.headers['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
    resp.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return resp

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"ok": True})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
