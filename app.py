# Gerekli kütüphaneleri ve modülleri içe aktarıyoruz
from flask import Flask, render_template, request, redirect, url_for, flash, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import os
from datetime import date, datetime 

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
login_manager.login_message = "Bu sayfayı görüntülemek için lütfen giriş yapın."
login_manager.login_message_category = "info"

# --- VERİTABANI MODELLERİ ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    transactions = db.relationship('Transaction', backref='owner', lazy=True)
    def set_password(self, password): self.password_hash = generate_password_hash(password)
    def check_password(self, password): return check_password_hash(self.password_hash, password)

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(10), nullable=False)
    description = db.Column(db.String(100), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    date = db.Column(db.Date, nullable=False, default=date.today)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- ROUTE'LAR (SAYFALAR) ---
@app.route('/')
@login_required
def index():
    transactions = Transaction.query.filter_by(user_id=current_user.id).order_by(Transaction.date.desc()).all()
    total_gelir = sum(t.amount for t in transactions if t.type == 'gelir')
    total_gider = sum(t.amount for t in transactions if t.type == 'gider')
    bakiye = total_gelir - total_gider
    today = date.today().isoformat()
    return render_template('index.html', transactions=transactions, bakiye=bakiye, today=today)

# YENİ EKLENEN DÜZENLEME SAYFASI VE MANTIĞI
@app.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_transaction(id):
    # Düzenlenecek işlemi ID'sine göre bul
    transaction_to_edit = Transaction.query.get_or_404(id)

    # Güvenlik Kontrolü: Kullanıcı sadece kendi işlemini düzenleyebilir
    if transaction_to_edit.owner != current_user:
        abort(403) # Yetkisiz erişim hatası ver

    if request.method == 'POST':
        # Formdan gelen yeni verileri al
        transaction_to_edit.type = request.form.get('type')
        transaction_to_edit.description = request.form.get('description')
        transaction_to_edit.amount = float(request.form.get('amount'))
        transaction_date_str = request.form.get('transaction_date')
        transaction_to_edit.date = datetime.strptime(transaction_date_str, '%Y-%m-%d').date()

        # Veritabanında güncelle
        db.session.commit()
        flash('İşlem başarıyla güncellendi!', 'success')
        return redirect(url_for('index'))

    # GET isteği yapıldığında, formu mevcut bilgilerle doldurarak göster
    return render_template('edit_transaction.html', transaction=transaction_to_edit)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('index'))
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username')).first()
        if user and user.check_password(request.form.get('password')):
            login_user(user)
            return redirect(url_for('index'))
        else:
            flash('Giriş başarısız. Kullanıcı adı veya şifre hatalı.', 'danger')
            return redirect(url_for('login'))
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Başarıyla çıkış yaptınız.', 'success')
    return redirect(url_for('login'))

@app.route('/add', methods=['POST'])
@login_required
def add_transaction():
    yeni_islem = Transaction(
        type=request.form.get('type'),
        description=request.form.get('description'),
        amount=float(request.form.get('amount')),
        date=datetime.strptime(request.form.get('transaction_date'), '%Y-%m-%d').date(),
        owner=current_user
    )
    db.session.add(yeni_islem)
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/delete/<int:id>')
@login_required
def delete_transaction(id):
    silinecek_islem = Transaction.query.get_or_404(id)
    if silinecek_islem.owner != current_user:
        abort(403)
    db.session.delete(silinecek_islem)
    db.session.commit()
    flash('İşlem başarıyla silindi.', 'success')
    return redirect(url_for('index'))

# --- UYGULAMAYI ÇALIŞTIRMA ---
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(username='camdibi').first():
            default_user = User(username='camdibi')
            default_user.set_password('mınka')
            db.session.add(default_user)
            db.session.commit()
    app.run(debug=True)