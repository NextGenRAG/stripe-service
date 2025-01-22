from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from models import User
import stripe
from config import STRIPE_SECRET_KEY  # Ensure you have this in your config

stripe.api_key = STRIPE_SECRET_KEY  # Set your Stripe secret key

app = FastAPI()

# Define subscription price IDs (replace these with actual Stripe price IDs)
PRICE_IDS = {
    "bronze": "price_1QhzfBIZhbjcBaqMHUSuptHA",  # Replace with your Bronze price ID
    "silver": "price_1QhzfAIZhbjcBaqMSilverXXX",  # Replace with your Silver price ID
    "gold": "price_1QhzfAIZhbjcBaqMGoldXXX",      # Replace with your Gold price ID
}

class PaymentLinkRequest(BaseModel):
    user_id: int
    plan: str  # Expected values: "bronze", "silver", "gold"

@app.post("/create-payment-link")
async def create_payment_link(request: PaymentLinkRequest, db: Session = Depends(get_db)):
    """
    Creates a payment link for a customer based on the subscription plan.
    """
    # Validate the user in the database
    user = db.query(User).filter(User.id == request.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Validate the subscription plan
    if request.plan not in PRICE_IDS:
        raise HTTPException(status_code=400, detail="Invalid subscription plan")

    try:
        # Create a payment link using Stripe API
        payment_link = stripe.PaymentLink.create(
            line_items=[
                {
                    "price": PRICE_IDS[request.plan],  # Get the Stripe price ID
                    "quantity": 1,
                },
            ],
            metadata={"cartID": str(request.user_id)},  # Attach the user ID as cartID
            after_completion={
                "type": "hosted_confirmation",
                "hosted_confirmation": {
                    "custom_message": f"Thank you for subscribing to the {request.plan.capitalize()} plan!"
                }
            },
        )
        return {"payment_link_url": payment_link.url}  # Return the link to the frontend
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create payment link: {e}")