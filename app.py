from flask import Flask, request, render_template, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta

app = Flask(__name__, static_folder='static')
app.secret_key = 'secret123'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///bank.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(80), nullable=False)
    balance = db.Column(db.Float, default=0.0)
    is_admin = db.Column(db.Boolean, default=False)  # Added is_admin field

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    type = db.Column(db.String(20))
    amount = db.Column(db.Float)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    target_user = db.Column(db.Integer, nullable=True)

class Loan(db.Model):
    __tablename__ = 'loan'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    duration_months = db.Column(db.Integer, nullable=False)
    due_date = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(50), default='Pending')
    user = db.relationship('User', backref='loans')

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if User.query.filter_by(username=username).first():
            return render_template('register.html', error="User already exists.")
        user = User(username=username, password=password)
        db.session.add(user)
        db.session.commit()
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username'], password=request.form['password']).first()
        if user:
            session['user_id'] = user.id
            session['is_admin'] = user.is_admin
            return redirect(url_for('dashboard'))
        else:
            return render_template('login.html', error='Invalid credentials.')
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    transactions = Transaction.query.filter_by(user_id=user.id).all()
    loans = Loan.query.filter_by(user_id=user.id).all()
    return render_template('dashboard.html', user=user, transactions=transactions, loans=loans)

@app.route('/deposit', methods=['POST'])
def deposit():
    user = User.query.get(session['user_id'])
    amount = float(request.form['amount'])
    user.balance += amount
    txn = Transaction(user_id=user.id, type='deposit', amount=amount)
    db.session.add(txn)
    db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/withdraw', methods=['POST'])
def withdraw():
    user = User.query.get(session['user_id'])
    amount = float(request.form['amount'])
    if user.balance >= amount:
        user.balance -= amount
        txn = Transaction(user_id=user.id, type='withdraw', amount=amount)
        db.session.add(txn)
        db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/transfer', methods=['POST'])
def transfer():
    sender = User.query.get(session['user_id'])
    receiver = User.query.filter_by(username=request.form['to']).first()
    amount = float(request.form['amount'])
    if receiver and sender.balance >= amount:
        sender.balance -= amount
        receiver.balance += amount
        txn = Transaction(user_id=sender.id, type='transfer', amount=amount, target_user=receiver.id)
        db.session.add(txn)
        db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/apply-loan', methods=['POST'])
def apply_loan():
    user = User.query.get(session['user_id'])
    amount = float(request.form['amount'])
    duration = int(request.form['duration'])
    due = datetime.utcnow() + timedelta(days=30 * duration)
    loan = Loan(user_id=user.id, amount=amount, duration_months=duration, due_date=due)
    db.session.add(loan)
    db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/admin/loan-applications')
def admin_loan_applications():
    if not session.get('is_admin'):
        return redirect(url_for('login'))
    loans = Loan.query.filter_by(status='Pending').all()
    return render_template('admin_loan_applications.html', loans=loans)

@app.route('/admin/approve-loan/<int:loan_id>')
def approve_loan(loan_id):
    loan = Loan.query.get_or_404(loan_id)
    loan.status = 'Approved'

    # user = loan.user  # Get the user associated with the loan
    # user.update_balance(loan.amount)  # Add loan amount to user balance
    try:
        db.session.commit()
        return redirect(url_for('admin_loan_applications'))
    except Exception as e:
        db.session.rollback()
        return f"Error approving loan: {e}"

@app.route('/admin/reject-loan/<int:loan_id>')
def reject_loan(loan_id):
    loan = Loan.query.get_or_404(loan_id)
    loan.status = 'Rejected'
    try:
        db.session.commit()
        return redirect(url_for('admin_loan_applications'))
    except Exception as e:
        db.session.rollback()
        return f"Error rejecting loan: {e}"

# if __name__ == '__main__':
#     with app.app_context():
#         db.create_all()
#     app.run(debug=True)


from flask import send_file
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import io

@app.route('/download_statement')
def download_statement():
    if 'user_id' not in session:
        return redirect('/login')

    user_id = session['user_id']
    user = User.query.get(user_id)
    transactions = Transaction.query.filter_by(user_id=user_id).order_by(Transaction.timestamp.desc()).all()

    # Create PDF
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    pdf.setTitle("Bank Statement")

    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(200, 750, "Bank Statement")
    pdf.setFont("Helvetica", 12)
    pdf.drawString(50, 720, f"Username: {user.username} | User ID: {user.id}")

    y = 700
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(50, y, "Date")
    pdf.drawString(150, y, "Type")
    pdf.drawString(250, y, "Amount")
    pdf.drawString(350, y, "To/From")

    y -= 20
    pdf.setFont("Helvetica", 10)

    for txn in transactions:
        pdf.drawString(50, y, txn.timestamp.strftime('%Y-%m-%d'))
        pdf.drawString(150, y, txn.type.capitalize())
        pdf.drawString(250, y, f"₹{txn.amount:.2f}")
        target = f"User ID {txn.target_user}" if txn.target_user else "-"
        pdf.drawString(350, y, target)

        y -= 20
        if y < 50:
            pdf.showPage()
            y = 750

    pdf.save()
    buffer.seek(0)

    return send_file(buffer, as_attachment=True, download_name="bank_statement.pdf", mimetype='application/pdf')


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
    