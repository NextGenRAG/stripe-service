import stripe
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from database import get_db
from models import User
from config import STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET

stripe.api_key = STRIPE_SECRET_KEY

app = FastAPI()

# Fulfillment function
def fulfill_service(session_id: str, db: Session):
    try:
        # Retrieve the Stripe Checkout Session
        session = stripe.checkout.Session.retrieve(session_id, expand=["line_items"])
        if session.payment_status != "paid":
            return False  # Only fulfill if the payment was successful

        # Extract cartID (user identifier) from metadata
        cart_id = session.metadata.get("cartID")
        if not cart_id:
            raise ValueError("cartID is missing from metadata.")

        # Query the user based on cartID
        user = db.query(User).filter(User.id == int(cart_id)).first()
        if not user:
            raise ValueError(f"User with cartID {cart_id} not found.")

        # Grant access to the user
        if not user.has_access:  # Ensure idempotency
            user.has_access = True
            db.commit()

        return True
    except Exception as e:
        print(f"Error in fulfillment: {e}")
        return False