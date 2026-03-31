# Render deployment - FULL VERSION v2
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

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'cooking-with-kaya-secret-key-2024')

# Database configuration - use PostgreSQL on Render, SQLite locally
database_url = os.environ.get('DATABASE_URL')
if database_url:
    # Convert postgres:// to postgresql+psycopg:// for psycopg v3 compatibility
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql+psycopg://', 1)
    elif database_url.startswith('postgresql://'):
        database_url = database_url.replace('postgresql://', 'postgresql+psycopg://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
    }
else:
    # Local SQLite database
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///cooking_with_kaya.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

# Create upload directory if it doesn't exist
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
    password_hash = db.Column(db.String(256))
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
    
    # Relationships
    user = db.relationship('User', foreign_keys=[user_id], backref='user_recipes')

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    image_url = db.Column(db.String(500))
    recipe_link = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    likes = db.Column(db.Integer, default=0)
    
    # Relationships - use user instead of author to avoid conflict
    user = db.relationship('User', foreign_keys=[user_id], backref='user_posts')
    comments = db.relationship('Comment', backref='post', lazy='dynamic', cascade='all, delete-orphan')

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'))
    
    # Relationships - use explicit foreign_keys to avoid conflicts
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

# Admin decorator
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('Admin access required', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

# Routes
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
        
        # Initialize progress tracking
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
            # Redirect admin users to admin dashboard, regular users to index
            if user.is_admin:
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('index'))
        
        flash('Invalid username or password', 'error')
    
    return render_template('login.html')

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        username_or_email = request.form.get('username_or_email', '').strip()
        
        # Find user by username or email
        user = User.query.filter(
            (User.username == username_or_email) | (User.email == username_or_email)
        ).first()
        
        if user:
            # In a production app, you would send an email with a reset token
            # For this demo, we'll redirect to reset password page with user id
            flash('Instructions sent! Please check your email.', 'success')
            return redirect(url_for('reset_password', user_id=user.id))
        else:
            # Don't reveal if user exists for security
            flash('If an account exists with that information, reset instructions have been sent.', 'info')
            return redirect(url_for('login'))
    
    return render_template('forgot_password.html')

@app.route('/reset-password/<int:user_id>', methods=['GET', 'POST'])
def reset_password(user_id):
    user = User.query.get_or_404(user_id)
    
    if request.method == 'POST':
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        # Validate passwords
        if len(new_password) < 6:
            flash('Password must be at least 6 characters long', 'error')
            return redirect(url_for('reset_password', user_id=user_id))
        
        if new_password != confirm_password:
            flash('Passwords do not match', 'error')
            return redirect(url_for('reset_password', user_id=user_id))
        
        # Update password
        user.password_hash = generate_password_hash(new_password)
        db.session.commit()
        
        flash('Your password has been reset successfully! Please sign in with your new password.', 'success')
        return redirect(url_for('login'))
    
    return render_template('reset_password.html')

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
    
    # Convert YouTube URL to embed format
    video_embed_url = None
    if recipe.video_url:
        video_url = recipe.video_url
        # Extract video ID from various YouTube URL formats
        if 'youtube.com' in video_url or 'youtu.be' in video_url:
            if 'v=' in video_url:
                video_id = video_url.split('v=')[1].split('&')[0]
            elif 'youtu.be/' in video_url:
                video_id = video_url.split('youtu.be/')[1].split('?')[0]
            elif 'embed/' in video_url:
                video_id = video_url.split('embed/')[1].split('?')[0]
            else:
                video_id = None
            if video_id:
                video_embed_url = f'https://www.youtube.com/embed/{video_id}'
        else:
            video_embed_url = video_url
    
    return render_template('recipe_detail.html', recipe=recipe, is_favorite=is_favorite, video_embed_url=video_embed_url)

@app.route('/add_recipe', methods=['GET', 'POST'])
@login_required
def add_recipe():
    if request.method == 'POST':
        # Handle image upload
        image_url = ''
        if 'image_file' in request.files:
            file = request.files['image_file']
            if file and file.filename != '':
                if allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    # Add timestamp to prevent filename collisions
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    filename = f"{timestamp}_{filename}"
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                    image_url = f'/static/uploads/{filename}'
                else:
                    flash('Invalid file type. Please upload an image (png, jpg, jpeg, gif, webp)', 'error')
                    return redirect(url_for('add_recipe'))
        
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
        
        # Update progress
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

@app.route('/edit_recipe/<int:recipe_id>', methods=['GET', 'POST'])
@login_required
def edit_recipe(recipe_id):
    recipe = Recipe.query.get_or_404(recipe_id)
    
    # Check if current user is the owner
    if recipe.user_id != current_user.id:
        flash('You can only edit your own recipes!', 'error')
        return redirect(url_for('recipe_detail', recipe_id=recipe_id))
    
    if request.method == 'POST':
        # Handle image upload
        image_url = recipe.image_url  # Keep existing image by default
        if 'image_file' in request.files:
            file = request.files['image_file']
            if file and file.filename != '':
                if allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    filename = f"{timestamp}_{filename}"
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                    image_url = f'/static/uploads/{filename}'
                else:
                    flash('Invalid file type. Please upload an image (png, jpg, jpeg, gif, webp)', 'error')
                    return redirect(url_for('edit_recipe', recipe_id=recipe_id))
        
        # Update recipe fields
        recipe.title = request.form['title']
        recipe.description = request.form['description']
        recipe.ingredients = request.form['ingredients']
        recipe.instructions = request.form['instructions']
        recipe.cooking_time = int(request.form['cooking_time'])
        recipe.difficulty = request.form['difficulty']
        recipe.tags = request.form.get('tags', '')
        recipe.image_url = image_url
        recipe.video_url = request.form.get('video_url', '')
        
        db.session.commit()
        flash('Recipe updated successfully!', 'success')
        return redirect(url_for('recipe_detail', recipe_id=recipe_id))
    
    return render_template('edit_recipe.html', recipe=recipe)

@app.route('/ingredient-suggester')
def ingredient_suggester():
    return render_template('ingredient_suggester.html')

@app.route('/api/suggest-recipes', methods=['POST'])
def suggest_recipes():
    ingredients = request.json.get('ingredients', [])
    
    if not ingredients:
        return jsonify([])
    
    all_recipes = Recipe.query.all()
    matched_recipes = []
    
    for recipe in all_recipes:
        recipe_ingredients = recipe.ingredients.lower()
        match_count = sum(1 for ing in ingredients if ing.lower() in recipe_ingredients)
        if match_count > 0:
            matched_recipes.append({
                'id': recipe.id,
                'title': recipe.title,
                'description': recipe.description,
                'cooking_time': recipe.cooking_time,
                'difficulty': recipe.difficulty,
                'match_score': match_count,
                'image_url': recipe.image_url or '/static/images/default-recipe.jpg'
            })
    
    matched_recipes.sort(key=lambda x: x['match_score'], reverse=True)
    return jsonify(matched_recipes[:10])

@app.route('/community')
def community():
    posts = Post.query.order_by(Post.created_at.desc()).all()
    return render_template('community.html', posts=posts)

@app.route('/add_post', methods=['POST'])
@login_required
def add_post():
    # Handle image upload
    image_url = ''
    if 'image_file' in request.files:
        file = request.files['image_file']
        if file and file.filename != '':
            if allowed_file(file.filename):
                filename = secure_filename(file.filename)
                # Add timestamp to prevent filename collisions
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f"{timestamp}_{filename}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                image_url = f'/static/uploads/{filename}'
            else:
                flash('Invalid file type. Please upload an image (png, jpg, jpeg, gif, webp)', 'error')
                return redirect(url_for('community'))
    
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

@app.route('/api/like_post/<int:post_id>', methods=['POST'])
@login_required
def like_post(post_id):
    post = Post.query.get_or_404(post_id)
    post.likes += 1
    db.session.commit()
    return jsonify({'likes': post.likes})

@app.route('/api/post/<int:post_id>/comments', methods=['GET', 'POST'])
@login_required
def post_comments(post_id):
    post = Post.query.get_or_404(post_id)
    
    if request.method == 'POST':
        data = request.get_json()
        content = data.get('content', '').strip()
        
        if not content:
            return jsonify({'error': 'Comment cannot be empty'}), 400
        
        comment = Comment(
            content=content,
            user_id=current_user.id,
            post_id=post_id
        )
        db.session.add(comment)
        db.session.commit()
        
        return jsonify({
            'id': comment.id,
            'content': comment.content,
            'author': comment.user.username,
            'created_at': comment.created_at.strftime('%B %d, %Y at %I:%M %p'),
            'success': True
        })
    
    # GET request - return all comments
    comments = Comment.query.filter_by(post_id=post_id).order_by(Comment.created_at.desc()).all()
    return jsonify([{
        'id': c.id,
        'content': c.content,
        'author': c.user.username,
        'created_at': c.created_at.strftime('%B %d, %Y at %I:%M %p')
    } for c in comments])

@app.route('/api/post/<int:post_id>/edit', methods=['POST'])
@login_required
def edit_post(post_id):
    """Edit a post - only the post owner can edit"""
    post = Post.query.get_or_404(post_id)
    
    # Check if current user is the post owner
    if post.user_id != current_user.id:
        return jsonify({'error': 'You can only edit your own posts'}), 403
    
    data = request.get_json()
    content = data.get('content', '').strip()
    
    if not content:
        return jsonify({'error': 'Post content cannot be empty'}), 400
    
    # Update the post
    post.content = content
    db.session.commit()
    
    return jsonify({
        'success': True,
        'id': post.id,
        'content': post.content,
        'message': 'Post updated successfully'
    })

@app.route('/api/post/<int:post_id>/delete', methods=['POST'])
@login_required
def delete_post(post_id):
    """Delete a post - only the post owner can delete"""
    post = Post.query.get_or_404(post_id)
    
    # Check if current user is the post owner
    if post.user_id != current_user.id:
        return jsonify({'error': 'You can only delete your own posts'}), 403
    
    # Delete the post (comments will be cascade deleted due to relationship)
    db.session.delete(post)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'Post deleted successfully'
    })

@app.route('/favorites')
@login_required
def favorites():
    user_favorites = Favorite.query.filter_by(user_id=current_user.id).all()
    recipes = [fav.recipe for fav in user_favorites]
    return render_template('favorites.html', recipes=recipes)

@app.route('/add_favorite/<int:recipe_id>', methods=['POST'])
@login_required
def add_favorite(recipe_id):
    existing = Favorite.query.filter_by(user_id=current_user.id, recipe_id=recipe_id).first()
    if not existing:
        favorite = Favorite(user_id=current_user.id, recipe_id=recipe_id)
        db.session.add(favorite)
        db.session.commit()
        flash('Added to favorites!', 'success')
    else:
        flash('Already in favorites!', 'info')
    return redirect(url_for('recipe_detail', recipe_id=recipe_id))

@app.route('/remove_favorite/<int:recipe_id>', methods=['POST'])
@login_required
def remove_favorite(recipe_id):
    favorite = Favorite.query.filter_by(user_id=current_user.id, recipe_id=recipe_id).first()
    if favorite:
        db.session.delete(favorite)
        db.session.commit()
        flash('Removed from favorites!', 'success')
    return redirect(request.referrer or url_for('favorites'))

@app.route('/progress')
@login_required
def progress():
    user_progress = Progress.query.filter_by(user_id=current_user.id).all()
    total_recipes = sum(p.completed_recipes for p in user_progress)
    avg_level = sum(p.level for p in user_progress) / len(user_progress) if user_progress else 0
    
    return render_template('progress.html', 
                         progress=user_progress, 
                         total_recipes=total_recipes, 
                         avg_level=avg_level)

@app.route('/tutorials')
def tutorials():
    # Sample video tutorials data
    tutorials = [
        {
            'title': 'Knife Skills 101',
            'description': 'Learn basic knife cuts and techniques',
            'video_url': 'https://www.youtube.com/embed/DY-8nH8A1yY',
            'duration': '15:30',
            'level': 'beginner'
        },
        {
            'title': 'Perfect Sautéing',
            'description': 'Master the art of sautéing vegetables and proteins',
            'video_url': 'https://www.youtube.com/embed/gyuP1nQW33g',
            'duration': '12:45',
            'level': 'beginner'
        },
        {
            'title': 'Baking Basics',
            'description': 'Essential techniques for successful baking',
            'video_url': 'https://www.youtube.com/embed/4bPF_3kDZ6g',
            'duration': '20:15',
            'level': 'intermediate'
        },
        {
            'title': 'Grilling Like a Pro',
            'description': 'Advanced grilling techniques for perfect results',
            'video_url': 'https://www.youtube.com/embed/f2QbZ8X0gXg',
            'duration': '18:20',
            'level': 'advanced'
        },
        {
            'title': 'Plating and Presentation',
            'description': 'Make your dishes look restaurant-quality',
            'video_url': 'https://www.youtube.com/embed/t9qG55Fw3jU',
            'duration': '10:30',
            'level': 'intermediate'
        }
    ]
    return render_template('tutorials.html', tutorials=tutorials)

@app.route('/ai-chef')
def ai_chef():
    return render_template('ai_chef.html')

@app.route('/api/ai-chef-chat', methods=['POST'])
def ai_chef_chat():
    data = request.json
    message = data.get('message', '').strip()
    
    # Return a helpful response without using AI API
    return jsonify({'response': "Hi! I'm Chef Kaya. I can help you with cooking tips and recipe suggestions. What would you like to know?"})


@app.route('/meal-planner')
@login_required
def meal_planner():
    # Get current user's meal plan for this week
    today = datetime.now().date()
    week_start = today - timedelta(days=today.weekday())
    
    meal_plans = MealPlan.query.filter_by(
        user_id=current_user.id,
        week_start=week_start
    ).all()
    
    # Generate AI meal plan if none exists
    if not meal_plans:
        recipes = Recipe.query.all()
        if recipes:
            days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
            meals = ['Breakfast', 'Lunch', 'Dinner']
            
            for day in days:
                for meal in meals:
                    if recipes:
                        recipe = random.choice(recipes)
                        plan = MealPlan(
                            user_id=current_user.id,
                            day=day,
                            meal_type=meal,
                            recipe_id=recipe.id,
                            week_start=week_start
                        )
                        db.session.add(plan)
            
            db.session.commit()
            meal_plans = MealPlan.query.filter_by(
                user_id=current_user.id,
                week_start=week_start
            ).all()
    
    return render_template('meal_planner.html', meal_plans=meal_plans, week_start=week_start)

@app.route('/api/generate-meal-plan', methods=['POST'])
@login_required
def generate_meal_plan():
    preferences = request.json.get('preferences', {})
    skill_level = current_user.skill_level
    
    recipes = Recipe.query.all()
    if not recipes:
        return jsonify({'error': 'No recipes available'})
    
    # Filter by difficulty based on skill level
    if skill_level == 'beginner':
        recipes = [r for r in recipes if r.difficulty in ['easy', 'beginner']]
    elif skill_level == 'intermediate':
        recipes = [r for r in recipes if r.difficulty in ['easy', 'medium', 'intermediate']]
    
    # Simple meal plan generation
    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    meals = ['Breakfast', 'Lunch', 'Dinner']
    
    meal_plan = {}
    for day in days:
        meal_plan[day] = {}
        for meal in meals:
            if recipes:
                recipe = random.choice(recipes)
                meal_plan[day][meal] = {
                    'id': recipe.id,
                    'title': recipe.title,
                    'cooking_time': recipe.cooking_time,
                    'difficulty': recipe.difficulty
                }
    
    return jsonify(meal_plan)

@app.route('/api/generate-recipe', methods=['POST'])
@login_required
def generate_recipe():
    data = request.json
    ingredients = data.get('ingredients', [])
    
    if not ingredients:
        return jsonify({'error': 'No ingredients provided'}), 400
    
    # Return a sample recipe without using AI
    sample_recipe = {
        'title': f'Delicious {ingredients[0].title()} Dish',
        'description': f'A wonderful recipe featuring {", ".join(ingredients)}',
        'difficulty': 'Medium',
        'cooking_time': 30,
        'ingredients': ingredients + ['Salt', 'Pepper', 'Olive oil'],
        'instructions': [
            'Prepare all ingredients',
            'Heat oil in a pan',
            'Cook ingredients together',
            'Season and serve'
        ],
        'tips': 'Use fresh ingredients for best results'
    }
    
    return jsonify({'recipe': sample_recipe})

@app.route('/api/save-generated-recipe', methods=['POST'])
@login_required
def save_generated_recipe():
    data = request.json
    recipe_data = data.get('recipe', {})
    
    if not recipe_data:
        return jsonify({'success': False, 'message': 'No recipe data provided'}), 400
    
    try:
        recipe = Recipe(
            title=recipe_data.get('title', 'Untitled Recipe'),
            description=recipe_data.get('description', ''),
            ingredients='\n'.join(recipe_data.get('ingredients', [])),
            instructions='\n'.join([f"{i+1}. {step}" for i, step in enumerate(recipe_data.get('instructions', []))]),
            cooking_time=recipe_data.get('cooking_time', 30),
            difficulty=recipe_data.get('difficulty', 'medium').lower(),
            tags='AI Generated',
            user_id=current_user.id
        )
        db.session.add(recipe)
        db.session.commit()
        
        # Update progress
        progress = Progress.query.filter_by(user_id=current_user.id).first()
        if progress:
            progress.completed_recipes += 1
            progress.experience += 50
            if progress.experience >= 100:
                progress.level += 1
                progress.experience = 0
            db.session.commit()
        
        return jsonify({'success': True, 'recipe_id': recipe.id})
        
    except Exception as e:
        print(f"Save recipe error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# Admin Routes
@app.route('/admin')
@login_required
@admin_required
def admin_dashboard():
    # Overview statistics
    total_users = User.query.count()
    total_recipes = Recipe.query.count()
    total_posts = Post.query.count()
    total_favorites = Favorite.query.count()
    
    # Recent activity
    recent_users = User.query.order_by(User.created_at.desc()).limit(5).all()
    recent_recipes = Recipe.query.order_by(Recipe.created_at.desc()).limit(5).all()
    recent_posts = Post.query.order_by(Post.created_at.desc()).limit(5).all()
    
    return render_template('admin_dashboard.html',
                         total_users=total_users,
                         total_recipes=total_recipes,
                         total_posts=total_posts,
                         total_favorites=total_favorites,
                         recent_users=recent_users,
                         recent_recipes=recent_recipes,
                         recent_posts=recent_posts)

@app.route('/admin/users')
@login_required
@admin_required
def admin_users():
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('admin_users.html', users=users)

@app.route('/admin/user/<int:user_id>/toggle_admin', methods=['POST'])
@login_required
@admin_required
def toggle_admin(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('Cannot remove admin from yourself', 'error')
    else:
        user.is_admin = not user.is_admin
        db.session.commit()
        flash(f'Admin status updated for {user.username}', 'success')
    return redirect(url_for('admin_users'))

@app.route('/admin/user/<int:user_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('Cannot delete yourself', 'error')
    else:
        db.session.delete(user)
        db.session.commit()
        flash(f'User {user.username} deleted', 'success')
    return redirect(url_for('admin_users'))

@app.route('/admin/recipes')
@login_required
@admin_required
def admin_recipes():
    recipes = Recipe.query.order_by(Recipe.created_at.desc()).all()
    return render_template('admin_recipes.html', recipes=recipes)

@app.route('/admin/recipe/<int:recipe_id>/delete', methods=['POST'])
@login_required
@admin_required
def admin_delete_recipe(recipe_id):
    recipe = Recipe.query.get_or_404(recipe_id)
    db.session.delete(recipe)
    db.session.commit()
    flash(f'Recipe "{recipe.title}" deleted', 'success')
    return redirect(url_for('admin_recipes'))

@app.route('/admin/posts')
@login_required
@admin_required
def admin_posts():
    posts = Post.query.order_by(Post.created_at.desc()).all()
    return render_template('admin_posts.html', posts=posts)

@app.route('/admin/post/<int:post_id>/delete', methods=['POST'])
@login_required
@admin_required
def admin_delete_post(post_id):
    post = Post.query.get_or_404(post_id)
    db.session.delete(post)
    db.session.commit()
    flash('Post deleted', 'success')
    return redirect(url_for('admin_posts'))

# Initialize database
@app.cli.command('init-db')
def init_db():
    db.create_all()
    print('Database initialized!')

@app.cli.command('create-admin')
@click.argument('username')
@click.argument('email')
@click.password_option()
def create_admin(username, email, password):
    """Create an admin user."""
    from werkzeug.security import generate_password_hash
    
    with app.app_context():
        existing = User.query.filter_by(username=username).first()
        if existing:
            print(f'User {username} already exists')
            return
        
        user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password),
            is_admin=True,
            skill_level='advanced'
        )
        db.session.add(user)
        
        # Initialize progress tracking for admin
        skills = ['Knife Skills', 'Sautéing', 'Baking', 'Grilling', 'Plating']
        for skill in skills:
            progress = Progress(user_id=user.id, skill_name=skill)
            db.session.add(progress)
        
        db.session.commit()
        print(f'Admin user {username} created successfully!')

# Initialize database tables on startup (for Render deployment)
def init_database():
    try:
        with app.app_context():
            db.create_all()
            
            # Create default admin account only if it doesn't exist
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
                
                # Initialize progress tracking for admin
                skills = ['Knife Skills', 'Sautéing', 'Baking', 'Grilling', 'Plating']
                for skill in skills:
                    progress = Progress(user_id=admin_user.id, skill_name=skill)
                    db.session.add(progress)
                
                db.session.commit()
                print('Database initialized! Admin: admin / admin123')
    except Exception as e:
        print(f'Database init error (may retry): {e}')

# Call init on startup
init_database()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
