"""Seed food database (~40 practical items with macro tags)."""

from __future__ import annotations

from typing import Any

# Approximate per typical serving — educational planning only
SEED_FOODS: list[dict[str, Any]] = [
    # Proteins — meat/fish
    {"name": "Grilled chicken breast (150g)", "calories": 248, "protein": 46.5, "carbs": 0, "fat": 5.4, "tags": ["meat", "poultry", "high_protein"]},
    {"name": "Lean beef mince cooked (120g)", "calories": 250, "protein": 30, "carbs": 0, "fat": 14, "tags": ["meat", "high_protein"]},
    {"name": "Baked salmon (120g)", "calories": 250, "protein": 28, "carbs": 0, "fat": 15, "tags": ["fish", "seafood", "high_protein"]},
    {"name": "Canned tuna in water (1 can)", "calories": 120, "protein": 28, "carbs": 0, "fat": 1, "tags": ["fish", "seafood", "high_protein"]},
    {"name": "Turkey breast slices (100g)", "calories": 135, "protein": 29, "carbs": 0, "fat": 2, "tags": ["meat", "poultry", "high_protein"]},
    # Eggs / dairy
    {"name": "Eggs scrambled (2 large)", "calories": 180, "protein": 12, "carbs": 2, "fat": 14, "tags": ["egg", "vegetarian", "high_protein"]},
    {"name": "Greek yogurt plain (200g)", "calories": 130, "protein": 20, "carbs": 8, "fat": 2, "tags": ["dairy", "vegetarian", "high_protein"]},
    {"name": "Cottage cheese (150g)", "calories": 120, "protein": 18, "carbs": 5, "fat": 3, "tags": ["dairy", "vegetarian", "high_protein"]},
    {"name": "Low-fat milk (250ml)", "calories": 105, "protein": 8.5, "carbs": 12, "fat": 2.5, "tags": ["dairy", "vegetarian"]},
    {"name": "Cheddar cheese (30g)", "calories": 120, "protein": 7, "carbs": 0.5, "fat": 10, "tags": ["dairy", "vegetarian"]},
    # Plant proteins
    {"name": "Firm tofu (150g)", "calories": 180, "protein": 20, "carbs": 4, "fat": 10, "tags": ["vegan", "vegetarian", "high_protein"]},
    {"name": "Tempeh (100g)", "calories": 190, "protein": 20, "carbs": 8, "fat": 11, "tags": ["vegan", "vegetarian", "high_protein"]},
    {"name": "Lentil dal cooked (1 cup)", "calories": 230, "protein": 18, "carbs": 40, "fat": 1, "tags": ["vegan", "vegetarian", "high_protein", "gluten_free"]},
    {"name": "Chickpeas cooked (1 cup)", "calories": 270, "protein": 15, "carbs": 45, "fat": 4, "tags": ["vegan", "vegetarian", "high_protein", "gluten_free"]},
    {"name": "Black beans cooked (1 cup)", "calories": 227, "protein": 15, "carbs": 41, "fat": 1, "tags": ["vegan", "vegetarian", "high_protein", "gluten_free"]},
    {"name": "Protein powder scoop (whey)", "calories": 120, "protein": 24, "carbs": 3, "fat": 1.5, "tags": ["dairy", "vegetarian", "high_protein"]},
    {"name": "Pea protein scoop", "calories": 120, "protein": 24, "carbs": 2, "fat": 2, "tags": ["vegan", "vegetarian", "high_protein"]},
    # Carbs
    {"name": "Cooked white rice (1 cup)", "calories": 205, "protein": 4, "carbs": 45, "fat": 0.4, "tags": ["vegan", "vegetarian", "gluten_free"]},
    {"name": "Cooked brown rice (1 cup)", "calories": 215, "protein": 5, "carbs": 45, "fat": 1.6, "tags": ["vegan", "vegetarian", "gluten_free"]},
    {"name": "Oats dry (50g)", "calories": 190, "protein": 7, "carbs": 33, "fat": 3.5, "tags": ["vegan", "vegetarian", "gluten"]},
    {"name": "Whole wheat bread (2 slices)", "calories": 160, "protein": 8, "carbs": 28, "fat": 2, "tags": ["vegan", "vegetarian", "gluten"]},
    {"name": "Pasta cooked (1.5 cups)", "calories": 330, "protein": 12, "carbs": 65, "fat": 2, "tags": ["vegan", "vegetarian", "gluten"]},
    {"name": "Potato baked medium", "calories": 160, "protein": 4, "carbs": 37, "fat": 0.2, "tags": ["vegan", "vegetarian", "gluten_free"]},
    {"name": "Sweet potato medium", "calories": 100, "protein": 2, "carbs": 23, "fat": 0.2, "tags": ["vegan", "vegetarian", "gluten_free"]},
    {"name": "Quinoa cooked (1 cup)", "calories": 220, "protein": 8, "carbs": 39, "fat": 3.5, "tags": ["vegan", "vegetarian", "gluten_free"]},
    {"name": "Banana medium", "calories": 105, "protein": 1.3, "carbs": 27, "fat": 0.4, "tags": ["vegan", "vegetarian", "fruit", "gluten_free"]},
    {"name": "Apple medium", "calories": 95, "protein": 0.5, "carbs": 25, "fat": 0.3, "tags": ["vegan", "vegetarian", "fruit", "gluten_free"]},
    {"name": "Berries mixed (1 cup)", "calories": 70, "protein": 1, "carbs": 17, "fat": 0.5, "tags": ["vegan", "vegetarian", "fruit", "gluten_free"]},
    # Fats / extras
    {"name": "Avocado half", "calories": 120, "protein": 1.5, "carbs": 6, "fat": 11, "tags": ["vegan", "vegetarian", "gluten_free"]},
    {"name": "Olive oil (1 tbsp)", "calories": 120, "protein": 0, "carbs": 0, "fat": 14, "tags": ["vegan", "vegetarian", "gluten_free"]},
    {"name": "Almonds (28g)", "calories": 160, "protein": 6, "carbs": 6, "fat": 14, "tags": ["vegan", "vegetarian", "nuts", "gluten_free"]},
    {"name": "Peanut butter (2 tbsp)", "calories": 190, "protein": 8, "carbs": 7, "fat": 16, "tags": ["vegan", "vegetarian", "nuts"]},
    {"name": "Mixed salad greens + veggies", "calories": 40, "protein": 2, "carbs": 8, "fat": 0.5, "tags": ["vegan", "vegetarian", "veg", "gluten_free"]},
    {"name": "Broccoli steamed (1 cup)", "calories": 55, "protein": 4, "carbs": 11, "fat": 0.6, "tags": ["vegan", "vegetarian", "veg", "gluten_free"]},
    {"name": "Stir-fry mixed vegetables", "calories": 80, "protein": 3, "carbs": 14, "fat": 2, "tags": ["vegan", "vegetarian", "veg", "gluten_free"]},
    # Convenience / meals-ish
    {"name": "Hummus (4 tbsp)", "calories": 140, "protein": 4, "carbs": 12, "fat": 8, "tags": ["vegan", "vegetarian"]},
    {"name": "Whole grain wrap", "calories": 150, "protein": 5, "carbs": 26, "fat": 3, "tags": ["vegan", "vegetarian", "gluten"]},
    {"name": "Rice cakes (2)", "calories": 70, "protein": 1.5, "carbs": 15, "fat": 0.5, "tags": ["vegan", "vegetarian", "gluten_free"]},
    {"name": "Dark chocolate (20g)", "calories": 110, "protein": 1.5, "carbs": 10, "fat": 7, "tags": ["vegetarian"]},
    {"name": "Whey yogurt parfait + berries", "calories": 220, "protein": 18, "carbs": 28, "fat": 4, "tags": ["dairy", "vegetarian", "high_protein"]},
]
