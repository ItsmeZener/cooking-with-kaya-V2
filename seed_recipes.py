"""Seed script to add sample recipes for testing the meal planner."""
from app import app, db, Recipe, User
from datetime import datetime

def seed_recipes():
    with app.app_context():
        # Check if there are any recipes
        existing_count = Recipe.query.count()
        if existing_count > 0:
            print(f"✓ Database already has {existing_count} recipes. No seeding needed.")
            return
        
        # Get the first admin user or create a default user
        admin = User.query.filter_by(is_admin=True).first()
        if not admin:
            admin = User.query.first()
        if not admin:
            print("✗ No users found. Please create a user first.")
            return
        
        sample_recipes = [
            {
                'title': 'Chicken Adobo',
                'description': 'A classic Filipino dish with tender chicken in a savory soy sauce and vinegar marinade.',
                'ingredients': '1 kg chicken, 1/2 cup soy sauce, 1/3 cup vinegar, 6 cloves garlic, 3 bay leaves, 1 tsp peppercorns',
                'instructions': '1. Marinate chicken in soy sauce and garlic for 30 mins. 2. Sauté garlic until golden. 3. Add chicken and brown. 4. Add marinade, vinegar, bay leaves, peppercorns. 5. Simmer for 30 mins. 6. Serve with rice.',
                'cooking_time': 45,
                'difficulty': 'Easy',
                'servings': 4,
                'image_url': 'https://images.unsplash.com/photo-1604579278540-bdb2a5aa9a0c?w=400',
                'cuisine': 'Filipino'
            },
            {
                'title': 'Vegetable Stir Fry',
                'description': 'Quick and healthy mixed vegetable stir fry with garlic sauce.',
                'ingredients': '2 cups broccoli, 1 cup carrots, 1 bell pepper, 2 cloves garlic, 2 tbsp soy sauce, 1 tbsp sesame oil',
                'instructions': '1. Chop all vegetables. 2. Heat oil in wok. 3. Add garlic and sauté. 4. Add vegetables and stir fry for 5 mins. 5. Add soy sauce. 6. Serve hot.',
                'cooking_time': 15,
                'difficulty': 'Easy',
                'servings': 2,
                'image_url': 'https://images.unsplash.com/photo-1512621776951-a57141f2eefd?w=400',
                'cuisine': 'Asian'
            },
            {
                'title': 'Spaghetti Bolognese',
                'description': 'Classic Italian pasta with rich meat sauce.',
                'ingredients': '400g spaghetti, 300g ground beef, 1 onion, 2 cloves garlic, 400g canned tomatoes, 2 tbsp tomato paste, Italian herbs',
                'instructions': '1. Cook spaghetti according to package. 2. Sauté onion and garlic. 3. Add beef and brown. 4. Add tomatoes, paste, and herbs. 5. Simmer for 20 mins. 6. Serve over pasta.',
                'cooking_time': 30,
                'difficulty': 'Medium',
                'servings': 4,
                'image_url': 'https://images.unsplash.com/photo-1551183053-bf91b1f0b5e1?w=400',
                'cuisine': 'Italian'
            },
            {
                'title': 'Grilled Salmon',
                'description': 'Healthy grilled salmon with lemon and herbs.',
                'ingredients': '2 salmon fillets, 1 lemon, 2 tbsp olive oil, salt, pepper, fresh dill',
                'instructions': '1. Season salmon with salt and pepper. 2. Drizzle with olive oil and lemon juice. 3. Grill for 4-5 mins per side. 4. Garnish with dill and serve.',
                'cooking_time': 15,
                'difficulty': 'Easy',
                'servings': 2,
                'image_url': 'https://images.unsplash.com/photo-1467003909585-2f8a72700288?w=400',
                'cuisine': 'International'
            },
            {
                'title': 'Beef Tacos',
                'description': 'Mexican-style beef tacos with fresh toppings.',
                'ingredients': '300g ground beef, taco seasoning, 8 taco shells, lettuce, tomato, cheese, salsa',
                'instructions': '1. Cook beef with taco seasoning. 2. Warm taco shells. 3. Fill shells with beef. 4. Add toppings. 5. Serve immediately.',
                'cooking_time': 20,
                'difficulty': 'Easy',
                'servings': 4,
                'image_url': 'https://images.unsplash.com/photo-1565299585323-38d6b0865b47?w=400',
                'cuisine': 'Mexican'
            },
            {
                'title': 'Caesar Salad',
                'description': 'Fresh romaine lettuce with Caesar dressing and croutons.',
                'ingredients': '1 head romaine lettuce, 1/2 cup croutons, 1/4 cup Parmesan, Caesar dressing, black pepper',
                'instructions': '1. Chop lettuce. 2. Toss with dressing. 3. Add croutons and Parmesan. 4. Season with pepper. 5. Serve chilled.',
                'cooking_time': 10,
                'difficulty': 'Easy',
                'servings': 2,
                'image_url': 'https://images.unsplash.com/photo-1550304943-4f24f54ddde9?w=400',
                'cuisine': 'International'
            },
            {
                'title': 'Pancakes',
                'description': 'Fluffy breakfast pancakes with syrup.',
                'ingredients': '1 cup flour, 1 egg, 1 cup milk, 1 tbsp sugar, 1 tsp baking powder, butter, maple syrup',
                'instructions': '1. Mix dry ingredients. 2. Add wet ingredients. 3. Cook on griddle until golden. 4. Serve with butter and syrup.',
                'cooking_time': 20,
                'difficulty': 'Easy',
                'servings': 2,
                'image_url': 'https://images.unsplash.com/photo-1567620905732-2d1ec7ab7445?w=400',
                'cuisine': 'American'
            },
            {
                'title': 'Chicken Curry',
                'description': 'Aromatic chicken curry with coconut milk.',
                'ingredients': '500g chicken, 1 onion, 2 tbsp curry paste, 1 can coconut milk, 2 potatoes, cilantro',
                'instructions': '1. Sauté onion. 2. Add curry paste. 3. Add chicken and brown. 4. Add coconut milk and potatoes. 5. Simmer for 25 mins. 6. Garnish with cilantro.',
                'cooking_time': 35,
                'difficulty': 'Medium',
                'servings': 4,
                'image_url': 'https://images.unsplash.com/photo-1565557623262-b51c2513a641?w=400',
                'cuisine': 'Indian'
            }
        ]
        
        for recipe_data in sample_recipes:
            recipe = Recipe(
                title=recipe_data['title'],
                description=recipe_data['description'],
                ingredients=recipe_data['ingredients'],
                instructions=recipe_data['instructions'],
                cooking_time=recipe_data['cooking_time'],
                difficulty=recipe_data['difficulty'],
                servings=recipe_data['servings'],
                image_url=recipe_data['image_url'],
                cuisine=recipe_data['cuisine'],
                author=admin
            )
            db.session.add(recipe)
        
        db.session.commit()
        print(f"✓ Successfully added {len(sample_recipes)} sample recipes!")
        print("\nRecipes added:")
        for recipe in sample_recipes:
            print(f"  - {recipe['title']} ({recipe['cuisine']})")

if __name__ == '__main__':
    seed_recipes()
