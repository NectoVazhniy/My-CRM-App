from flask import Flask, request, render_template, redirect, send_file
import io
import datetime
import os
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
from openpyxl.workbook import Workbook
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
import os
app = Flask(__name__, template_folder='templates')
app.secret_key = os.environ.get('SECRET_KEY', 'default_secret_key')

# Получение и проверка DATABASE_URL
db_url = os.environ.get("DATABASE_URL")
if not db_url:
    raise ValueError("❌ Переменная DATABASE_URL не задана!")

if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# Проверка подключения
try:
    with app.app_context():
        db.session.execute(text("SELECT 1"))
    print("✅ Подключение к базе успешно.")
except Exception as e:
    print("❌ ОШИБКА при подключении к базе:", e)
login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

class User(db.Model, UserMixin):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

class Client(db.Model):
    __tablename__ = 'clients'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150))
    phone = db.Column(db.String(50))
    email = db.Column(db.String(150))
    total_orders = db.Column(db.Float, default=0.0)
    birth_date = db.Column(db.String(50), default="Отсутствует")
    bonus_points = db.Column(db.Integer, default=0)
    last_order_date = db.Column(db.String(50), default="Отсутствует")
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))

def get_filter_params():
    return {
        'search': request.args.get('search', '').strip(),
        'min_points': request.args.get('min_points', '').strip(),
        'max_points': request.args.get('max_points', '').strip(),
        'min_orders': request.args.get('min_orders', '').strip(),
        'max_orders': request.args.get('max_orders', '').strip(),
        'sort_by': request.args.get('sort_by', 'bonus_points')
    }

def fetch_filtered_clients(params):
    query = Client.query.filter_by(user_id=current_user.id)

    if params['search']:
        like = f"%{params['search']}%"
        query = query.filter(
            (Client.id.cast(db.String).like(like)) |
            (Client.name.like(like)) |
            (Client.phone.like(like)) |
            (Client.email.like(like))
        )

    if params['min_points']:
        query = query.filter(Client.bonus_points >= int(params['min_points']))
    if params['max_points']:
        query = query.filter(Client.bonus_points <= int(params['max_points']))
    if params['min_orders']:
        query = query.filter(Client.total_orders >= float(params['min_orders']))
    if params['max_orders']:
        query = query.filter(Client.total_orders <= float(params['max_orders']))

    return query.all()

def days_until_birthday(birth_date_str):
    if not birth_date_str or birth_date_str == 'Отсутствует':
        return 9999
    try:
        birth_date = datetime.datetime.strptime(birth_date_str, '%Y-%m-%d').date()
        today = datetime.datetime.now().date()
        next_bd = birth_date.replace(year=today.year)
        if next_bd < today:
            next_bd = next_bd.replace(year=today.year + 1)
        return (next_bd - today).days
    except:
        return 9999


def sort_by_bonus_points(clients):
    return sorted(clients, key=lambda c: c.bonus_points, reverse=True)

def sort_by_nearest_birthday(clients):
    with_dates = []
    without_dates = []

    for c in clients:
        days = days_until_birthday(c.birth_date)
        if days == 9999:
            without_dates.append(c)
        else:
            with_dates.append((days, c))

    with_dates.sort(key=lambda x: x[0])
    return [c for _, c in with_dates] + without_dates

    with_dates.sort(key=lambda x: x[0])
    return [c for _, c in with_dates] + without_dates
def parse_order_date(date_str):
    if not date_str or date_str == 'Отсутствует':
        return None
    try:
        return datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
    except:
        return None

def sort_by_last_order_oldest(clients):
    return sorted(clients, key=lambda c: (
        parse_order_date(c.last_order_date) is None,
        parse_order_date(c.last_order_date) or datetime.date.min
    ))

def sort_by_last_order_newest(clients):
    return sorted(clients, key=lambda c: (
        parse_order_date(c.last_order_date) is None,
        -(parse_order_date(c.last_order_date) or datetime.date.min).toordinal()
    ))

def sort_by_total_orders(clients):
    return sorted(clients, key=lambda c: c.total_orders, reverse=True)

def sort_clients(clients, sort_by):
    if sort_by == 'bonus_points':
        return sort_by_bonus_points(clients)
    elif sort_by == 'nearest_birthday':
        return sort_by_nearest_birthday(clients)
    elif sort_by == 'last_order_oldest':
        return sort_by_last_order_oldest(clients)
    elif sort_by == 'last_order_newest':
        return sort_by_last_order_newest(clients)
    elif sort_by == 'total_orders':
        return sort_by_total_orders(clients)
    else:
        return clients


@app.route('/')
def index():
    return redirect('/clients')

@app.route('/clients')
@login_required
def show_clients():
    params = get_filter_params()
    clients = fetch_filtered_clients(params)

    sorted_clients = sort_clients(clients, params['sort_by'])

    total_clients = len(sorted_clients)
    total_sum = sum(c['total_orders'] for c in sorted_clients if c['total_orders'])

    return render_template('clients.html',
                           clients=sorted_clients,
                           search=params['search'],
                           min_points=params['min_points'],
                           max_points=params['max_points'],
                           min_orders=params['min_orders'],
                           max_orders=params['max_orders'],
                           sort_by=params['sort_by'],
                           total_clients=total_clients,
                           total_sum=total_sum)

@app.route('/clients/new', methods=['GET', 'POST'])
@login_required
def add_client():
    if request.method == 'POST':
        birth_date = request.form['birth_date'].strip() or 'Отсутствует'
        last_order_date = request.form['last_order_date'].strip() or 'Отсутствует'

        client = Client(
            name=request.form['name'],
            phone=request.form['phone'],
            email=request.form['email'],
            total_orders=float(request.form['total_orders'] or 0),
            birth_date=birth_date,
            bonus_points=int(request.form['bonus_points'] or 0),
            last_order_date=last_order_date,
            user_id=current_user.id
        )
        db.session.add(client)
        db.session.commit()
        return redirect('/clients')

    return render_template('new_client.html')

@app.route('/clients/delete/<int:id>')
@login_required
def delete_client(id):
    client = Client.query.filter_by(id=id, user_id=current_user.id).first()

    if not client:
        return "Клиент не найден или доступ запрещён", 403

    db.session.delete(client)
    db.session.commit()

    return redirect('/clients')

@app.route('/clients/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_client(id):
    client = Client.query.filter_by(id=id, user_id=current_user.id).first()

    if not client:
        return "Клиент не найден или доступ запрещён", 403

    if request.method == 'POST':
        client.name = request.form['name']
        client.phone = request.form['phone']
        client.email = request.form['email']
        client.total_orders = float(request.form['total_orders'] or 0)
        client.birth_date = request.form['birth_date'].strip() or 'Отсутствует'
        client.bonus_points = int(request.form['bonus_points'] or 0)
        client.last_order_date = request.form['last_order_date'].strip() or 'Отсутствует'

        db.session.commit()

        return redirect('/clients')

    return render_template('edit_client.html', client=client)

@app.route('/clients/export')
@login_required
def export_clients():
    clients = Client.query.filter_by(user_id=current_user.id).all()

    wb = Workbook()
    ws = wb.active
    ws.title = "Клиенты"

    # Заголовки
    ws.append(["ID", "Имя", "Телефон", "Email", "Сумма заказов", "Дата рождения", "Бонусы", "Последний заказ"])

    # Данные
    for c in clients:
        ws.append([
            c.id,
            c.name,
            c.phone,
            c.email,
            c.total_orders,
            c.birth_date,
            c.bonus_points,
            c.last_order_date
        ])

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    return send_file(
        output,
        download_name="clients.xlsx",
        as_attachment=True,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

@app.route('/register', methods=['GET', 'POST'])
def register():
    message = None

    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']

        if len(username) < 3:
            message = "Логин должен быть минимум 3 символа"
        elif len(password) < 6:
            message = "Пароль должен быть минимум 6 символов"
        elif User.query.filter_by(username=username).first():
            message = "Пользователь уже существует"
        else:
            password_hash = generate_password_hash(password)
            new_user = User(username=username, password_hash=password_hash)
            db.session.add(new_user)
            db.session.commit()

            login_user(new_user)
            return redirect('/clients')

    return render_template('register.html', message=message)

@app.route('/login', methods=['GET', 'POST'])
def login():
    message = None

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect('/clients')
        else:
            message = "Неверный логин или пароль"

    return render_template('login.html', message=message)


@app.route('/change_password', methods=['GET', 'POST'])
@login_required
def change_password():
    message = None

    if request.method == 'POST':
        old_password = request.form['old_password']
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']

        user = User.query.get(current_user.id)

        if not user or not check_password_hash(user.password_hash, old_password):
            message = "Старый пароль неверен"
        elif len(new_password) < 6:
            message = "Новый пароль должен быть не менее 6 символов"
        elif new_password != confirm_password:
            message = "Новый пароль и его подтверждение не совпадают"
        else:
            user.password_hash = generate_password_hash(new_password)
            db.session.commit()
            return redirect('/clients')

    return render_template('change_password.html', message=message)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect('/login')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
