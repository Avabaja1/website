from flask import Flask, request, jsonify, render_template
from flask_cors import CORS

app = Flask(__name__, template_folder="templates")
CORS(app)

# username → статус ('paid', 'pending', 'unpaid')
users = {}

@app.route('/check-payment', methods=['POST'])
def check_payment():
    data = request.get_json()
    username = data.get('username')
    if not username:
        return jsonify({'error': 'Не указан username'}), 400

    status = users.get(username, 'pending')
    if status == 'paid':
        return jsonify({'paid': True})
    else:
        # если юзер ранее не отправлялся — добавить его в pending
        if username not in users:
            users[username] = 'pending'
        return jsonify({'paid': False, 'status': users[username]})

@app.route('/add-payment', methods=['POST'])
def add_payment():
    data = request.get_json()
    username = data.get('username')
    if not username:
        return jsonify({'error': 'Не указан username'}), 400

    users[username] = 'paid'
    return jsonify({'success': True})

@app.route('/set-status', methods=['POST'])
def set_status():
    data = request.get_json()
    username = data.get('username')
    status = data.get('status')
    if not username or status not in ['paid', 'pending', 'unpaid']:
        return jsonify({'error': 'Неверные данные'}), 400

    users[username] = status
    return jsonify({'success': True})

@app.route('/admin')
def admin():
    return render_template("admin.html", users=users)

if __name__ == '__main__':
    app.run(port=46321)
