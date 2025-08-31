# Gerekli kütüphaneleri ve modülleri içe aktarıyoruz
from flask import Flask, render_template, request, redirect, url_for, flash, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import os
from datetime import date, datetime
import calendar

# --- UYGULAMA YAPILANDIRMASI ---
app = Flask(__name__)
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SECRET_KEY'] = 'bu-anahtari-kimseyle-paylasma'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'database.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# --- KÜTÜPHANE ENTEGRASYONLARI ---
db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# --- VERİTABANI MODELLERİ ---
transaction_members = db.Table('transaction_members',
    db.Column('transaction_id', db.Integer, db.ForeignKey('transaction.id'), primary_key=True),
    db.Column('member_id', db.Integer, db.ForeignKey('member.id'), primary_key=True)
)

class Member(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    def __repr__(self): return f'<Member {self.name}>'

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(10), nullable=False)
    description = db.Column(db.String(100), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    date = db.Column(db.Date, nullable=False, default=date.today)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    members = db.relationship('Member', secondary=transaction_members, lazy='subquery',
        backref=db.backref('transactions', lazy=True))

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    transactions = db.relationship('Transaction', backref='user', lazy=True)
    def set_password(self, password): self.password_hash = generate_password_hash(password)
    def check_password(self, password): return check_password_hash(self.password_hash, password)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- ROUTE'LAR (SAYFALAR) ---
@app.route('/')
@login_required
def index():
    today = date.today()
    year = request.args.get('year', default=today.year, type=int)
    month = request.args.get('month', default=today.month, type=int)
    start_date = date(year, month, 1)
    end_date = date(year, month, calendar.monthrange(year, month)[1])
    monthly_transactions = Transaction.query.filter(
        Transaction.user_id == current_user.id,
        Transaction.date >= start_date,
        Transaction.date <= end_date
    ).order_by(Transaction.date.desc()).all()
    all_transactions = Transaction.query.filter_by(user_id=current_user.id).all()
    total_bakiye = sum(t.amount for t in all_transactions if t.type == 'gelir') - sum(t.amount for t in all_transactions if t.type == 'gider')
    monthly_bakiye = sum(t.amount for t in monthly_transactions if t.type == 'gelir') - sum(t.amount for t in monthly_transactions if t.type == 'gider')
    month_names = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
    all_members = Member.query.all()
    return render_template('index.html', 
                           transactions=monthly_transactions, bakiye=total_bakiye, monthly_bakiye=monthly_bakiye,
                           selected_year=year, selected_month=month, month_names=month_names,
                           current_year=today.year, today=today.isoformat(), all_members=all_members)

@app.route('/add', methods=['POST'])
@login_required
def add_transaction():
    yeni_islem = Transaction(
        type=request.form.get('type'),
        description=request.form.get('description'),
        amount=float(request.form.get('amount')),
        date=datetime.strptime(request.form.get('transaction_date'), '%Y-%m-%d').date(),
        user_id=current_user.id  # ---- HATA BURADA DÜZELTİLDİ ----
    )
    member_ids = request.form.getlist('members')
    if not member_ids:
        flash('Lütfen işlemi yapan en az bir kişi seçin!', 'warning')
        return redirect(url_for('index', year=yeni_islem.date.year, month=yeni_islem.date.month))

    for member_id in member_ids:
        member = Member.query.get(member_id)
        if member:
            yeni_islem.members.append(member)
        
    db.session.add(yeni_islem)
    db.session.commit()
    return redirect(url_for('index', year=yeni_islem.date.year, month=yeni_islem.date.month))

@app.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_transaction(id):
    transaction_to_edit = Transaction.query.get_or_404(id)
    if transaction_to_edit.user_id != current_user.id:
        abort(403)
    if request.method == 'POST':
        transaction_to_edit.type = request.form.get('type')
        transaction_to_edit.description = request.form.get('description')
        transaction_to_edit.amount = float(request.form.get('amount'))
        transaction_to_edit.date = datetime.strptime(request.form.get('transaction_date'), '%Y-%m-%d').date()
        member_ids = request.form.getlist('members')
        if not member_ids:
            flash('Lütfen işlemi yapan en az bir kişi seçin!', 'warning')
            return redirect(url_for('edit_transaction', id=id))
        transaction_to_edit.members.clear()
        for member_id in member_ids:
            member = Member.query.get(member_id)
            if member:
                transaction_to_edit.members.append(member)
        db.session.commit()
        flash('İşlem başarıyla güncellendi!', 'success')
        return redirect(url_for('index', year=transaction_to_edit.date.year, month=transaction_to_edit.date.month))
    all_members = Member.query.all()
    return render_template('edit_transaction.html', transaction=transaction_to_edit, all_members=all_members)

@app.route('/delete/<int:id>')
@login_required
def delete_transaction(id):
    silinecek_islem = Transaction.query.get_or_404(id)
    if silinecek_islem.user_id != current_user.id:
        abort(403)
    db.session.delete(silinecek_islem)
    db.session.commit()
    flash('İşlem başarıyla silindi.', 'success')
    return redirect(request.referrer or url_for('index'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username')).first()
        if user and user.check_password(request.form.get('password')):
            login_user(user)
            return redirect(url_for('index'))
        else:
            flash('Giriş başarısız. Kullanıcı adı veya şifre hatalı.', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Başarıyla çıkış yaptınız.', 'success')
    return redirect(url_for('login'))

# --- UYGULAMAYI ÇALIŞTIRMA ---
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(username='camdibi').first():
            default_user = User(username='camdibi')
            default_user.set_password('mınka')
            db.session.add(default_user)
        member_names = ['aytun', 'kınık', 'kandemir']
        for name in member_names:
            if not Member.query.filter_by(name=name).first():
                member = Member(name=name)
                db.session.add(member)
        db.session.commit()
    app.run(debug=True)