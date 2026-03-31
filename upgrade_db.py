#!/usr/bin/env python3
"""Database migration script to fix password_hash column size"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app, db
from sqlalchemy import text

def upgrade_password_hash_column():
    """Alter password_hash column to VARCHAR(256)"""
    with app.app_context():
        try:
            # Check if we're using PostgreSQL
            db_url = app.config['SQLALCHEMY_DATABASE_URI']
            if 'postgresql' in db_url:
                # PostgreSQL - alter column
                db.session.execute(text('ALTER TABLE "user" ALTER COLUMN password_hash TYPE VARCHAR(256)'))
                db.session.commit()
                print('✅ password_hash column upgraded to VARCHAR(256)')
            else:
                # SQLite - no change needed (TEXT type)
                print('SQLite detected - no migration needed')
        except Exception as e:
            print(f'Migration info: {e}')
            db.session.rollback()

if __name__ == '__main__':
    upgrade_password_hash_column()
