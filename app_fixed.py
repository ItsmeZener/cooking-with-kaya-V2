import os
import re
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from functools import wraps
import click
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
import json
import random
import google.generativeai as genai

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'cooking-with-kaya-secret-key-2024')

# Database configuration - use PostgreSQL on Render, SQLite locally
database_url = os.environ.get('DATABASE_URL')
if database_url:
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
    }
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///cooking_with_kaya.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Database Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    skill_level = db.Column(db.String(20), default='beginner')
    dietary_preferences = db.Column(db.String(200))
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    recipes = db.relationship('Recipe', backref='author', lazy=True)
    posts = db.relationship('Post', backref='author', lazy=True)
    favorites = db.relationship('Favorite', backref='user', lazy=True)
    progress = db.relationship('Progress', backref='user', lazy=True)
    meal_plans = db.relationship('MealPlan', backref='user', lazy=True)

class Recipe(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    ingredients = db.Column(db.Text, nullable=False)
    instructions = db.Column(db.Text, nullable=False)
    cooking_time = db.Column(db.Integer)
    difficulty = db.Column(db.String(20))
    image_url = db.Column(db.String(500))
    video_url = db.Column(db.String(500))
    tags = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    user = db.relationship('User', foreign_keys=[user_id], backref='user_recipes')

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    image_url = db.Column(db.String(500))
    recipe_link = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    likes = db.Column(db.Integer, default=0)
    user = db.relationship('User', foreign_keys=[user_id], backref='user_posts')
    comments = db.relationship('Comment', backref='post', lazy='dynamic', cascade='all, delete-orphan')

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'))
    user = db.relationship('User', foreign_keys=[user_id], backref='user_comments')

class Favorite(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    recipe_id = db.Column(db.Integer, db.ForeignKey('recipe.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    recipe = db.relationship('Recipe', backref='favorites')

class Progress(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    skill_name = db.Column(db.String(100))
    level = db.Column(db.Integer, default=1)
    experience = db.Column(db.Integer, default=0)
    completed_recipes = db.Column(db.Integer, default=0)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)

class MealPlan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    day = db.Column(db.String(20))
    meal_type = db.Column(db.String(20))
    recipe_id = db.Column(db.Integer, db.ForeignKey('recipe.id'))
    week_start = db.Column(db.Date)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('Admin access required', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    featured_recipes = Recipe.query.order_by(Recipe.created_at.desc()).limit(6).all()
    recent_posts = Post.query.order_by(Post.created_at.desc()).limit(5).all()
    return render_template('index.html', recipes=featured_recipes, posts=recent_posts)

@app.route('/health')
def health_check():
    return jsonify({'status': 'healthy'}), 200

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        
        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'error')
            return redirect(url_for('register'))
        
        user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password),
            skill_level=request.form.get('skill_level', 'beginner')
        )
        db.session.add(user)
        db.session.commit()
        
        skills = ['Knife Skills', 'Sautéing', 'Baking', 'Grilling', 'Plating']
        for skill in skills:
            progress = Progress(user_id=user.id, skill_name=skill)
            db.session.add(progress)
        db.session.commit()
        
        flash('Registration successful!', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            if user.is_admin:
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('index'))
        
        flash('Invalid username or password', 'error')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/recipes')
def recipes():
    difficulty = request.args.get('difficulty')
    time = request.args.get('time')
    search = request.args.get('search')
    
    query = Recipe.query
    
    if difficulty:
        query = query.filter_by(difficulty=difficulty)
    if time:
        if time == 'quick':
            query = query.filter(Recipe.cooking_time <= 30)
        elif time == 'medium':
            query = query.filter(Recipe.cooking_time.between(31, 60))
        elif time == 'long':
            query = query.filter(Recipe.cooking_time > 60)
    if search:
        query = query.filter(Recipe.title.contains(search) | Recipe.ingredients.contains(search))
    
    recipes = query.order_by(Recipe.created_at.desc()).all()
    return render_template('recipes.html', recipes=recipes)

@app.route('/recipe/<int:recipe_id>')
def recipe_detail(recipe_id):
    recipe = Recipe.query.get_or_404(recipe_id)
    is_favorite = False
    if current_user.is_authenticated:
        is_favorite = Favorite.query.filter_by(user_id=current_user.id, recipe_id=recipe_id).first() is not None
    return render_template('recipe_detail.html', recipe=recipe, is_favorite=is_favorite)

@app.route('/add_recipe', methods=['GET', 'POST'])
@login_required
def add_recipe():
    if request.method == 'POST':
        image_url = ''
        if 'image_file' in request.files:
            file = request.files['image_file']
            if file and file.filename != '':
                if allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    filename = f"{timestamp}_{filename}"
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                    image_url = f'/static/uploads/{filename}'
        
        recipe = Recipe(
            title=request.form['title'],
            description=request.form['description'],
            ingredients=request.form['ingredients'],
            instructions=request.form['instructions'],
            cooking_time=int(request.form['cooking_time']),
            difficulty=request.form['difficulty'],
            tags=request.form.get('tags', ''),
            image_url=image_url,
            video_url=request.form.get('video_url', ''),
            user_id=current_user.id
        )
        db.session.add(recipe)
        db.session.commit()
        
        progress = Progress.query.filter_by(user_id=current_user.id).first()
        if progress:
            progress.completed_recipes += 1
            progress.experience += 50
            if progress.experience >= 100:
                progress.level += 1
                progress.experience = 0
            db.session.commit()
        
        flash('Recipe added successfully!', 'success')
        return redirect(url_for('recipes'))
    
    return render_template('add_recipe.html')

@app.route('/community')
def community():
    posts = Post.query.order_by(Post.created_at.desc()).all()
    return render_template('community.html', posts=posts)

@app.route('/add_post', methods=['POST'])
@login_required
def add_post():
    image_url = ''
    if 'image_file' in request.files:
        file = request.files['image_file']
        if file and file.filename != '':
            if allowed_file(file.filename):
                filename = secure_filename(file.filename)
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f"{timestamp}_{filename}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                image_url = f'/static/uploads/{filename}'
    
    post = Post(
        content=request.form['content'],
        image_url=image_url,
        recipe_link=request.form.get('recipe_link', ''),
        user_id=current_user.id
    )
    db.session.add(post)
    db.session.commit()
    flash('Post shared successfully!', 'success')
    return redirect(url_for('community'))

@app.route('/favorites')
@login_required
def favorites():
    user_favorites = Favorite.query.filter_by(user_id=current_user.id).all()
    recipes = [fav.recipe for fav in user_favorites]
    return render_template('favorites.html', recipes=recipes)

@app.route('/progress')
@login_required
def progress():
    user_progress = Progress.query.filter_by(user_id=current_user.id).all()
    total_recipes = sum(p.completed_recipes for p in user_progress)
    avg_level = sum(p.level for p in user_progress) / len(user_progress) if user_progress else 0
    return render_template('progress.html', progress=user_progress, total_recipes=total_recipes, avg_level=avg_level)

@app.route('/tutorials')
def tutorials():
    return render_template('tutorials.html')

@app.route('/ai-chef')
def ai_chef():
    return render_template('ai_chef.html')

@app.route('/meal-planner')
@login_required
def meal_planner():
    today = datetime.now().date()
    week_start = today - timedelta(days=today.weekday())
    meal_plans = MealPlan.query.filter_by(user_id=current_user.id, week_start=week_start).all()
    return render_template('meal_planner.html', meal_plans=meal_plans, week_start=week_start)

@app.route('/admin')
@login_required
@admin_required
def admin_dashboard():
    total_users = User.query.count()
    total_recipes = Recipe.query.count()
    total_posts = Post.query.count()
    recent_users = User.query.order_by(User.created_at.desc()).limit(5).all()
    recent_recipes = Recipe.query.order_by(Recipe.created_at.desc()).limit(5).all()
    return render_template('admin_dashboard.html', total_users=total_users, total_recipes=total_recipes, total_posts=total_posts, recent_users=recent_users, recent_recipes=recent_recipes)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        existing_admin = User.query.filter_by(username='admin').first()
        if not existing_admin:
            admin_user = User(
                username='admin',
                email='admin@cookingwithkaya.com',
                password_hash=generate_password_hash('admin123'),
                is_admin=True,
                skill_level='advanced'
            )
            db.session.add(admin_user)
            db.session.flush()
            skills = ['Knife Skills', 'Sautéing', 'Baking', 'Grilling', 'Plating']
            for skill in skills:
                progress = Progress(user_id=admin_user.id, skill_name=skill)
                db.session.add(progress)
            db.session.commit()
            print('Database initialized!')
    app.run(debug=True, host='0.0.0.0', port=5000)
