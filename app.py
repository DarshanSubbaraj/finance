from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from io import BytesIO
import base64
import pandas as pd
from datetime import datetime
import csv

app = Flask(__name__)

app.config['SECRET_KEY'] = 'your-secret-key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:alpha4563@localhost/family_finance'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    expenses = db.relationship('Expense', backref='user', lazy=True, cascade='all, delete-orphan')

class Expense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    category = db.Column(db.String(50), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    description = db.Column(db.String(100))
    date = db.Column(db.Date, nullable=False, default=datetime.utcnow().date)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

def create_pie_chart(expenses):
    categories = {}
    for expense in expenses:
        if expense.category in categories:
            categories[expense.category] += expense.amount
        else:
            categories[expense.category] = expense.amount
    
    plt.figure(figsize=(6, 6))
    plt.pie(categories.values(), labels=categories.keys(), autopct='%1.1f%%')
    plt.title('Spending by Category')
    
    buffer = BytesIO()
    plt.savefig(buffer, format='png')
    buffer.seek(0)
    plt.close()
    return base64.b64encode(buffer.getvalue()).decode('utf-8')

def create_time_chart(expenses, time_period='month'):
    data = []
    for e in expenses:
        data.append({
            'date': pd.to_datetime(e.date),
            'amount': e.amount
        })
    
    df = pd.DataFrame(data)
    
    if df.empty:
        return create_empty_chart()
    
    if time_period == 'day':
        df['period'] = df['date'].dt.date
        title = 'Daily Spending'
    elif time_period == 'month':
        df['period'] = df['date'].dt.to_period('M').astype(str)
        title = 'Monthly Spending'
    else:
        df['period'] = df['date'].dt.to_period('Y').astype(str)
        title = 'Yearly Spending'
    
    grouped = df.groupby('period')['amount'].sum()
    
    plt.figure(figsize=(10, 5))
    if not grouped.empty:
        plt.bar(grouped.index, grouped.values)
    plt.title(title)
    plt.xlabel('Time Period')
    plt.ylabel('Amount ($)')
    plt.xticks(rotation=45)
    
    buffer = BytesIO()
    plt.savefig(buffer, format='png')
    buffer.seek(0)
    plt.close()
    return base64.b64encode(buffer.getvalue()).decode('utf-8')

def create_empty_chart():
    plt.figure(figsize=(10, 5))
    plt.text(0.5, 0.5, 'No data available', ha='center', va='center')
    plt.axis('off')
    
    buffer = BytesIO()
    plt.savefig(buffer, format='png')
    buffer.seek(0)
    plt.close()
    return base64.b64encode(buffer.getvalue()).decode('utf-8')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        if User.query.filter_by(username=username).first():
            flash('Username already exists!', 'error')
        else:
            new_user = User(username=username, password=password)
            db.session.add(new_user)
            db.session.commit()
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        
        if not user:
            flash('Invalid username or password!', 'error')
            return redirect(url_for('login'))
        
        if user.password == request.form['password']:
            session['user_id'] = user.id
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password!', 'error')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('login'))

@app.route('/')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    
    if not user:
        flash('User not found! Please login again.', 'error')
        session.pop('user_id', None)
        return redirect(url_for('login'))
    
    time_period = request.args.get('time_period', 'month')
    
    pie_chart = create_pie_chart(user.expenses)
    time_chart = create_time_chart(user.expenses, time_period)
    
    return render_template('dashboard.html', 
                         expenses=user.expenses,
                         pie_chart=pie_chart,
                         time_chart=time_chart,
                         time_period=time_period)

@app.route('/add', methods=['GET', 'POST'])
def add_expense():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        try:
            expense_date = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
            new_expense = Expense(
                category=request.form['category'],
                amount=float(request.form['amount']),
                description=request.form['description'],
                date=expense_date,
                user_id=session['user_id']
            )
            db.session.add(new_expense)
            db.session.commit()
            flash('Expense added successfully!', 'success')
            return redirect(url_for('dashboard'))
        except ValueError as e:
            flash(f'Invalid date format: {str(e)}', 'error')
    
    default_date = datetime.utcnow().strftime('%Y-%m-%d')
    return render_template('add_expense.html', default_date=default_date)

@app.route('/edit/<int:id>', methods=['GET', 'POST'])
def edit_expense(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    expense = Expense.query.get_or_404(id)
    
    if expense.user_id != session['user_id']:
        flash('You cannot edit this expense!', 'error')
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        try:
            expense.date = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
            expense.category = request.form['category']
            expense.amount = float(request.form['amount'])
            expense.description = request.form['description']
            db.session.commit()
            flash('Expense updated successfully!', 'success')
            return redirect(url_for('dashboard'))
        except ValueError as e:
            flash(f'Invalid date format: {str(e)}', 'error')
    
    return render_template('edit_expense.html', expense=expense)

@app.route('/delete/<int:id>')
def delete_expense(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    expense = Expense.query.get_or_404(id)
    
    if expense.user_id != session['user_id']:
        flash('You cannot delete this expense!', 'error')
    else:
        db.session.delete(expense)
        db.session.commit()
        flash('Expense deleted successfully!', 'success')
    
    return redirect(url_for('dashboard'))

@app.route('/upload', methods=['POST'])
def upload_csv():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    if 'csv_file' not in request.files:
        flash('No file selected', 'error')
        return redirect(url_for('dashboard'))
    
    file = request.files['csv_file']
    if file.filename == '':
        flash('No file selected', 'error')
        return redirect(url_for('dashboard'))
    
    if file and file.filename.endswith('.csv'):
        try:
            df = pd.read_csv(file)
            for _, row in df.iterrows():
                expense = Expense(
                    category=row['Category'],
                    amount=float(row['Amount']),
                    description=row.get('Description', ''),
                    date=datetime.strptime(row['Date'], '%Y-%m-%d').date(),
                    user_id=session['user_id']
                )
                db.session.add(expense)
            db.session.commit()
            flash('CSV imported successfully!', 'success')
        except Exception as e:
            flash(f'Error importing CSV: {str(e)}', 'error')
    
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)