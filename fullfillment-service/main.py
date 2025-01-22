import os
import logging
import stripe
from fastapi import FastAPI, Request, HTTPException
from starlette.background import BackgroundTasks
from sqlalchemy.orm import Session
from database import SessionLocal  # Your SQLAlchemy Session
from models import User  # The updated User model

# Configure logging (Production-level practice)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Initialize Stripe keys
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
endpoint_secret = os.getenv("STRIPE_ENDPOINT_SECRET")

# 1) Change webhook path to "/webhooks/stripe"
@app.post("/webhooks/stripe")
async def stripe_webhook(request: Request, background_tasks: BackgroundTasks):
    """Stripe webhook endpoint to handle Checkout Session events and subscription renewals."""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    # Verify the webhook signature
    try:
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=sig_header,
            secret=endpoint_secret
        )
    except ValueError:
        # Invalid payload
        logger.error("Invalid payload received from Stripe.")
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        # Invalid signature
        logger.error("Invalid signature detected for Stripe webhook.")
        raise HTTPException(status_code=400, detail="Invalid signature")

    # 2) Handle events relevant to subscription checkout & renewals:
    #    - checkout.session.completed (initial subscription checkout)
    #    - checkout.session.async_payment_succeeded (async payment methods)
    #    - invoice.payment_succeeded (renewal payments)
    #    - invoice.payment_failed (subscription renewal failure)
    #    ... add more as needed (customer.subscription.deleted, etc.)

    event_type = event["type"]

    if event_type in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
        session_object = event["data"]["object"]
        session_id = session_object["id"]

        # Fulfill the order in the background
        background_tasks.add_task(fulfill_order, session_id)

    elif event_type == "invoice.payment_succeeded":
        # This indicates a recurring subscription payment succeeded
        invoice = event["data"]["object"]
        background_tasks.add_task(handle_subscription_renewal, invoice)

    elif event_type == "invoice.payment_failed":
        # Payment failed for a subscription renewal
        invoice = event["data"]["object"]
        background_tasks.add_task(handle_failed_payment, invoice)

    # ... handle other events as needed

    return {"status": "success"}

def fulfill_order(session_id: str):
    """
    Fulfillment function that:
      1) Retrieves the session from Stripe (expanding line_items).
      2) Confirms payment status.
      3) Looks for user_id in session.metadata["cartID"] (equal to user_id).
      4) Grants access by updating the 'has_platform_access' column.
      5) Records fulfillment to avoid double-processing.
    """
    try:
        # Fetch the session from Stripe, expand line_items if needed
        session = stripe.checkout.Session.retrieve(session_id, expand=["line_items"])
    except Exception as e:
        logger.error(f"Error retrieving session from Stripe: {e}")
        return  # Early return, can't proceed

    # Check payment status
    if session.get("payment_status") != "paid":
        logger.info(f"Session {session_id} not paid. Skipping fulfillment.")
        return

    # Retrieve user_id from session metadata
    metadata = session.get("metadata", {})
    user_id = metadata.get("cartID")  # cartID == user_id in your use case
    if not user_id:
        logger.warning(f"Session {session_id} has no 'cartID' in metadata. Cannot fulfill.")
        return

    # Convert to int if needed
    try:
        user_id = int(user_id)
    except ValueError:
        logger.error(f"cartID={user_id} is not a valid integer. Cannot fulfill.")
        return

    # 2) Check if already fulfilled
    if is_session_already_fulfilled(session_id):
        logger.info(f"Session {session_id} already fulfilled. Skipping.")
        return

    # 3) Open a DB session & update the user's access
    db: Session = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            user.has_platform_access = True
            db.add(user)
            db.commit()

            # Mark the session as fulfilled (if you're tracking that)
            mark_session_as_fulfilled(session_id, db=db)
            logger.info(f"User {user_id} granted platform access for session {session_id}.")
        else:
            logger.warning(f"No user found with id {user_id}. Cannot grant access.")
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating user access for user {user_id}: {e}")
    finally:
        db.close()

def handle_subscription_renewal(invoice: dict):
    """
    Called when a subscription invoice is successfully paid (invoice.payment_succeeded).
    Typically used to confirm ongoing access or re-grant access if it was suspended.
    """
    # 'invoice' is the Stripe invoice object
    # If you stored the user_id in the 'subscription' or 'customer' metadata,
    # you can retrieve and update access or track usage.
    # For example, invoice["subscription"], invoice["customer"] might lead to
    # retrieving the user. This may vary based on how you set your subscription up.

    # Here’s a simple placeholder that logs successful renewals.
    logger.info(f"Invoice {invoice['id']} for subscription {invoice['subscription']} succeeded.")
    # Add logic for re-extending subscription access if needed.

def handle_failed_payment(invoice: dict):
    """
    Called when a subscription invoice payment fails (invoice.payment_failed).
    Typically you might mark the account as past due or email the user.
    """
    logger.warning(f"Invoice {invoice['id']} for subscription {invoice['subscription']} failed.")
    # Add logic for restricting access or notifying user, etc.

def is_session_already_fulfilled(session_id: str) -> bool:
    """
    Placeholder to avoid fulfilling the same session multiple times.
    Typically, you'd query a separate table that stores fulfilled session IDs.
    """
    # e.g. query the 'FulfilledSessions' table
    return False

def mark_session_as_fulfilled(session_id: str, db: Session):
    """
    Placeholder for storing session_id in a 'FulfilledSessions' table
    so you don't fulfill the same session twice.
    """
    # Insert into FulfilledSessions table, e.g.:
    # new_record = FulfilledSession(session_id=session_id)
    # db.add(new_record)
    # db.commit()
    pass