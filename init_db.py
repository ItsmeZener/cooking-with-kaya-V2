#!/usr/bin/env python3
"""Initialize database tables for Cooking with Kaya"""
import os
import sys

# Add the project directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app, db

def init_database():
    """Create all database tables"""
    with app.app_context():
        print("Creating database tables...")
        db.create_all()
        print("Database tables created successfully!")
        
        # Create admin user if it doesn't exist
        from app import User
        from werkzeug.security import generate_password_hash
        
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            admin = User(
                username='admin',
                email='admin@cookingwithkaya.com',
                password_hash=generate_password_hash('admin123'),
                is_admin=True,
                skill_level='expert'
            )
            db.session.add(admin)
            db.session.commit()
            print("Admin user created: admin / admin123")
        else:
            print("Admin user already exists")
        
        print("Database initialization complete!")

if __name__ == '__main__':
    init_database()
