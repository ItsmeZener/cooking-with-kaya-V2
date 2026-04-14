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

class PostLike(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Unique constraint to prevent duplicate likes
    __table_args__ = (db.UniqueConstraint('user_id', 'post_id', name='unique_post_like'),)
    
    # Relationships
    user = db.relationship('User', backref='post_likes')
    post = db.relationship('Post', backref='likes_rel')

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
    
    # Relationship to Recipe
    recipe = db.relationship('Recipe', backref='meal_plans')

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
            password_hash=generate_password_hash(password, method="pbkdf2:sha256"),
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
        user.password_hash = generate_password_hash(new_password, method='pbkdf2:sha256')
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
            cooking_time=int(request.form['cooking_hours']) * 60 + int(request.form['cooking_minutes']),
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
        recipe.cooking_time = int(request.form['cooking_hours']) * 60 + int(request.form['cooking_minutes'])
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
    
    # Get set of post IDs that current user has liked
    liked_post_ids = set()
    if current_user.is_authenticated:
        user_likes = PostLike.query.filter_by(user_id=current_user.id).all()
        liked_post_ids = {like.post_id for like in user_likes}
    
    return render_template('community.html', posts=posts, liked_post_ids=liked_post_ids)

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
    
    # Check if user already liked this post
    existing_like = PostLike.query.filter_by(user_id=current_user.id, post_id=post_id).first()
    
    if existing_like:
        # User already liked, so unlike (remove the like)
        db.session.delete(existing_like)
        post.likes = max(0, post.likes - 1)
        liked = False
    else:
        # User hasn't liked, so add like
        new_like = PostLike(user_id=current_user.id, post_id=post_id)
        db.session.add(new_like)
        post.likes += 1
        liked = True
    
    db.session.commit()
    return jsonify({'likes': post.likes, 'liked': liked})

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

@app.route('/api/complete_recipe/<int:recipe_id>', methods=['POST'])
@login_required
def complete_recipe(recipe_id):
    """Handle recipe completion photo upload and post to community"""
    recipe = Recipe.query.get_or_404(recipe_id)
    
    # Handle image upload
    image_url = ''
    if 'photo' in request.files:
        file = request.files['photo']
        if file and file.filename != '':
            if allowed_file(file.filename):
                filename = secure_filename(file.filename)
                # Add timestamp to prevent filename collisions
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f"{timestamp}_{filename}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                image_url = f'/static/uploads/{filename}'
    
    # Create post content
    content = f"🎉 Just cooked {recipe.title}! It was delicious! Check out my creation. 🍽️"
    
    # Create community post
    post = Post(
        content=content,
        image_url=image_url,
        recipe_link=f'/recipe/{recipe.id}',
        user_id=current_user.id
    )
    db.session.add(post)
    
    # Update user progress
    progress = Progress.query.filter_by(user_id=current_user.id).first()
    if not progress:
        progress = Progress(user_id=current_user.id, skill_name='Cooking')
        db.session.add(progress)
    
    progress.completed_recipes += 1
    progress.experience += 50
    
    # Level up if enough experience
    if progress.experience >= 100:
        progress.level += 1
        progress.experience = 0
    
    db.session.commit()
    
    # Flash success message and redirect to community
    flash('Recipe completed and shared to community!', 'success')
    return redirect(url_for('community'))

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

@app.route('/meal-planner')
@login_required
def meal_planner():
    from datetime import datetime, timedelta
    
    # Get current week's meal plan
    today = datetime.now().date()
    week_start = today - timedelta(days=today.weekday())
    
    print(f"DEBUG meal_planner: today={today}, week_start={week_start}")
    
    meal_plans = MealPlan.query.filter_by(
        user_id=current_user.id,
        week_start=week_start
    ).all()
    
    print(f"DEBUG meal_planner: Found {len(meal_plans)} meal plans for week {week_start}")
    for mp in meal_plans[:3]:  # Log first 3
        print(f"  - {mp.day} {mp.meal_type}: recipe_id={mp.recipe_id}")
    
    if not meal_plans:
        # If no meal plan exists for this week, generate one
        print(f"DEBUG meal_planner: No plans found, generating...")
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
    try:
        preferences = request.json.get('preferences', {})
        skill_level = getattr(current_user, 'skill_level', 'beginner')  # Safe attribute access with default
        
        print(f"DEBUG: Generating meal plan for user {current_user.id}, skill_level: {skill_level}")
        
        # Get current week's start date
        today = datetime.now().date()
        week_start = today - timedelta(days=today.weekday())
        
        # Delete existing meal plans for this week
        deleted = MealPlan.query.filter_by(
            user_id=current_user.id,
            week_start=week_start
        ).delete()
        db.session.commit()
        print(f"DEBUG: Deleted {deleted} existing meal plans")
        
        recipes = Recipe.query.all()
        if not recipes:
            print("DEBUG: No recipes found in database")
            return jsonify({'error': 'No recipes available. Please add some recipes first.'}), 400
        
        print(f"DEBUG: Found {len(recipes)} recipes")
        
        # Filter by difficulty based on skill level
        filtered_recipes = recipes
        if skill_level == 'beginner':
            filtered_recipes = [r for r in recipes if r.difficulty in ['easy', 'beginner']]
        elif skill_level == 'intermediate':
            filtered_recipes = [r for r in recipes if r.difficulty in ['easy', 'medium', 'intermediate']]
        
        # If no recipes after filtering, use all recipes
        if not filtered_recipes:
            print(f"DEBUG: No recipes match skill level {skill_level}, using all recipes")
            filtered_recipes = recipes
        
        print(f"DEBUG: Using {len(filtered_recipes)} recipes for meal plan")
        
        # Generate and save meal plan
        days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        meals = ['Breakfast', 'Lunch', 'Dinner']
        
        for day in days:
            for meal in meals:
                if filtered_recipes:
                    recipe = random.choice(filtered_recipes)
                    plan = MealPlan(
                        user_id=current_user.id,
                        day=day,
                        meal_type=meal,
                        recipe_id=recipe.id,
                        week_start=week_start
                    )
                    db.session.add(plan)
        
        db.session.commit()
        print(f"DEBUG: Successfully created meal plan with {len(days) * len(meals)} meals")
        
        return jsonify({'success': True, 'message': 'Meal plan generated successfully'})
        
    except Exception as e:
        import traceback
        error_msg = str(e)
        print(f"ERROR: Failed to generate meal plan: {error_msg}")
        print(f"Traceback: {traceback.format_exc()}")
        db.session.rollback()
        return jsonify({'error': f'Failed to generate meal plan: {error_msg}'}), 500

@app.route('/api/test', methods=['GET'])
def test_api():
    return jsonify({'status': 'ok', 'message': 'API is working'})

@app.route('/api/test-post', methods=['POST'])
@login_required
def test_post_api():
    """Simple test endpoint that returns static JSON"""
    data = request.json
    return jsonify({
        'status': 'ok',
        'message': 'POST API is working',
        'received': data
    })

@app.route('/api/generate-recipe', methods=['POST'])
@login_required
def generate_recipe():
    print("DEBUG: generate_recipe called")
    data = request.json
    ingredients = data.get('ingredients', [])
    
    print(f"DEBUG: ingredients = {ingredients}")
    
    if not ingredients:
        print("DEBUG: No ingredients provided")
        return jsonify({'error': 'No ingredients provided'}), 400
    
    try:
        from groq import Groq
        
        # Use Groq API - Free tier available at console.groq.com
        api_key = os.environ.get('GROQ_API_KEY', '')  # Get from environment variable
        
        # Create Groq client
        client = Groq(api_key=api_key)
        
        # Create prompt for Groq
        ingredients_str = ", ".join(ingredients)
        prompt = f"""You are an expert chef with 20 years of experience. Create a professional, restaurant-quality recipe using these ingredients: {ingredients_str}.

Please provide the response in this exact JSON format:
{{
    "title": "Creative, appetizing recipe name",
    "description": "An enticing, mouth-watering description (2-3 sentences that make the dish sound delicious and professional)",
    "difficulty": "Easy/Medium/Hard",
    "cooking_time": 30 (estimated minutes, be realistic for a home cook),
    "ingredients": ["ingredient 1 with exact quantity", "ingredient 2 with exact quantity", ...],
    "instructions": [
        "Step 1: Very detailed action - Start with preparation. Include specific knife cuts (dice, julienne, mince), measurements, and WHY this step matters",
        "Step 2: Cooking technique - Specify exact heat level (medium-high, low simmer), pan type, oil temperature. Explain WHAT to look for (visual cues, sounds, smells)",
        "Step 3: Layering flavors - Add ingredients in order. Include specific timing (2-3 minutes until golden, stir constantly for 30 seconds)",
        "Step 4: Temperature control - Specify exact temperatures when possible (350°F, bring to gentle boil). Include resting times if needed",
        "Step 5: Finishing touches - How to plate, garnish, or add final seasonings. Include presentation tips",
        "Step 6-8: Continue with 3-4 more detailed steps covering resting, plating, and serving"
    ],
    "tips": "3-4 professional chef tips: include ingredient substitutions, common mistakes to avoid, wine pairings, storage tips, or reheating instructions"
}}

CRITICAL REQUIREMENTS:
- Instructions MUST be extremely detailed - each step should be 2-4 sentences explaining the technique, timing, and why it matters
- Include specific temperatures in Fahrenheit and cooking times
- Mention visual cues (golden brown, translucent, bubbling)
- Include chef secrets that make the difference between good and great
- Suggest specific cookware (cast iron skillet, non-stick pan, Dutch oven) when relevant
- Add technique tips (folding vs stirring, resting meat, tempering eggs)
- Cooking time should account for prep AND cooking
- Write like a Michelin-star chef teaching a passionate home cook

Return ONLY the JSON object, nothing else before or after it."""

        # Generate recipe with Groq (Llama 3.1 8B - fast and free)
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": "You are a professional chef with 20 years of experience."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=2000
        )
        
        ai_response = response.choices[0].message.content
        
        # Try to extract JSON from the response
        try:
            # Find JSON in the response
            start_idx = ai_response.find('{')
            end_idx = ai_response.rfind('}') + 1
            if start_idx != -1 and end_idx != -1:
                json_str = ai_response[start_idx:end_idx]
                recipe_data = json.loads(json_str)
            else:
                recipe_data = json.loads(ai_response)
            
            return jsonify({'recipe': recipe_data})
            
        except json.JSONDecodeError as je:
            print(f"DEBUG: JSON decode error: {je}")
            print(f"DEBUG: ai_response was: {ai_response[:200]}")
            # If parsing fails, return enhanced mock response
            sample_recipe = {
                'title': f'Pan-Seared {ingredients[0].title()} with Herb Butter',
                'description': f'A restaurant-quality dish featuring fresh {", ".join(ingredients)}. This recipe brings together classic techniques with modern flavors.',
                'difficulty': 'Medium',
                'cooking_time': 35,
                'ingredients': ingredients + ['2 tbsp butter', '2 cloves garlic', 'Fresh herbs', 'Salt and pepper'],
                'instructions': [
                    'Step 1: Preparation - Wash and dry all ingredients. Cut into uniform pieces for even cooking.',
                    'Step 2: Heat Control - Preheat skillet over medium-high heat for 3-4 minutes until hot.',
                    'Step 3: Sear - Add ingredients to hot pan. Don\'t move for 2-3 minutes to develop golden crust.',
                    'Step 4: Build Flavor - Add aromatics and stir for 30 seconds until fragrant.',
                    'Step 5: Deglaze - Add liquid to release browned bits from pan bottom.',
                    'Step 6: Finish - Add butter and herbs, swirl to create glossy sauce.',
                    'Step 7: Rest - Let dish rest 2-3 minutes off heat for juices to redistribute.',
                    'Step 8: Plate - Serve hot with sauce spooned over top.'
                ],
                'tips': 'Pro Tips: Use room temperature ingredients. Don\'t overcrowd the pan. Season at every stage. Pair with crisp white wine.'
            }
            return jsonify({'recipe': sample_recipe})
            
    except Exception as e:
        import traceback
        error_msg = str(e)
        print(f"DEBUG: AI Error: {error_msg}")
        print(f"DEBUG: Full traceback: {traceback.format_exc()}")
        # Log error to file for debugging
        with open('ai_error.log', 'a', encoding='utf-8') as f:
            f.write(f"\n=== ERROR at {datetime.now()} ===\n")
            f.write(f"Error: {error_msg}\n")
            f.write(f"Traceback:\n{traceback.format_exc()}\n")
        # Return enhanced fallback mock recipe on any error
        sample_recipe = {
            'title': f'Pan-Seared {ingredients[0].title()} with Herb Butter',
            'description': f'A restaurant-quality dish featuring fresh {", ".join(ingredients)}. This recipe brings together classic techniques with modern flavors for an unforgettable dining experience.',
            'difficulty': 'Medium',
            'cooking_time': 35,
            'ingredients': ingredients + ['2 tbsp butter', '2 cloves garlic, minced', '1 tsp fresh herbs', 'Salt and pepper to taste', '1 tbsp olive oil'],
            'instructions': [
                'Step 1: Preparation - Wash and dry all ingredients thoroughly. Cut vegetables into uniform pieces (1/2 inch dice) to ensure even cooking. Pat proteins dry with paper towels to achieve a perfect sear.',
                'Step 2: Heat Control - Preheat a heavy-bottomed skillet (cast iron preferred) over medium-high heat for 3-4 minutes until a drop of water sizzles immediately. Add olive oil and swirl to coat.',
                'Step 3: Sear - Add the main ingredient to the hot pan. Do not move it for 2-3 minutes to develop a golden-brown crust. Listen for the sizzle - it should be audible but not violent.',
                'Step 4: Build Flavor - Add aromatics (garlic, onions) and stir constantly for 30 seconds until fragrant. The kitchen should smell amazing at this point.',
                'Step 5: Deglaze - Add a splash of liquid (wine, broth, or water) to release the fond (browned bits) from the bottom of the pan. Scrape with a wooden spoon.',
                'Step 6: Finish - Reduce heat to low, add butter and fresh herbs. Swirl the pan to create a glossy sauce. The butter should foam but not burn.',
                'Step 7: Rest and Plate - Let the dish rest for 2-3 minutes off heat. This allows juices to redistribute. Plate with the sauce spooned over top.',
                'Step 8: Garnish - Add fresh herbs, a drizzle of good olive oil, or a squeeze of lemon just before serving for brightness.'
            ],
            'tips': 'Pro Tips: (1) Use room temperature ingredients for more even cooking. (2) Don\'t overcrowd the pan - cook in batches if needed. (3) Season at every stage, not just at the end. (4) Pair with a crisp white wine or light beer.'
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

@app.route('/api/ai-chef-chat', methods=['POST'])
@login_required
def ai_chef_chat():
    """AI Chef Assistant chat endpoint"""
    data = request.json
    message = data.get('message', '')
    context = data.get('context', '')  # Recipe name or ingredients context
    
    if not message:
        return jsonify({'error': 'No message provided'}), 400
    
    try:
        from groq import Groq
        
        # Use Groq API - Free tier available at console.groq.com
        api_key = os.environ.get('GROQ_API_KEY', '')  # Get from environment variable
        
        # Create Groq client
        client = Groq(api_key=api_key)
        
        # Create system prompt with context
        system_prompt = """You are Chef Kaya, an expert AI cooking assistant with 20 years of culinary experience. 
You help home cooks with:
- Ingredient substitutions and alternatives
- Cooking tips and techniques
- Recipe troubleshooting
- Timing and temperature advice
- Storage and meal prep tips

Respond in a friendly, encouraging tone. Be specific and practical in your advice."""
        
        if context:
            system_prompt += f"\n\nCurrent recipe context: {context}"
        
        # Generate response with Groq
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message}
            ],
            temperature=0.7,
            max_tokens=500
        )
        
        ai_response = response.choices[0].message.content
        return jsonify({'response': ai_response})
        
    except Exception as e:
        print(f"AI Chef Chat Error: {e}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        # Return fallback response with helpful pre-written responses
        demo_responses = {
            'substitutions': "Here are some common substitutions:\n• Butter → Olive oil or coconut oil\n• Eggs → Applesauce or flax eggs\n• Milk → Almond milk or oat milk\n• Sugar → Honey or maple syrup\n• All-purpose flour → Almond flour (use 3/4 amount)",
            'tips': "Here are some pro cooking tips:\n• Always preheat your pan before adding ingredients\n• Season at every stage, not just at the end\n• Let meat rest after cooking for juicier results\n• Use a sharp knife - it's safer than a dull one\n• Read the entire recipe before starting",
            'timing': "Cooking time tips:\n• Prep all ingredients before you start cooking (mise en place)\n• Use a timer to avoid overcooking\n• Let proteins come to room temperature before cooking\n• Rest meat for 5-10 minutes after cooking",
            'storage': "Storage tips:\n• Store herbs in water like flowers\n• Keep potatoes and onions separate\n• Freeze leftover wine in ice cube trays for cooking\n• Label and date everything in the freezer",
        }
        
        # Check message keywords for appropriate response
        msg_lower = message.lower()
        if any(word in msg_lower for word in ['substitute', 'replacement', 'instead of', 'swap']):
            response_text = demo_responses['substitutions']
        elif any(word in msg_lower for word in ['tip', 'trick', 'advice', 'secret']):
            response_text = demo_responses['tips']
        elif any(word in msg_lower for word in ['time', 'how long', 'when', 'minute']):
            response_text = demo_responses['timing']
        elif any(word in msg_lower for word in ['store', 'keep', 'save', 'leftover', 'fridge', 'freezer']):
            response_text = demo_responses['storage']
        else:
            response_text = f"Hi! I'm Chef Kaya. You asked about: '{message}'\n\nI'm here to help with:\n• Ingredient substitutions\n• Cooking tips and techniques\n• Recipe suggestions\n• Timing and storage advice\n\nWhat would you like to know more about?"
        
        return jsonify({'response': response_text})

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
            password_hash=generate_password_hash(password, method="pbkdf2:sha256"),
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
            # First, run migration to fix password_hash column size if using PostgreSQL
            try:
                db.session.execute(text('ALTER TABLE "user" ALTER COLUMN password_hash TYPE VARCHAR(256)'))
                db.session.commit()
                print('Migration: password_hash column upgraded to VARCHAR(256)')
            except Exception as migration_error:
                db.session.rollback()
                # Column might already be correct or table doesn't exist yet
                pass
            
            db.create_all()
            
            # Create default admin account only if it doesn't exist
            existing_admin = User.query.filter_by(username='admin').first()
            if not existing_admin:
                admin_user = User(
                    username='admin',
                    email='admin@cookingwithkaya.com',
                    password_hash=generate_password_hash('admin123', method='pbkdf2:sha256'),
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
