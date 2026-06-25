from flask import Flask, request, jsonify, make_response
import requests

app = Flask(__name__)

def add_cors(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'POST, GET, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response

@app.after_request
def after_request(response):
    return add_cors(response)

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

@app.route('/', methods=['OPTIONS'])
def options():
    return make_response('', 204)

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"ok": True})

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
