-- Cooking with Kaya - MySQL Database Schema
-- Run this in XAMPP phpMyAdmin to create the database and tables

CREATE DATABASE IF NOT EXISTS cooking_with_kaya CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE cooking_with_kaya;

-- User Table
CREATE TABLE user (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(80) NOT NULL UNIQUE,
    email VARCHAR(120) NOT NULL UNIQUE,
    password_hash VARCHAR(256),
    skill_level VARCHAR(20) DEFAULT 'beginner',
    dietary_preferences VARCHAR(200),
    is_admin BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Recipe Table
CREATE TABLE recipe (
    id INT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    description TEXT,
    ingredients TEXT NOT NULL,
    instructions TEXT NOT NULL,
    cooking_time INT,
    difficulty VARCHAR(20),
    image_url VARCHAR(500),
    video_url VARCHAR(500),
    tags VARCHAR(200),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    user_id INT,
    FOREIGN KEY (user_id) REFERENCES user(id) ON DELETE SET NULL
);

-- Post Table (Community)
CREATE TABLE post (
    id INT AUTO_INCREMENT PRIMARY KEY,
    content TEXT NOT NULL,
    image_url VARCHAR(500),
    recipe_link VARCHAR(200),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    user_id INT,
    likes INT DEFAULT 0,
    FOREIGN KEY (user_id) REFERENCES user(id) ON DELETE CASCADE
);

-- Comment Table
CREATE TABLE comment (
    id INT AUTO_INCREMENT PRIMARY KEY,
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    user_id INT,
    post_id INT,
    FOREIGN KEY (user_id) REFERENCES user(id) ON DELETE CASCADE,
    FOREIGN KEY (post_id) REFERENCES post(id) ON DELETE CASCADE
);

-- Favorite Table (User's favorite recipes)
CREATE TABLE favorite (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT,
    recipe_id INT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES user(id) ON DELETE CASCADE,
    FOREIGN KEY (recipe_id) REFERENCES recipe(id) ON DELETE CASCADE,
    UNIQUE KEY unique_favorite (user_id, recipe_id)
);

-- Progress Table (User skill tracking)
CREATE TABLE progress (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT,
    skill_name VARCHAR(100),
    level INT DEFAULT 1,
    experience INT DEFAULT 0,
    completed_recipes INT DEFAULT 0,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES user(id) ON DELETE CASCADE
);

-- MealPlan Table
CREATE TABLE meal_plan (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT,
    day VARCHAR(20),
    meal_type VARCHAR(20),
    recipe_id INT,
    week_start DATE,
    FOREIGN KEY (user_id) REFERENCES user(id) ON DELETE CASCADE,
    FOREIGN KEY (recipe_id) REFERENCES recipe(id) ON DELETE SET NULL
);

-- Indexes for better performance
CREATE INDEX idx_recipe_user ON recipe(user_id);
CREATE INDEX idx_post_user ON post(user_id);
CREATE INDEX idx_comment_post ON comment(post_id);
CREATE INDEX idx_comment_user ON comment(user_id);
CREATE INDEX idx_favorite_user ON favorite(user_id);
CREATE INDEX idx_favorite_recipe ON favorite(recipe_id);
CREATE INDEX idx_progress_user ON progress(user_id);
CREATE INDEX idx_mealplan_user ON meal_plan(user_id);
CREATE INDEX idx_mealplan_recipe ON meal_plan(recipe_id);
CREATE INDEX idx_mealplan_week ON meal_plan(week_start);
