import os
import json
from datetime import datetime, date, timedelta
import random
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['SECRET_KEY'] = 'choloka_secret_key_2026'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# File uploads config
app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload size globally

# Mail settings
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'shota.cholokava17@gmail.com'
app.config['MAIL_PASSWORD'] = 'vgdc lvtc iozy jwni'
app.config['MAIL_DEFAULT_SENDER'] = 'shota.cholokava17@gmail.com'

db = SQLAlchemy(app)
mail = Mail(app)

login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

# Ensure upload subfolders exist
UPLOAD_FOLDERS = [
    'static/uploads/profiles',
    'static/uploads/pdfs',
    'static/uploads/posts',
    'static/uploads/chat',
    'static/uploads/ads'
]
for folder in UPLOAD_FOLDERS:
    os.makedirs(os.path.join(app.root_path, folder), exist_ok=True)

# --- Database Models ---

followers = db.Table('followers',
    db.Column('follower_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('followed_id', db.Integer, db.ForeignKey('user.id'), primary_key=True)
)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(250), nullable=False)
    role = db.Column(db.String(50), nullable=False)  # 'teacher', 'student', 'other'
    
    # Profile information
    school = db.Column(db.String(150), nullable=True)
    city = db.Column(db.String(100), nullable=True)
    phone = db.Column(db.String(50), nullable=True)
    bio = db.Column(db.Text, nullable=True)
    profile_pic = db.Column(db.String(250), nullable=True)  # filename in static/uploads/profiles
    cv_url = db.Column(db.String(250), nullable=True)  # filename in static/uploads/pdfs
    custom_badge = db.Column(db.String(100), nullable=True)  # approved custom label (e.g. School Principal)
    
    # Auth and status
    is_verified = db.Column(db.Boolean, default=False)
    verification_code = db.Column(db.String(10), nullable=True)
    is_admin = db.Column(db.Boolean, default=False)
    is_blocked = db.Column(db.Boolean, default=False)
    login_email_notify = db.Column(db.Boolean, default=True)  # Send email on each login
    
    # Relationships
    posts = db.relationship('Post', backref='author', lazy=True, cascade='all, delete-orphan')
    notifications = db.relationship('Notification', backref='user', lazy=True, cascade='all, delete-orphan')
    login_histories = db.relationship('LoginHistory', backref='user', lazy=True, cascade='all, delete-orphan')
    followed = db.relationship(
        'User', secondary=followers,
        primaryjoin=(followers.c.follower_id == id),
        secondaryjoin=(followers.c.followed_id == id),
        backref=db.backref('followers', lazy='dynamic'), lazy='dynamic')
        
    def is_following(self, user):
        return self.followed.filter(followers.c.followed_id == user.id).count() > 0

    def follow(self, user):
        if not self.is_following(user):
            self.followed.append(user)

    def unfollow(self, user):
        if self.is_following(user):
            self.followed.remove(user)

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    media_url = db.Column(db.String(500), nullable=True)  # Video link (youtube)
    status = db.Column(db.String(50), default='pending')  # 'pending', 'approved'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Sharing functionality
    original_post_id = db.Column(db.Integer, db.ForeignKey('post.id', ondelete='SET NULL'), nullable=True)
    is_shared = db.Column(db.Boolean, default=False)
    original_post = db.relationship('Post', remote_side=[id], backref=db.backref('shares', lazy=True))
    
    # Relationships
    media = db.relationship('PostMedia', backref='post', lazy=True, cascade='all, delete-orphan')
    likes = db.relationship('PostLike', backref='post', lazy=True, cascade='all, delete-orphan')
    comments = db.relationship(
        'PostComment',
        backref='post',
        lazy=True,
        cascade='all, delete-orphan'
    )

class PostMedia(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id', ondelete='CASCADE'), nullable=False)
    file_path = db.Column(db.String(250), nullable=False)  # filename in static/uploads/posts

class PostLike(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id', ondelete='CASCADE'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint('post_id', 'user_id', name='_post_user_like_uc'),)
    user = db.relationship('User', backref=db.backref('likes', lazy=True))

class PostComment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id', ondelete='CASCADE'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_pinned = db.Column(db.Boolean, default=False)
    user = db.relationship('User', backref=db.backref('comments', lazy=True))

class DirectMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, nullable=False)
    recipient_id = db.Column(db.Integer, nullable=False)
    content = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_read = db.Column(db.Boolean, default=False)
    is_deleted = db.Column(db.Boolean, default=False)
    
    # File transfer support
    file_url = db.Column(db.String(250), nullable=True)  # filename in static/uploads/chat
    file_name = db.Column(db.String(250), nullable=True)  # original filename
    is_image = db.Column(db.Boolean, default=False)

class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    form_template = db.Column(db.Text, nullable=False)  # JSON string describing the custom template fields

class CourseRegistration(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    registration_data = db.Column(db.Text, nullable=False)  # JSON string containing user inputs
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    course = db.relationship('Course', backref='registrations')
    user = db.relationship('User', backref='registrations')

class Poll(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    question = db.Column(db.String(300), nullable=False)
    options = db.Column(db.Text, nullable=False)  # JSON string of list of choices, e.g. ["A", "B", "C"]
    date_scheduled = db.Column(db.String(10), nullable=False)  # YYYY-MM-DD format for calendar scheduling

class PollVote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    poll_id = db.Column(db.Integer, db.ForeignKey('poll.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    selected_option = db.Column(db.String(150), nullable=False)
    poll = db.relationship('Poll', backref='votes')

class AdminChat(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    sender_role = db.Column(db.String(50), nullable=False)  # 'user' or 'admin'
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship('User', backref='admin_chats')

class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.String(500), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_read = db.Column(db.Boolean, default=False)

class LoginHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    login_time = db.Column(db.DateTime, default=datetime.utcnow)

class Ad(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    image_url = db.Column(db.String(250), nullable=False)  # filename in static/uploads/ads
    link_url = db.Column(db.String(250), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    end_time = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class BadgeRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    requested_badge = db.Column(db.String(100), nullable=False)
    justification = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(50), default='pending')  # 'pending', 'approved', 'rejected'
    admin_explanation = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship('User', backref='badge_requests')

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- Custom Filters ---
@app.template_filter('youtube_embed')
def youtube_embed(url):
    import re
    if not url:
        return ""
    match = re.search(r'(?:youtube\.com\/(?:[^\/]+\/.+\/|(?:v|e(?:mbed)?)\/|.*[?&]v=)|youtu\.be\/)([^"&?\/\s]{11})', url)
    if match:
        return f"https://www.youtube.com/embed/{match.group(1)}"
    return url

# --- Helper Functions ---

def send_email(subject, recipient, body_html):
    try:
        msg = Message(subject, recipients=[recipient])
        msg.html = body_html
        msg.charset = 'utf-8'
        mail.send(msg)
        try:
            print(f"[EMAIL SENT] To: {recipient} | Subject: {subject}")
        except UnicodeEncodeError:
            print(f"[EMAIL SENT] To: {recipient} | Subject: <Contains Georgian characters>")
        return True
    except Exception as e:
        try:
            print(f"[EMAIL ERROR] Could not send email to {recipient}: {e}")
        except UnicodeEncodeError:
            print(f"[EMAIL ERROR] Could not send email to {recipient}: <Contains Georgian characters>")
        return False

def add_notification(user_id, content):
    notification = Notification(user_id=user_id, content=content)
    db.session.add(notification)
    db.session.commit()

# --- Auth Routes ---

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('feed'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        role = request.form.get('role')
        school = request.form.get('school')
        city = request.form.get('city')
        phone = request.form.get('phone')
        
        # Validation
        if User.query.filter_by(username=username).first():
            flash('ეს მომხმარებლის სახელი უკვე დაკავებულია.', 'danger')
            return redirect(url_for('register'))
            
        if User.query.filter_by(email=email).first():
            flash('ეს ელ-ფოსტა უკვე რეგისტრირებულია.', 'danger')
            return redirect(url_for('register'))
            
        verification_code = str(random.randint(100000, 999999))
        
        # Store in session (do not insert into database yet)
        session['reg_data'] = {
            'username': username,
            'email': email,
            'password': password,
            'role': role,
            'school': school if role in ['teacher', 'student'] else None,
            'city': city if role in ['teacher', 'student'] else None,
            'phone': phone if role == 'teacher' else None
        }
        session['reg_code'] = verification_code
        
        # Send verification email
        email_body = f"""
        <div style="font-family: 'Helvetica Neue', Arial, sans-serif; padding: 20px; border-radius: 10px; background: #f4f6f9;">
            <h2 style="color: #1e3a8a;">მოგესალმებით choloka.ge-ზე!</h2>
            <p>გმადლობთ რეგისტრაციისთვის. გთხოვთ გამოიყენოთ ქვემოთ მოცემული ვერიფიკაციის კოდი თქვენი ელ-ფოსტის დასადასტურებლად და რეგისტრაციის დასასრულებლად:</p>
            <div style="font-size: 24px; font-weight: bold; background: #e0e7ff; color: #1e3a8a; padding: 10px 20px; display: inline-block; border-radius: 5px; margin: 15px 0;">
                {verification_code}
            </div>
            <p>თუ თქვენ არ დაგირეგისტრირებიათ ანგარიში, უბრალოდ დააიგნორეთ ეს წერილი.</p>
        </div>
        """
        send_email("ელ-ფოსტის ვერიფიკაცია - choloka.ge", email, email_body)
        
        flash('გთხოვთ შეიყვანოთ თქვენს მეილზე გამოგზავნილი 6-ნიშნა ვერიფიკაციის კოდი რეგისტრაციის დასასრულებლად.', 'info')
        return redirect(url_for('verify'))
        
    return render_template('register.html')

@app.route('/verify', methods=['GET', 'POST'])
def verify():
    reg_data = session.get('reg_data')
    reg_code = session.get('reg_code')
    if not reg_data or not reg_code:
        flash('სესიის ვადა ამოიწურა. გთხოვთ დარეგისტრირდეთ თავიდან.', 'warning')
        return redirect(url_for('register'))
        
    if request.method == 'POST':
        code = request.form.get('code')
        if reg_code == code:
            # Create user in DB
            hashed_password = generate_password_hash(reg_data['password'], method='scrypt')
            new_user = User(
                username=reg_data['username'],
                email=reg_data['email'],
                password_hash=hashed_password,
                role=reg_data['role'],
                school=reg_data.get('school'),
                city=reg_data.get('city'),
                phone=reg_data.get('phone'),
                is_verified=True
            )
            db.session.add(new_user)
            db.session.commit()
            
            # Clear session
            session.pop('reg_data', None)
            session.pop('reg_code', None)
            
            flash('რეგისტრაცია წარმატებით დასრულდა! შეგიძლიათ გაიაროთ ავტორიზაცია.', 'success')
            return redirect(url_for('login'))
        else:
            flash('არასწორი კოდი. გთხოვთ სცადოთ თავიდან.', 'danger')
            
    return render_template('verify.html', user_email=reg_data['email'], dev_code=reg_code)

@app.route('/resend_code')
def resend_code():
    reg_data = session.get('reg_data')
    if not reg_data:
        return redirect(url_for('register'))
        
    verification_code = str(random.randint(100000, 999999))
    session['reg_code'] = verification_code
    
    email_body = f"""
    <div style="font-family: 'Helvetica Neue', Arial, sans-serif; padding: 20px; background: #f4f6f9; border-radius: 10px;">
        <h2 style="color: #1e3a8a;">ვერიფიკაციის ახალი კოდი</h2>
        <div style="font-size: 24px; font-weight: bold; background: #e0e7ff; color: #1e3a8a; padding: 10px 20px; display: inline-block; border-radius: 5px; margin: 15px 0;">
            {verification_code}
        </div>
    </div>
    """
    send_email("ახალი ვერიფიკაციის კოდი - choloka.ge", reg_data['email'], email_body)
    flash('ახალი კოდი გამოიგზავნა თქვენს ელ-ფოსტაზე.', 'info')
    return redirect(url_for('verify'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('feed'))
        
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        user = User.query.filter_by(email=email).first()
        
        if not user or not check_password_hash(user.password_hash, password):
            flash('ელ-ფოსტა ან პაროლი არასწორია.', 'danger')
            return redirect(url_for('login'))
            
        if user.is_blocked:
            flash('თქვენი ანგარიში დაიბლოკა ადმინისტრატორის მიერ.', 'danger')
            return redirect(url_for('login'))
            
        if not user.is_verified:
            flash('ავტორიზაციამდე საჭიროა ელ-ფოსტის დადასტურება. გთხოვთ დარეგისტრირდეთ თავიდან.', 'warning')
            return redirect(url_for('register'))
            
        login_user(user)
        
        # Log login history
        login_time = datetime.utcnow()
        history = LoginHistory(user_id=user.id, login_time=login_time)
        db.session.add(history)
        db.session.commit()
        
        # Send login notification email only if user has it enabled
        if user.login_email_notify:
            time_str = login_time.strftime('%Y-%m-%d %H:%M:%S UTC')
            email_body = f"""
            <div style="font-family: Arial, sans-serif; padding: 20px; border: 1px solid #e2e8f0; border-radius: 8px;">
                <h3 style="color: #1e3a8a;">Security Notification - choloka.ge</h3>
                <p>Hello {user.username},</p>
                <p>A new login was detected on your account:</p>
                <p><strong>Time:</strong> {time_str}</p>
                <p>If this was not you, please reset your password immediately.</p>
            </div>
            """
            send_email("New Login Detected - choloka.ge", user.email, email_body)
        
        flash('წარმატებული ავტორიზაცია!', 'success')
        return redirect(url_for('feed'))
        
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('თქვენ გამოხვედით სისტემიდან.', 'info')
    return redirect(url_for('login'))

@app.route('/recover_password', methods=['GET', 'POST'])
def recover_password():
    if request.method == 'POST':
        email = request.form.get('email')
        user = User.query.filter_by(email=email).first()
        if user:
            # Simple recovery: Send code and store recovery code in session
            recovery_code = str(random.randint(100000, 999999))
            session['recovery_email'] = email
            session['recovery_code'] = recovery_code
            
            email_body = f"""
            <div style="font-family: Arial, sans-serif; padding: 20px; background: #fffbeb; border-radius: 8px;">
                <h3 style="color: #d97706;">პაროლის აღდგენა - choloka.ge</h3>
                <p>თქვენი პაროლის აღდგენის კოდია:</p>
                <div style="font-size: 24px; font-weight: bold; color: #b45309; margin: 15px 0;">{recovery_code}</div>
            </div>
            """
            send_email("პაროლის აღდგენა - choloka.ge", email, email_body)
            flash('პაროლის აღდგენის კოდი გამოიგზავნა მეილზე.', 'info')
            return redirect(url_for('reset_password'))
        else:
            flash('მომხმარებელი ამ ელ-ფოსტით ვერ მოიძებნა.', 'danger')
    return render_template('recover.html')

@app.route('/reset_password', methods=['GET', 'POST'])
def reset_password():
    email = session.get('recovery_email')
    correct_code = session.get('recovery_code')
    
    if not email or not correct_code:
        return redirect(url_for('recover_password'))
        
    if request.method == 'POST':
        code = request.form.get('code')
        new_password = request.form.get('password')
        
        if code == correct_code:
            user = User.query.filter_by(email=email).first()
            if user:
                user.password_hash = generate_password_hash(new_password, method='scrypt')
                db.session.commit()
                session.pop('recovery_email', None)
                session.pop('recovery_code', None)
                flash('პაროლი წარმატებით შეიცვალა. გაიარეთ ავტორიზაცია.', 'success')
                return redirect(url_for('login'))
        else:
            flash('არასწორი კოდი. გთხოვთ სცადოთ თავიდან.', 'danger')
            
    return render_template('reset.html')

# --- Feed / Posts Routes ---

@app.route('/')
@app.route('/feed')
@login_required
def feed():
    # Only show approved posts, sorted by created_at desc
    posts = Post.query.filter_by(status='approved').order_by(Post.created_at.desc()).all()
    # Get active ads
    now = datetime.utcnow()
    active_ads = Ad.query.filter(Ad.is_active == True, Ad.end_time > now).all()
    # If admin, show counts of pending posts
    pending_count = Post.query.filter_by(status='pending').count() if current_user.is_admin else 0
    return render_template('feed.html', posts=posts, pending_count=pending_count, active_ads=active_ads)

@app.route('/submit_post', methods=['POST'])
@login_required
def submit_post():
    title = request.form.get('title')
    content = request.form.get('content')
    media_url = request.form.get('media_url')
    
    # Auto-approve if user is admin, else pending
    status = 'approved' if current_user.is_admin else 'pending'
    
    new_post = Post(
        user_id=current_user.id,
        title=title,
        content=content,
        media_url=media_url,
        status=status
    )
    
    db.session.add(new_post)
    db.session.commit()
    
    # Handle multiple image uploads
    uploaded_files = request.files.getlist('post_images')
    for file in uploaded_files:
        if file and file.filename != '':
            if allowed_file(file.filename, {'png', 'jpg', 'jpeg', 'gif'}):
                filename = f"post_{new_post.id}_{random.randint(1000, 9999)}_{secure_filename(file.filename)}"
                save_path = os.path.join(app.config['UPLOAD_FOLDER'], 'posts', filename)
                file.save(save_path)
                
                media = PostMedia(post_id=new_post.id, file_path=filename)
                db.session.add(media)
    
    db.session.commit()
    
    if status == 'approved':
        flash('პოსტი წარმატებით გამოქვეყნდა!', 'success')
    else:
        # Notify admins
        admins = User.query.filter_by(is_admin=True).all()
        for admin in admins:
            add_notification(admin.id, f"მომხმარებელმა {current_user.username} გამოაგზავნა ახალი პოსტი დასადასტურებლად.")
        flash('პოსტი გაიგზავნა დასადასტურებლად. იგი გამოჩნდება ადმინისტრატორის მიერ განხილვის შემდეგ.', 'info')
        
    return redirect(url_for('feed'))

@app.route('/post/<int:post_id>/delete', methods=['POST'])
@login_required
def delete_post(post_id):
    post = Post.query.get_or_404(post_id)
    # Check if the current user is admin OR the author of the post
    if not (current_user.is_admin or post.user_id == current_user.id):
        flash('ამ პოსტის წაშლის უფლება არ გაქვთ.', 'danger')
        return redirect(url_for('feed'))
        
    author_id = post.user_id
    post_title = post.title
    
    # Delete media files from disk
    for m in post.media:
        try:
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], 'posts', m.file_path)
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception as e:
            print(f"Error deleting media file: {e}")
            
    db.session.delete(post)
    db.session.commit()
    
    # Notify writer if deleted by admin (not themselves)
    if current_user.id != author_id:
        add_notification(author_id, f"თქვენი პოსტი '{post_title}' წაიშალა ადმინისტრატორის მიერ.")
        
    flash('პოსტი წარმატებით წაიშალა!', 'success')
    
    referrer = request.referrer
    if referrer and any(path in referrer for path in ['/feed', '/user/', '/admin']):
        return redirect(referrer)
    return redirect(url_for('feed'))

@app.route('/post/<int:post_id>/like', methods=['POST'])
@login_required
def like_post(post_id):
    post = Post.query.get_or_404(post_id)
    like = PostLike.query.filter_by(post_id=post_id, user_id=current_user.id).first()
    
    if like:
        db.session.delete(like)
        db.session.commit()
        liked = False
    else:
        new_like = PostLike(post_id=post_id, user_id=current_user.id)
        db.session.add(new_like)
        db.session.commit()
        liked = True
        
        # Send notification to post author
        if post.user_id != current_user.id:
            add_notification(post.user_id, f"მომხმარებელმა {current_user.username} მოიწონა თქვენი პოსტი.")
            
    likes_count = PostLike.query.filter_by(post_id=post_id).count()
    return jsonify({
        'liked': liked,
        'likes_count': likes_count
    })

@app.route('/post/<int:post_id>/comment', methods=['POST'])
@login_required
def comment_post(post_id):
    post = Post.query.get_or_404(post_id)
    content = request.form.get('content', '').strip()
    
    if not content:
        flash('კომენტარი არ შეიძლება იყოს ცარიელი.', 'warning')
        return redirect(request.referrer or url_for('feed'))
        
    comment = PostComment(post_id=post_id, user_id=current_user.id, content=content)
    db.session.add(comment)
    db.session.commit()
    
    # Send notification to post author
    if post.user_id != current_user.id:
        add_notification(post.user_id, f"მომხმარებელმა {current_user.username} დააკომენტარა თქვენს პოსტზე.")
        
    flash('კომენტარი წარმატებით დაემატა.', 'success')
    return redirect(request.referrer or url_for('feed'))

@app.route('/comment/<int:comment_id>/delete', methods=['POST'])
@login_required
def delete_comment(comment_id):
    comment = PostComment.query.get_or_404(comment_id)
    post = comment.post
    
    # Allowed: comment author, post author, or admin
    if not (current_user.is_admin or comment.user_id == current_user.id or post.user_id == current_user.id):
        flash('კომენტარის წაშლის უფლება არ გაქვთ.', 'danger')
        return redirect(request.referrer or url_for('feed'))
        
    db.session.delete(comment)
    db.session.commit()
    
    flash('კომენტარი წარმატებით წაიშალა.', 'success')
    return redirect(request.referrer or url_for('feed'))

@app.route('/comment/<int:comment_id>/pin', methods=['POST'])
@login_required
def pin_comment(comment_id):
    comment = PostComment.query.get_or_404(comment_id)
    post = comment.post
    
    # Allowed: post author or admin
    if not (current_user.is_admin or post.user_id == current_user.id):
        flash('კომენტარის აპინვის უფლება არ გაქვთ.', 'danger')
        return redirect(request.referrer or url_for('feed'))
        
    if not comment.is_pinned:
        # Unpin any currently pinned comments for this post
        PostComment.query.filter_by(post_id=post.id, is_pinned=True).update({'is_pinned': False})
        comment.is_pinned = True
        flash('კომენტარი აიპინა.', 'success')
    else:
        comment.is_pinned = False
        flash('კომენტარის აპინვა გაუქმდა.', 'success')
        
    db.session.commit()
    return redirect(request.referrer or url_for('feed'))

@app.route('/post/<int:post_id>/share', methods=['POST'])
@login_required
def share_post(post_id):
    post = Post.query.get_or_404(post_id)
    share_comment = request.form.get('share_comment', '').strip()
    
    # Create shared post
    shared = Post(
        user_id=current_user.id,
        title="გაზიარებული პოსტი",
        content=share_comment,
        is_shared=True,
        original_post_id=post.id,
        status='approved'  # Shares of approved posts are approved
    )
    db.session.add(shared)
    db.session.commit()
    
    # Notify original post author
    if post.user_id != current_user.id:
        add_notification(post.user_id, f"მომხმარებელმა {current_user.username} გააზიარა თქვენი პოსტი.")
        
    flash('პოსტი გაზიარდა თქვენს პროფილზე!', 'success')
    return redirect(request.referrer or url_for('feed'))

# --- Messenger Routes ---

@app.route('/messages', methods=['GET'])
@login_required
def messages_list():
    search_query = request.args.get('search_name', '').strip()
    search_school = request.args.get('search_school', '').strip()
    
    users = []
    
    if search_school:
        # If school filter is used, return both teachers and students of that school
        users = User.query.filter(
            User.id != current_user.id,
            User.school.ilike(f'%{search_school}%'),
            User.is_blocked == False
        ).all()
    elif search_query:
        # Filter by name/username
        users = User.query.filter(
            User.id != current_user.id,
            User.username.ilike(f'%{search_query}%'),
            User.is_blocked == False
        ).all()
    else:
        # Get users who have conversed with the current user
        sent = db.session.query(DirectMessage.recipient_id).filter_by(sender_id=current_user.id).distinct().all()
        received = db.session.query(DirectMessage.sender_id).filter_by(recipient_id=current_user.id).distinct().all()
        user_ids = list(set([u[0] for u in sent] + [u[0] for u in received]))
        users = User.query.filter(User.id.in_(user_ids), User.is_blocked == False).all() if user_ids else []
        
    return render_template('messages.html', users=users, search_query=search_query, search_school=search_school)

@app.route('/messages/<int:recipient_id>', methods=['GET', 'POST'])
@login_required
def get_chat(recipient_id):
    recipient = User.query.get(recipient_id)
    if not recipient or recipient.is_blocked:
        return jsonify({'error': 'მომხმარებელი ვერ მოიძებნა ან დაბლოკილია.'}), 404
        
    if request.method == 'POST':
        content = request.form.get('content')
        file_url = None
        file_name = None
        is_image = False
        
        chat_file = request.files.get('chat_file')
        if chat_file and chat_file.filename != '':
            # Get file size
            chat_file.seek(0, os.SEEK_END)
            file_length = chat_file.tell()
            chat_file.seek(0)
            
            if file_length > 2 * 1024 * 1024:
                return jsonify({'error': 'ფაილის ზომა აღემატება 2MB-ს.'}), 400
                
            if allowed_file(chat_file.filename, {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'doc', 'docx', 'xls', 'xlsx', 'txt', 'zip', 'rar'}):
                filename = f"chat_{current_user.id}_{random.randint(1000, 9999)}_{secure_filename(chat_file.filename)}"
                save_path = os.path.join(app.config['UPLOAD_FOLDER'], 'chat', filename)
                chat_file.save(save_path)
                
                file_url = filename
                file_name = chat_file.filename
                is_image = chat_file.filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg', 'gif'}
            else:
                return jsonify({'error': 'ეს ფაილის ტიპი არ არის მხარდაჭერილი.'}), 400
                
        if content or file_url:
            msg = DirectMessage(
                sender_id=current_user.id,
                recipient_id=recipient_id,
                content=content,
                file_url=file_url,
                file_name=file_name,
                is_image=is_image
            )
            db.session.add(msg)
            db.session.commit()
            
            # Send notification
            add_notification(recipient_id, f"ახალი შეტყობინება {current_user.username}-სგან.")
            
            if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest' or 'chat_file' in request.files:
                return jsonify({
                    'id': msg.id,
                    'sender_id': msg.sender_id,
                    'content': msg.content,
                    'file_url': msg.file_url,
                    'file_name': msg.file_name,
                    'is_image': msg.is_image,
                    'created_at': msg.created_at.strftime('%H:%M')
                })
                
    # Mark incoming messages as read
    DirectMessage.query.filter_by(
        sender_id=recipient_id,
        recipient_id=current_user.id,
        is_read=False
    ).update({DirectMessage.is_read: True})
    db.session.commit()
    
    messages = DirectMessage.query.filter(
        ((DirectMessage.sender_id == current_user.id) & (DirectMessage.recipient_id == recipient_id)) |
        ((DirectMessage.sender_id == recipient_id) & (DirectMessage.recipient_id == current_user.id))
    ).order_by(DirectMessage.created_at.asc()).all()
    
    if request.is_json or request.headers.get('Accept') == 'application/json':
        return jsonify([{
            'id': m.id,
            'sender_id': m.sender_id,
            'content': m.content,
            'file_url': m.file_url,
            'file_name': m.file_name,
            'is_image': m.is_image,
            'created_at': m.created_at.strftime('%H:%M')
        } for m in messages])
        
    return render_template('messages.html', recipient=recipient, chat_messages=messages)

# --- Admin Chat (Direct Chat with Admin) ---

@app.route('/admin-chat', methods=['GET', 'POST'])
@login_required
def admin_chat():
    if request.method == 'POST':
        content = request.form.get('content')
        sender_role = 'admin' if current_user.is_admin else 'user'
        user_id = request.form.get('user_id', current_user.id) if current_user.is_admin else current_user.id
        
        chat_msg = AdminChat(
            user_id=user_id,
            sender_role=sender_role,
            content=content
        )
        db.session.add(chat_msg)
        db.session.commit()
        
        # Send notifications
        if current_user.is_admin:
            add_notification(user_id, "ადმინისტრატორმა გიპასუხათ ჩატში.")
        else:
            admins = User.query.filter_by(is_admin=True).all()
            for admin in admins:
                add_notification(admin.id, f"მომხმარებელმა {current_user.username} მოგწერათ ადმინ-ჩატში.")
                
        return redirect(url_for('admin_chat', user_id=user_id if current_user.is_admin else None))
        
    if current_user.is_admin:
        active_user_id = request.args.get('user_id')
        chat_users = db.session.query(User).join(AdminChat).distinct().all()
        
        chat_messages = []
        selected_user = None
        if active_user_id:
            selected_user = User.query.get(active_user_id)
            chat_messages = AdminChat.query.filter_by(user_id=active_user_id).order_by(AdminChat.created_at.asc()).all()
        return render_template('admin_chat.html', chat_users=chat_users, chat_messages=chat_messages, selected_user=selected_user)
    else:
        chat_messages = AdminChat.query.filter_by(user_id=current_user.id).order_by(AdminChat.created_at.asc()).all()
        return render_template('admin_chat.html', chat_messages=chat_messages)

# --- Profiles & Settings ---

def allowed_file(filename, allowed_extensions):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        # Admin Promotion check
        admin_code = request.form.get('admin_code')
        if admin_code == 'choloka123':
            current_user.is_admin = True
            db.session.commit()
            
            # Send automated email notification to the user about promotion
            email_body = f"""
            <div style="font-family: Arial, sans-serif; padding: 20px; border: 1px solid #10b981; border-radius: 8px;">
                <h3 style="color: #10b981;">სტატუსის განახლება - choloka.ge</h3>
                <p>გაცნობებთ, რომ თქვენ წარმატებით მიიღეთ <strong>ადმინისტრატორის (დეველოპერის) სტატუსი</strong> საიდუმლო კოდის გამოყენებით.</p>
            </div>
            """
            send_email("ადმინისტრატორის სტატუსის მინიჭება - choloka.ge", current_user.email, email_body)
            
            # Notify all other admins
            other_admins = User.query.filter(User.is_admin == True, User.id != current_user.id).all()
            for admin in other_admins:
                add_notification(admin.id, f"მომხმარებელი {current_user.username} გახდა ადმინისტრატორი საიდუმლო კოდით.")
                admin_email_body = f"""
                <div style="font-family: Arial, sans-serif; padding: 20px;">
                    <h3>სისტემური შეტყობინება - choloka.ge</h3>
                    <p>მომხმარებელი <strong>{current_user.username}</strong> დაინიშნა <strong>ადმინისტრატორად</strong> კოდის გამოყენებით.</p>
                </div>
                """
                send_email("ახალი ადმინისტრატორის დანიშვნა - choloka.ge", admin.email, admin_email_body)
                
            flash('თქვენ წარმატებით მიიღეთ ადმინისტრატორის სტატუსი! მეილი გამოგზავნილია.', 'success')
            return redirect(url_for('profile'))
            
        # Handle login email notification toggle
        login_email_notify = request.form.get('login_email_notify') == '1'
        current_user.login_email_notify = login_email_notify
        
        bio = request.form.get('bio')
        school = request.form.get('school')
        city = request.form.get('city')
        phone = request.form.get('phone')
        
        # Handle profile pic upload
        profile_file = request.files.get('profile_pic')
        if profile_file and profile_file.filename != '':
            if allowed_file(profile_file.filename, {'png', 'jpg', 'jpeg', 'gif'}):
                filename = f"user_{current_user.id}_{secure_filename(profile_file.filename)}"
                save_path = os.path.join(app.config['UPLOAD_FOLDER'], 'profiles', filename)
                profile_file.save(save_path)
                current_user.profile_pic = filename
            else:
                flash('არასწორი ფაილის ტიპი პროფილის სურათისთვის. ნებადართულია: png, jpg, jpeg, gif', 'danger')
                
        # Handle CV/PDF upload
        cv_file = request.files.get('cv_file')
        if cv_file and cv_file.filename != '':
            if allowed_file(cv_file.filename, {'pdf'}):
                filename = f"cv_{current_user.id}_{secure_filename(cv_file.filename)}"
                save_path = os.path.join(app.config['UPLOAD_FOLDER'], 'pdfs', filename)
                cv_file.save(save_path)
                current_user.cv_url = filename
            else:
                flash('მხოლოდ PDF ფაილებია ნებადართული CV-სთვის.', 'danger')
        
        current_user.bio = bio
        if current_user.role in ['teacher', 'student']:
            current_user.school = school
            current_user.city = city
        if current_user.role == 'teacher':
            current_user.phone = phone
            
        db.session.commit()
        flash('პროფილი წარმატებით განახლდა.', 'success')
        return redirect(url_for('profile'))
        
    return render_template('profile.html')

@app.route('/user/<int:user_id>')
@login_required
def user_profile(user_id):
    user = User.query.get_or_404(user_id)
    # Get approved posts for this user
    user_posts = Post.query.filter_by(user_id=user.id, status='approved').order_by(Post.created_at.desc()).all()
    
    # Notify profile owner if visited by someone else
    if current_user.id != user.id:
        visit_time = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
        email_body = f"""
        <div style="font-family: Arial, sans-serif; padding: 20px; border: 1px solid #e2e8f0; border-radius: 8px;">
            <h3 style="color: #3b82f6;">პროფილის ნახვის შეტყობინება - choloka.ge</h3>
            <p>გაცნობებთ, რომ მომხმარებელი <strong>{current_user.username}</strong> ესტუმრა თქვენს პროფილის გვერდს.</p>
            <p><strong>დრო:</strong> {visit_time}</p>
        </div>
        """
        send_email("ახალი ვიზიტი თქვენს პროფილზე - choloka.ge", user.email, email_body)
        
    return render_template('public_profile.html', user=user, posts=user_posts)

# --- Courses and Registrations ---

@app.route('/courses')
@login_required
def courses():
    all_courses = Course.query.all()
    return render_template('courses.html', courses=all_courses)

@app.route('/courses/<int:course_id>/register', methods=['GET', 'POST'])
@login_required
def course_register(course_id):
    course = Course.query.get_or_404(course_id)
    fields = json.loads(course.form_template)
    
    if request.method == 'POST':
        responses = {}
        for field in fields:
            field_name = field['name']
            val = request.form.get(field_name)
            responses[field_name] = val
            
        registration = CourseRegistration(
            course_id=course_id,
            user_id=current_user.id,
            registration_data=json.dumps(responses)
        )
        db.session.add(registration)
        db.session.commit()
        
        flash(f'თქვენ წარმატებით დარეგისტრირდით კურსზე: {course.title}!', 'success')
        return redirect(url_for('courses'))
        
    return render_template('course_register.html', course=course, fields=fields)

# --- Polls & Notifications ---

@app.route('/polls', methods=['GET'])
@login_required
def polls():
    today_str = date.today().strftime('%Y-%m-%d')
    active_polls = Poll.query.filter_by(date_scheduled=today_str).all()
    
    for poll in active_polls:
        poll.choices = json.loads(poll.options)
        vote = PollVote.query.filter_by(poll_id=poll.id, user_id=current_user.id).first()
        poll.user_vote = vote.selected_option if vote else None
        
        all_votes = PollVote.query.filter_by(poll_id=poll.id).all()
        vote_counts = {c: 0 for c in poll.choices}
        for v in all_votes:
            if v.selected_option in vote_counts:
                vote_counts[v.selected_option] += 1
                
        total = len(all_votes)
        poll.results = {
            c: {
                'count': count,
                'pct': int((count / total) * 100) if total > 0 else 0
            } for c, count in vote_counts.items()
        }
        
    scheduled_polls = Poll.query.all()
    events = []
    for p in scheduled_polls:
        events.append({
            'title': p.question,
            'start': p.date_scheduled,
            'allDay': True
        })
        
    return render_template('polls.html', active_polls=active_polls, events=json.dumps(events))

@app.route('/polls/<int:poll_id>/vote', methods=['POST'])
@login_required
def vote_poll(poll_id):
    poll = Poll.query.get_or_404(poll_id)
    choice = request.form.get('choice')
    
    existing_vote = PollVote.query.filter_by(poll_id=poll_id, user_id=current_user.id).first()
    if existing_vote:
        flash('თქვენ უკვე მიეცით ხმა ამ გამოკითხვას.', 'warning')
    elif choice:
        vote = PollVote(poll_id=poll_id, user_id=current_user.id, selected_option=choice)
        db.session.add(vote)
        db.session.commit()
        flash('თქვენი ხმა მიღებულია!', 'success')
        
    return redirect(url_for('polls'))

@app.route('/api/notifications')
@login_required
def get_notifications():
    notifs = Notification.query.filter_by(user_id=current_user.id, is_read=False).order_by(Notification.created_at.desc()).all()
    data = [{'id': n.id, 'content': n.content, 'created_at': n.created_at.strftime('%Y-%m-%d %H:%M')} for n in notifs]
    return jsonify(data)

@app.route('/api/notifications/read', methods=['POST'])
@login_required
def mark_notifications_read():
    Notification.query.filter_by(user_id=current_user.id, is_read=False).update({Notification.is_read: True})
    db.session.commit()
    return jsonify({'success': True})

# --- Admin Panel Routes ---

@app.route('/admin', strict_slashes=False)
@login_required
def admin_panel():
    if not current_user.is_admin:
        flash('ამ გვერდზე შესვლა შეუძლიათ მხოლოდ ადმინისტრატორებს.', 'danger')
        return redirect(url_for('feed'))
        
    # Filters & Search for Users
    search_name = request.args.get('search_name', '').strip()
    filter_role = request.args.get('role', '').strip()
    filter_city = request.args.get('city', '').strip()
    filter_school = request.args.get('school', '').strip()
    filter_admin = request.args.get('is_admin', '').strip()
    
    query = User.query
    
    if search_name:
        query = query.filter(User.username.ilike(f'%{search_name}%'))
    if filter_role:
        query = query.filter_by(role=filter_role)
    if filter_city:
        query = query.filter(User.city.ilike(f'%{filter_city}%'))
    if filter_school:
        query = query.filter(User.school.ilike(f'%{filter_school}%'))
    if filter_admin:
        is_adm = True if filter_admin == '1' else False
        query = query.filter_by(is_admin=is_adm)
        
    users = query.all()
    
    # Pending posts
    pending_posts = Post.query.filter_by(status='pending').order_by(Post.created_at.desc()).all()
    
    # Courses list
    courses_list = Course.query.all()
    
    # Load all poll events for admin calendar
    polls_list = Poll.query.all()
    
    # Ads and Badge requests lists
    ads_list = Ad.query.order_by(Ad.created_at.desc()).all()
    badge_requests = BadgeRequest.query.order_by(BadgeRequest.created_at.desc()).all()
    
    return render_template(
        'admin.html',
        users=users,
        pending_posts=pending_posts,
        courses=courses_list,
        polls=polls_list,
        ads=ads_list,
        badge_requests=badge_requests
    )

@app.route('/admin/user/<int:user_id>/delete', methods=['POST'])
@login_required
def admin_delete_user(user_id):
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403
        
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash("საკუთარი ანგარიშის წაშლა შეუძლებელია.", "danger")
        return redirect(url_for('admin_panel'))
        
    reason = request.form.get('reason', 'მიზეზი არ არის მითითებული.')
    
    # Send email
    subject = "თქვენი ანგარიში წაიშალა - choloka.ge"
    body = f"""
    <div style="font-family: sans-serif; padding: 20px;">
        <h2 style="color: #e11d48;">ანგარიშის წაშლა</h2>
        <p>გამარჯობა {user.username},</p>
        <p>თქვენი ანგარიში choloka.ge-ზე წაშლილია ადმინისტრატორის მიერ.</p>
        <div style="background: #f8fafc; padding: 15px; border-left: 4px solid #e11d48; margin: 20px 0;">
            <strong>წაშლის მიზეზი:</strong><br>
            {reason}
        </div>
        <p>თუ ფიქრობთ, რომ მოხდა შეცდომა, გთხოვთ დაგვიკავშირდეთ.</p>
    </div>
    """
    send_email(subject, user.email, body)
    
    # Manually delete related entities
    PostLike.query.filter_by(user_id=user.id).delete()
    PostComment.query.filter_by(user_id=user.id).delete()
    CourseRegistration.query.filter_by(user_id=user.id).delete()
    PollVote.query.filter_by(user_id=user.id).delete()
    Notification.query.filter_by(user_id=user.id).delete()
    LoginHistory.query.filter_by(user_id=user.id).delete()
    BadgeRequest.query.filter_by(user_id=user.id).delete()
    
    for post in Post.query.filter_by(user_id=user.id).all():
        db.session.delete(post)
        
    db.session.delete(user)
    db.session.commit()
    
    flash(f"მომხმარებელი {user.username} წარმატებით წაიშალა.", "success")
    return redirect(url_for('admin_panel'))

@app.route('/admin/user/<int:user_id>/action/<string:action_type>', methods=['POST'])
@login_required
def admin_user_action(user_id, action_type):
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403
        
    user = User.query.get_or_404(user_id)
    email_body = ""
    subject = ""
    
    if action_type == 'toggle_admin':
        user.is_admin = not user.is_admin
        db.session.commit()
        
        if user.is_admin:
            subject = "ადმინისტრატორის სტატუსი - choloka.ge"
            email_body = f"<h2>მოგესალმებით {user.username},</h2><p>გაცნობებთ, რომ ადმინისტრატორმა მოგანიჭათ <strong>ადმინისტრატორის სტატუსი</strong> ვებგვერდზე choloka.ge.</p>"
            add_notification(user.id, "ადმინისტრატორმა მოგცათ ადმინის სტატუსი.")
            
            # Notify all other admins
            other_admins = User.query.filter(User.is_admin == True, User.id != user.id, User.id != current_user.id).all()
            for admin in other_admins:
                add_notification(admin.id, f"მომხმარებელი {user.username} დაინიშნა ადმინისტრატორად.")
                admin_email_body = f"""
                <div style="font-family: Arial, sans-serif; padding: 20px;">
                    <h3>სისტემური შეტყობინება - choloka.ge</h3>
                    <p>მომხმარებელი <strong>{user.username}</strong> ({user.email}) დაინიშნა <strong>ადმინისტრატორად</strong> ადმინ პანელიდან.</p>
                </div>
                """
                send_email("ახალი ადმინისტრატორის დანიშვნა - choloka.ge", admin.email, admin_email_body)
        else:
            subject = "ადმინისტრატორის სტატუსი ჩამოგერთვათ - choloka.ge"
            email_body = f"<h2>მოგესალმებით {user.username},</h2><p>გაცნობებთ, რომ ჩამოგერთვათ <strong>ადმინისტრატორის სტატუსი</strong> ვებგვერდზე choloka.ge.</p>"
            add_notification(user.id, "ადმინისტრატორმა ჩამოგართვათ ადმინის სტატუსი.")
            
    elif action_type == 'toggle_block':
        user.is_blocked = not user.is_blocked
        db.session.commit()
        
        if user.is_blocked:
            subject = "თქვენი ანგარიში დაიბლოკა - choloka.ge"
            email_body = f"<h2>მოგესალმებით {user.username},</h2><p>სამწუხაროდ, თქვენი ანგარიში ვებგვერდზე choloka.ge <strong>დაიბლოკა</strong> ადმინისტრატორის მიერ.</p>"
        else:
            subject = "თქვენი ანგარიში განბლოკილია - choloka.ge"
            email_body = f"<h2>მოგესალმებით {user.username},</h2><p>თქვენი ანგარიში ვებგვერდზე choloka.ge წარმატებით <strong>განბლოკილია</strong> ადმინისტრატორის მიერ.</p>"
            
    # Send email notification
    if subject and email_body:
        send_email(subject, user.email, f"<div style='font-family: Arial, sans-serif; padding: 20px;'>{email_body}</div>")
        
    flash('მომხმარებლის სტატუსი წარმატებით განახლდა და გაეგზავნა შეტყობინება მეილზე.', 'success')
    return redirect(url_for('admin_panel'))

@app.route('/admin/post/<int:post_id>/approve', methods=['POST'])
@login_required
def admin_post_approve(post_id):
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403
        
    post = Post.query.get_or_404(post_id)
    post.status = 'approved'
    db.session.commit()
    
    # Notify writer
    add_notification(post.user_id, f"თქვენი პოსტი '{post.title}' წარმატებით დადასტურდა!")
    
    flash('პოსტი დადასტურდა და გამოჩნდა სიახლეებში!', 'success')
    return redirect(url_for('admin_panel'))

@app.route('/admin/post/<int:post_id>/delete', methods=['POST'])
@login_required
def admin_post_delete(post_id):
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403
        
    post = Post.query.get_or_404(post_id)
    author_id = post.user_id
    post_title = post.title
    db.session.delete(post)
    db.session.commit()
    
    # Notify writer
    add_notification(author_id, f"თქვენი პოსტი '{post_title}' წაიშალა ადმინისტრატორის მიერ.")
    
    flash('პოსტი წარმატებით წაიშალა!', 'success')
    return redirect(url_for('admin_panel'))

@app.route('/admin/course/add', methods=['POST'])
@login_required
def admin_course_add():
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403
        
    title = request.form.get('title')
    description = request.form.get('description')
    
    fields = []
    field_names = request.form.getlist('field_name[]')
    field_types = request.form.getlist('field_type[]')
    field_required = request.form.getlist('field_required[]')
    
    for i in range(len(field_names)):
        if field_names[i].strip():
            fields.append({
                'name': field_names[i].strip(),
                'type': field_types[i],
                'required': field_required[i] == '1'
            })
            
    if not fields:
        fields = [
            {'name': 'სახელი და გვარი', 'type': 'text', 'required': True},
            {'name': 'ტელეფონის ნომერი', 'type': 'text', 'required': True},
            {'name': 'ელ-ფოსტა', 'type': 'email', 'required': True}
        ]
        
    course = Course(
        title=title,
        description=description,
        form_template=json.dumps(fields)
    )
    db.session.add(course)
    db.session.commit()
    
    flash('კურსი წარმატებით დაემატა!', 'success')
    return redirect(url_for('admin_panel'))

@app.route('/admin/poll/add', methods=['POST'])
@login_required
def admin_poll_add():
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403
        
    question = request.form.get('question')
    options_list = request.form.getlist('options[]')
    date_scheduled = request.form.get('date_scheduled')
    
    choices = [c.strip() for c in options_list if c.strip()]
    if not choices:
        choices = ["დიახ", "არა"]
        
    poll = Poll(
        question=question,
        options=json.dumps(choices),
        date_scheduled=date_scheduled
    )
    db.session.add(poll)
    db.session.commit()
    
    users = User.query.filter_by(is_blocked=False).all()
    for user in users:
        add_notification(user.id, f"დაემატა ახალი გამოკითხვა თარიღისთვის: {date_scheduled} - {question}")
        
    flash('გამოკითხვა წარმატებით ჩაინიშნა კალენდარში!', 'success')
    return redirect(url_for('admin_panel'))

@app.route('/request_badge', methods=['GET', 'POST'])
@login_required
def request_badge():
    if request.method == 'POST':
        requested_badge = request.form.get('requested_badge')
        justification = request.form.get('justification')
        
        if not requested_badge or not justification:
            flash('გთხოვთ შეავსოთ ყველა ველი.', 'danger')
            return redirect(url_for('request_badge'))
            
        req = BadgeRequest(
            user_id=current_user.id,
            requested_badge=requested_badge,
            justification=justification
        )
        db.session.add(req)
        db.session.commit()
        
        # Notify admins
        admins = User.query.filter_by(is_admin=True).all()
        for admin in admins:
            add_notification(admin.id, f"ახალი იარლიყის მოთხოვნა მომხმარებლისგან {current_user.username}: {requested_badge}")
            
        flash('მოთხოვნა წარმატებით გაიგზავნა განხილვისთვის.', 'success')
        return redirect(url_for('profile'))
        
    return render_template('badge_request.html')

@app.route('/admin/ad/add', methods=['POST'])
@login_required
def admin_ad_add():
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403
        
    link_url = request.form.get('link_url')
    duration_days = int(request.form.get('duration_days', 1))
    
    ad_file = request.files.get('ad_file')
    if ad_file and ad_file.filename != '':
        if allowed_file(ad_file.filename, {'png', 'jpg', 'jpeg', 'gif'}):
            filename = f"ad_{random.randint(100000, 999999)}_{secure_filename(ad_file.filename)}"
            save_path = os.path.join(app.config['UPLOAD_FOLDER'], 'ads', filename)
            ad_file.save(save_path)
            
            end_time = datetime.utcnow() + timedelta(days=duration_days)
            
            ad = Ad(
                image_url=filename,
                link_url=link_url,
                end_time=end_time
            )
            db.session.add(ad)
            db.session.commit()
            flash('რეკლამა წარმატებით დაემატა!', 'success')
        else:
            flash('არასწორი ფაილის ტიპი რეკლამისთვის.', 'danger')
    else:
        flash('რეკლამის სურათის ატვირთვა სავალდებულოა.', 'danger')
        
    return redirect(url_for('admin_panel'))

@app.route('/admin/ad/delete/<int:ad_id>', methods=['POST'])
@login_required
def admin_ad_delete(ad_id):
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403
        
    ad = Ad.query.get_or_404(ad_id)
    db.session.delete(ad)
    db.session.commit()
    flash('რეკლამა წაიშალა.', 'success')
    return redirect(url_for('admin_panel'))

@app.route('/admin/badge_request/<int:request_id>/<string:action>', methods=['POST'])
@login_required
def admin_badge_action(request_id, action):
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403
        
    req = BadgeRequest.query.get_or_404(request_id)
    admin_explanation = request.form.get('admin_explanation', '').strip()
    
    if action == 'approve':
        req.status = 'approved'
        req.user.custom_badge = req.requested_badge
        flash_msg = f"მოთხოვნა იარლიყზე '{req.requested_badge}' დამტკიცდა."
    else:
        req.status = 'rejected'
        req.admin_explanation = admin_explanation
        flash_msg = f"მოთხოვნა იარლიყზე '{req.requested_badge}' უარყოფილ იქნა."
        
    req.admin_explanation = admin_explanation
    db.session.commit()
    
    # Notify user in-app
    add_notification(req.user_id, f"თქვენი მოთხოვნა იარლიყზე '{req.requested_badge}' {action == 'approve' and 'დამტკიცდა' or 'უარყოფილ იქნა'}.")
    
    # Send email to user
    status_ge = "დამტკიცდა" if action == 'approve' else "უარყოფილ იქნა"
    email_body = f"""
    <div style="font-family: Arial, sans-serif; padding: 20px; border: 1px solid #e2e8f0; border-radius: 8px;">
        <h3>მოთხოვნა იარლიყის მიწერაზე - choloka.ge</h3>
        <p>მოგესალმებით {req.user.username},</p>
        <p>თქვენი მოთხოვნა იარლიყზე <strong>"{req.requested_badge}"</strong> განხილულია და <strong>{status_ge}</strong>.</p>
        <p><strong>ადმინისტრატორის ახსნა-განმარტება:</strong> {admin_explanation or 'არ არის მითითებული'}</p>
    </div>
    """
    send_email(f"მოთხოვნა იარლიყზე განხილულია - choloka.ge", req.user.email, email_body)
    
    # Send automated message in support chat (AdminChat)
    chat_content = f"თქვენი მოთხოვნა იარლიყზე '{req.requested_badge}' {status_ge}.\nახსნა-განმარტება: {admin_explanation or 'არ არის მითითებული'}"
    admin_msg = AdminChat(
        user_id=req.user_id,
        sender_role='admin',
        content=chat_content
    )
    db.session.add(admin_msg)
    db.session.commit()
    
    flash(flash_msg, 'success')
    return redirect(url_for('admin_panel'))

# --- Follow & Message Routes ---

@app.route('/follow/<int:user_id>', methods=['POST'])
@login_required
def follow(user_id):
    user = User.query.get_or_404(user_id)
    if user == current_user:
        return jsonify({'error': 'საკუთარი თავის გამოწერა შეუძლებელია.'}), 400
    
    if not current_user.is_following(user):
        current_user.follow(user)
        add_notification(user.id, f'{current_user.username}-მა გამოგიწერათ.')
        db.session.commit()
        return jsonify({'status': 'success', 'followers_count': user.followers.count()})
    
    return jsonify({'error': 'უკვე გამოწერილი გყავთ.'}), 400

@app.route('/unfollow/<int:user_id>', methods=['POST'])
@login_required
def unfollow(user_id):
    user = User.query.get_or_404(user_id)
    if user == current_user:
        return jsonify({'error': 'საკუთარი თავის გამოწერა შეუძლებელია.'}), 400
        
    if current_user.is_following(user):
        current_user.unfollow(user)
        db.session.commit()
        return jsonify({'status': 'success', 'followers_count': user.followers.count()})
        
    return jsonify({'error': 'არ გყავთ გამოწერილი.'}), 400

@app.route('/message/<int:message_id>/delete', methods=['POST'])
@login_required
def delete_message(message_id):
    msg = DirectMessage.query.get_or_404(message_id)
    if msg.sender_id != current_user.id:
        return jsonify({'error': 'თქვენ არ გაქვთ ამ მესიჯის წაშლის უფლება.'}), 403
        
    msg.is_deleted = True
    msg.content = None
    if msg.file_url:
        import os
        file_path = os.path.join(app.root_path, 'static/uploads/chat', msg.file_url)
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass
        msg.file_url = None
        msg.file_name = None
        
    db.session.commit()
    return jsonify({'status': 'success'})

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(username='admin').first():
            admin_pwd = generate_password_hash('admin123', method='scrypt')
            default_admin = User(
                username='admin',
                email='admin@choloka.ge',
                password_hash=admin_pwd,
                role='other',
                is_verified=True,
                is_admin=True
            )
            db.session.add(default_admin)
            db.session.commit()
            print("Default admin created (username: admin, password: admin123)")
            
    app.run(debug=True, port=5000)

