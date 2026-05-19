import json, os
from flask import Flask, send_from_directory, jsonify, request

app = Flask(__name__, static_folder='static')

def load(f, default):
    try:
        with open(f, encoding='utf-8') as fp: return json.load(fp)
    except: return default

goods    = load('goods.json', [])
orders   = load('orders.json', [])
users    = load('users.json', {})
balance  = load('balance.json', {})
settings = load('settings.json', {})

@app.route('/')
@app.route('/dashboard')
def index():
    r = send_from_directory('static', 'dashboard.html')
    r.headers['Cache-Control'] = 'no-cache'
    return r

@app.route('/webapp')
def webapp():
    r = send_from_directory('static', 'webapp.html')
    r.headers['Cache-Control'] = 'no-cache'
    return r

@app.route('/static/<path:f>')
def static_files(f):
    return send_from_directory('static', f)

@app.route('/api/public/goods')
def pub_goods():
    return jsonify({"success": True, "data": goods})

@app.route('/api/public/deposit-numbers')
def pub_deposit():
    return jsonify({"success": True, "data": settings.get("deposit_numbers", ["97675410"])})

@app.route('/api/public/user/<uid>')
def pub_user(uid):
    if uid not in users: return jsonify({"success": False}), 404
    return jsonify({"success": True, "balance": balance.get(uid, 0), "username": users[uid].get("username","")})

@app.route('/api/public/orders/<uid>')
def pub_orders(uid):
    return jsonify({"success": True, "data": [o for o in orders if str(o.get('user_id')) == uid]})

@app.route('/api/public/buy', methods=['POST'])
def pub_buy():
    return jsonify({"success": True})

@app.route('/api/public/recharge', methods=['POST'])
def pub_recharge():
    return jsonify({"success": True})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8081))
    app.run(host='0.0.0.0', port=port, debug=False)
