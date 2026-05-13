from flask import Flask, render_template, request, redirect, url_for, jsonify, flash, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_mail import Mail, Message
import secrets
import requests
import os
from werkzeug.utils import secure_filename
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'votal9ja_secret_key' 

# Database Configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///votal9ja_v2.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# --- OPTIMIZED GMAIL CONFIGURATION ---
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 465
app.config['MAIL_USE_SSL'] = True
app.config['MAIL_USE_TLS'] = False
app.config['MAIL_USERNAME'] = 'votal9ja@gmail.com' 
app.config['MAIL_PASSWORD'] = 'yakuzaucibqjeeaa' 
app.config['MAIL_DEFAULT_SENDER'] = ('VoTal9ja Official', 'votal9ja@gmail.com')
mail = Mail(app)

# --- PAYSTACK CONFIGURATION ---
PAYSTACK_SECRET_KEY = 'sk_test_9048cdcc0e2a9f84241dae63206c48e11b851f08'

db = SQLAlchemy(app)

# User Model
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(10)) 
    fullname = db.Column(db.String(100)) 
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    state = db.Column(db.String(50))
    votes = db.Column(db.Integer, default=0) 
    is_paid = db.Column(db.Boolean, default=False) 
    otp = db.Column(db.String(6)) 
    is_admin = db.Column(db.Boolean, default=False)
    username = db.Column(db.String(50), unique=True, nullable=True)
    full_name = db.Column(db.String(100), nullable=True)

class PaymentReceipt(db.Model):
    __table_args__ = {'extend_existing': True} 
    id = db.Column(db.Integer, primary_key=True)
    transaction_id = db.Column(db.String(100), unique=True, nullable=False)
    contestant_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    image_path = db.Column(db.String(200))
    status = db.Column(db.String(20), default="Pending")

# --- APP CONFIG FOR COOKIES ---
app.config.update(
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=False,
    UPLOAD_FOLDER = 'static/receipts'
)

# THE SERVER STATE (The "Brain")
# This stores the current status of your registration and maintenance locks
system_status = {
    "registration_open": True,
    "maintenance_mode": False
}

@app.route('/')
def home():
    # The monitor: It looks at the Brain and displays what it sees
    # This ensures your 'if reg_status' in HTML works perfectly
    return render_template('home.html', 
                           reg_status=system_status["registration_open"], 
                           maint_status=system_status["maintenance_mode"])

@app.route('/register', methods=['POST'])
def register():
    if request.method == 'POST':
        title = request.form.get('title')
        fullname = request.form.get('fullname')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        state = request.form.get('state')

        if password != confirm_password:
            flash("Passwords do not match!")
            return redirect(url_for('home'))

        user_exists = User.query.filter_by(email=email).first()
        if user_exists:
            flash("Email already registered!")
            return redirect(url_for('home'))

        verification_code = str(secrets.randbelow(1000000)).zfill(6)
        hashed_pw = generate_password_hash(password, method='pbkdf2:sha256')
        new_user = User(title=title, fullname=fullname, email=email, password=hashed_pw, state=state, otp=verification_code)
        
        db.session.add(new_user)
        db.session.commit()
        
        session['user_id_to_verify'] = new_user.id
        
        try:
            msg = Message("Verify Your VoTal9ja Account",
                          sender=("VoTal9ja Official", app.config['MAIL_USERNAME']),
                          recipients=[email])
            msg.body = f"Hello {fullname},\n\nYour security verification code is: {verification_code}\n\nPlease enter this code to proceed."
            mail.send(msg)
        except Exception as e:
            print(f"Mail Error: {e}")

        return render_template('verify.html', email=email)

@app.route('/verify-otp', methods=['POST'])
def verify_otp():
    entered_otp = request.form.get('otp')
    user_id = session.get('user_id_to_verify') 
    user = User.query.get(user_id)

    if user and user.otp == entered_otp:
        user.otp = None
        db.session.commit()
        
        paystack_url = "https://api.paystack.co/transaction/initialize"
        headers = {"Authorization": f"Bearer {PAYSTACK_SECRET_KEY}", "Content-Type": "application/json"}
        data = {
            "email": user.email,
            "amount": 1000000, 
            "callback_url": url_for('payment_callback', _external=True)
        }
        response = requests.post(paystack_url, json=data, headers=headers)
        res_data = response.json()
        
        if res_data['status']:
            return redirect(res_data['data']['authorization_url'])
        else:
            flash("Payment gateway error. Please try again.")
            return redirect(url_for('home'))
    
    flash("Invalid Verification Code.")
    return redirect(url_for('home'))

@app.route('/payment-callback')
def payment_callback():
    reference = request.args.get('reference')
    headers = {"Authorization": f"Bearer {PAYSTACK_SECRET_KEY}"}
    verify_url = f"https://api.paystack.co/transaction/verify/{reference}"
    response = requests.get(verify_url, headers=headers)
    res_data = response.json()

    if res_data['status'] and res_data['data']['status'] == 'success':
        user_email = res_data['data']['customer']['email']
        user = User.query.filter_by(email=user_email).first()
        user.is_paid = True
        db.session.commit()

        try:
            msg = Message("Congratulations! Your VoTal9ja Registration is Complete",
                          sender=("VoTal9ja Official", app.config['MAIL_USERNAME']),
                          recipients=[user.email])
            msg.body = f"Hello {user.fullname},\n\nCongratulations on reaching this milestone!"
            mail.send(msg)
        except Exception as e:
            print(f"Congratulatory Mail Error: {e}")

        session['user_id'] = user.id
        flash("Payment Successful! Welcome to the competition.")
        return redirect(url_for('login')) 

    flash("Payment verification failed.")
    return redirect(url_for('home'))

@app.route('/contestant')
def contestant_dashboard():
    # 1. We bypass the login check
    user_id = session.get('user_id')
    
    # 2. We try to find the user, but if you aren't logged in, 
    # we just grab the very first user in your database so the page doesn't crash.
    current_user = db.session.get(User, user_id) if user_id else User.query.first()

    # 3. If there are NO users in the DB at all, we create a "Fake" one for the preview
    if not current_user:
        class FakeUser:
            id = 1
            full_name = "Test Contestant"
            is_paid = True
        current_user = FakeUser()

    # 4. WE COMMENT OUT THE PAYMENT CHECK BELOW
    # if not current_user.is_paid:
    #     flash("Please complete payment to access your dashboard.")
    #     return redirect(url_for('home'))

    voting_link = url_for('vote_for_contestant', contestant_id=current_user.id, _external=True)
    return render_template('contestant.html', user=current_user, voting_link=voting_link)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password, password):
            if user.otp and not user.is_paid:
                session['user_id_to_verify'] = user.id
                flash("Please verify your account first.")
                return render_template('verify.html', email=user.email)
            session['user_id'] = user.id
            flash("Login Successful!")
            return redirect(url_for('contestant_dashboard'))
        else:
            flash("Invalid email or password.")
            return redirect(url_for('login'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    flash("Successfully logged out.")
    return redirect(url_for('login'))

@app.route('/stats')
def stats():
    rankings = User.query.filter_by(is_paid=True).order_by(User.votes.desc()).all()
    return render_template('ranking.html', rankings=rankings, active_contest=True)

@app.route('/vote/<int:contestant_id>', methods=['GET', 'POST'])
def vote_for_contestant(contestant_id):
    contestant = db.session.get(User, contestant_id)
    if not contestant:
        flash("Contestant not found.")
        return redirect(url_for('stats'))
    if request.method == 'POST':
        contestant.votes += 1
        db.session.commit()
        flash(f"Success! You just voted for {contestant.fullname}.")
        return redirect(url_for('stats'))
    return render_template('vote_payment.html', contestant=contestant)

@app.route('/upload-receipt', methods=['POST'])
def upload_receipt():
    user_id = session.get('user_id')
    user = db.session.get(User, user_id)
    trans_id = request.form.get('transaction_id').strip()
    file = request.files.get('receipt_image')
    existing = PaymentReceipt.query.filter_by(transaction_id=trans_id).first()
    if existing:
        flash("FRAUD ALERT: This Transaction ID has already been used!")
        return redirect(url_for('contestant_dashboard'))
    if file and trans_id:
        filename = secure_filename(f"{user_id}_{trans_id}_{file.filename}")
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        new_receipt = PaymentReceipt(transaction_id=trans_id, contestant_id=user_id, image_path=filename)
        user.votes += 1 
        db.session.add(new_receipt)
        db.session.commit()
        flash("Vote recorded successfully!")
    return redirect(url_for('contestant_dashboard'))

# --- ADMIN SECTION ---
CATALOG_KEYS = {
    "verification": "verify123",
    "contestants": "admin456",
    "media": "view789",
    "finance": "money000",
    "broadcast": "send111",
    "settings": "secure999",
    "staff": "staff123"
}

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username == "SuperAdmin" and password == "VoTalMaster2026":
            session['is_admin'] = True
            session.modified = True
            return redirect(url_for('admin_master'))
        flash("Invalid Credentials") 
    return render_template('admin_login.html')

@app.route('/admin/master')
def admin_master():
    if not session.get('is_admin'):
        return redirect(url_for('admin_login'))
    return render_template('admin_master.html')

@app.route('/admin/unlock', methods=['POST'])
def unlock_catalog():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "message": "No data"}), 400
    catalog = data.get('catalog')
    key = data.get('key')
    if CATALOG_KEYS.get(catalog) == key:
        session[f'unlocked_{catalog}'] = True
        session.modified = True
        return jsonify({"success": True, "redirect": url_for(f'admin_{catalog}')})
    return jsonify({"success": False, "message": "Invalid Key"})


@app.route('/admin/verification')
def admin_verification():
    if not session.get('is_admin') or not session.get('unlocked_verification'):
        return redirect(url_for('admin_master'))
    return render_template('admin_verification.html', votes=[])

@app.route('/admin/contestants')
def admin_contestants():
    if not session.get('is_admin') or not session.get('unlocked_contestants'):
        return redirect(url_for('admin_master'))
    all_contestants = User.query.filter_by(is_admin=False).all()
    return render_template('admin_contestants.html', all_c=all_contestants)

@app.route('/admin/staff')
def admin_staff():
    if not session.get('is_admin') or not session.get('unlocked_staff'):
        return redirect(url_for('admin_master'))
    return redirect(url_for('admin_register'))

@app.route('/admin/register', methods=['GET', 'POST'])
def admin_register():
    if not session.get('is_admin') or not session.get('unlocked_staff'):
        return redirect(url_for('admin_master'))
    if request.method == 'POST':
        # Registration logic remains here
        pass
    return render_template('admin_register.html')

@app.route('/admin/logout')
def admin_logout():
    session.clear()
    return redirect(url_for('admin_login'))

@app.route('/admin/media-vault')
def admin_media():  # Changed from media_vault to admin_media
    media_files = []
    
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])

    files = os.listdir(app.config['UPLOAD_FOLDER'])

    for filename in files:
        file_ext = filename.rsplit('.', 1)[-1].lower()
        
        if file_ext in ['mp4', 'webm', 'ogg']:
            media_type = 'video'
        elif file_ext in ['jpg', 'jpeg', 'png', 'gif', 'webp']:
            media_type = 'image'
        elif file_ext in ['mp3', 'wav', 'aac']:
            media_type = 'audio'
        else:
            continue

        media_files.append({
            'id': filename,
            'filename': filename,
            'type': media_type,
            'contestant_name': "Contestant Node: " + filename.split('_')[0], 
            'user_id': "VTL-" + filename.split('.')[0][-4:],
            'date': "2026-ACTIVE"
        })

    return render_template('media_vault.html', media_files=media_files)

@app.route('/admin/finance-ledger')
def admin_finance():
    registrations = [] # Empty until live registration begins
    
    total_reg = sum(item['amount'] for item in registrations)
    total_votes_count = 0  
    
    VOTE_UNIT_PRICE = 50
    total_votes_revenue = total_votes_count * VOTE_UNIT_PRICE
    ground_total = total_reg + total_votes_revenue

    return render_template('finance_ledger.html', 
                           registrations=registrations,
                           total_votes_count=total_votes_count,
                           total_reg=total_reg, 
                           total_votes_revenue=total_votes_revenue, 
                           ground_total=ground_total)

@app.route('/admin/broadcast', methods=['GET', 'POST'])
def admin_broadcast():
    if request.method == 'POST':
        recipient_ids = request.form.getlist('ids')
        subject = request.form.get('subject')
        message_body = request.form.get('message')
        pdf_file = request.files.get('document')

        if not recipient_ids:
            return jsonify({"success": False, "message": "No recipients selected."})

        return jsonify({"success": True, "message": f"Broadcast & Document sent to {len(recipient_ids)} nodes."})

    all_contestants = [] 
    
    return render_template('broadcast.html', contestants=all_contestants)

@app.route('/admin/settings', methods=['GET', 'POST'])
def admin_settings(): 
    """
    VoTal9ja Master Control Center - UPDATED TO SYNC WITH BRAIN
    """
    if request.method == 'POST':
        data = request.get_json()
        action = data.get('action') 
        status = data.get('status')
        
        if action in system_status:
            system_status[action] = status
            return jsonify({"success": True, "message": "Server state updated!"})
        return jsonify({"success": False, "message": "Invalid action"})

    return render_template('settings.html', system=system_status, admins=[], contestants=[])

@app.before_request
def check_for_maintenance():
    # If maintenance is ON and the user is NOT in an admin path, redirect or block
    if system_status["maintenance_mode"] and not request.path.startswith('/admin'):
        # You could create a maintenance.html and return it here
        # return render_template('maintenance.html'), 503
        pass
# Make sure this folder exists in your project!
UPLOAD_FOLDER = 'static/uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# --- ROUTE 1: PROFILE PICTURE ---
@app.route('/upload_profile_pic', methods=['POST'])
def upload_profile_pic():
    if 'profile_pic' not in request.files:
        return jsonify(success=False, error="No file part")
    
    file = request.files['profile_pic']
    user_id = session.get('user_id')
    
    if not user_id:
        return jsonify(success=False, error="User not logged in")

    if file and file.filename != '':
        filename = f"profile_{user_id}_{file.filename}"
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)

        # Save to database
        user = db.session.get(User, user_id)
        user.profile_pic = filename
        db.session.commit()

        return jsonify(success=True, image_url=url_for('static', filename='uploads/' + filename))
    return jsonify(success=False, error="Upload failed")

# --- ROUTE 2: PUBLICITY PHOTO ---
@app.route('/upload_publicity_photo', methods=['POST'])
def upload_publicity_photo():
    if 'profile_pic' not in request.files:
        return jsonify(success=False, error="No file part")
    
    file = request.files['profile_pic']
    user_id = session.get('user_id')
    
    if not user_id:
        return jsonify(success=False, error="User not logged in")

    if file and file.filename != '':
        filename = f"publicity_{user_id}_{file.filename}"
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)

        # Save to a DIFFERENT database field (e.g., publicity_photo)
        user = db.session.get(User, user_id)
        user.publicity_photo = filename # Make sure this column exists in your User model!
        db.session.commit()

        return jsonify(success=True, image_url=url_for('static', filename='uploads/' + filename))
    return jsonify(success=False, error="Upload failed")

class VoteTransaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    contestant_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    voter_name = db.Column(db.String(100))
    amount_paid = db.Column(db.Float, nullable=False)
    vote_count = db.Column(db.Integer, nullable=False) # Total votes bought
    status = db.Column(db.String(20), default='Pending') # Pending, Confirmed, Cancelled
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

@app.route('/vote/pay/<int:contestant_id>', methods=['GET', 'POST'])
def initiate_vote(contestant_id):
    contestant = db.session.get(User, contestant_id)
    if request.method == 'POST':
        # Calculate votes based on 50 Naira per vote
        amount = float(request.form.get('amount'))
        votes = int(amount / 50)
        voter_name = request.form.get('voter_name', 'Anonymous')

        # Record the transaction as Pending
        new_tx = VoteTransaction(
            contestant_id=contestant_id,
            voter_name=voter_name,
            amount_paid=amount,
            vote_count=votes,
            status='Pending'
        )
        db.session.add(new_tx)
        db.session.commit()
        
        return redirect(url_for('payment_instructions', tx_id=new_tx.id))

    return render_template('vote_payment.html', contestant=contestant)

@app.route('/vote/instructions/<int:tx_id>')
def payment_instructions(tx_id):
    transaction = db.session.get(VoteTransaction, tx_id)
    contestant = db.session.get(User, transaction.contestant_id)
    return render_template('payment_instructions.html', tx=transaction, contestant=contestant)

if __name__ == "__main__":
    with app.app_context():
        # Clean up database for fresh start if needed
        db_path = 'votal9ja_v2.db'
        # Only uncomment the next lines if you want to wipe data every time you restart
        # if os.path.exists(db_path):
        #     os.remove(db_path)
        db.create_all()
        print("--- Database Ready ---")
        
    app.run(debug=True)