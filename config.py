import os
from dotenv import load_dotenv

# Load environment variables from a .env file
load_dotenv()

# Stripe configuration
STRIPE_SECRET_KEY = os.getenv("sk_test_51QZ0OuIZhbjcBaqMNvXW5swrcxwuZV1fMiEhKKlbvhnZaNXp8e4uzzLz2owRvg6f7iucYCtei0KJnG6r2i12q15500MU8HeXYb")  # Your Stripe secret key
STRIPE_WEBHOOK_SECRET = os.getenv("rk_test_51QZ0OuIZhbjcBaqMtwyYuWTLjgipJUOu4U19yjbQRbPYWqx1YcC07l3yH8VQtt3JzpimrRLQi03wpQnFZ4UkQhLh001wk6PnvF")  # Your Stripe webhook secret (if applicable)

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL")  # Your database connection string

# Other application settings
ENV = os.getenv("ENV", "development")  # Environment: development, production, etc.
DEBUG = ENV == "development"  # Debug mode based on environment