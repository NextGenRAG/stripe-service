import os
import logging
import stripe

from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from database import SessionLocal, get_db  # Ensure these point to your setup
from models import User

app = FastAPI()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Replace with your real secret keys:
STRIPE_API_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")

stripe.api_key = STRIPE_API_KEY

@app.post("/webhook")
async def stripe_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Stripe webhook endpoint that handles:
      - checkout.session.completed
      - checkout.session.async_payment_succeeded
      - invoice.payment_succeeded
      - invoice.payment_failed
      - subscription_schedule.completed
      - subscription_schedule.created
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    # 1. Verify webhook signature
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    event_type = event["type"]
    logger.info(f"Received event: {event_type}")

    # 2. Handle events
    if event_type in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
        session_object = event["data"]["object"]
        session_id = session_object.get("id")

        # Fulfill the checkout session
        success = fulfill_service(session_id, db)
        if not success:
            logger.error(f"Failed to fulfill the service for session: {session_id}")
            raise HTTPException(status_code=500, detail="Failed to fulfill the service")

    elif event_type == "invoice.payment_succeeded":
        invoice = event["data"]["object"]
        handle_invoice_payment_succeeded(invoice, db)

    elif event_type == "invoice.payment_failed":
        invoice = event["data"]["object"]
        handle_invoice_payment_failed(invoice, db)

    elif event_type == "subscription_schedule.completed":
        # If you need to do something once the schedule completes
        schedule = event["data"]["object"]
        logger.info(f"Subscription schedule completed: {schedule.get('id')}")
        # Add your logic here

    elif event_type == "subscription_schedule.created":
        # If you want to track schedule creation
        schedule = event["data"]["object"]
        logger.info(f"Subscription schedule created: {schedule.get('id')}")
        # Add your logic here

    # ... handle other events as needed

    return JSONResponse({"status": "success"})


def fulfill_service(session_id: str, db: Session) -> bool:
    """
    1) Retrieves the Checkout Session from Stripe.
    2) Confirms payment status is 'paid'.
    3) Reads user_id from session.metadata["cartID"] (since cartID == user_id).
    4) Grants user access by setting 'has_platform_access' = True.
    5) Returns True if successful; False otherwise.
    """
    try:
        session = stripe.checkout.Session.retrieve(session_id, expand=["line_items"])
    except Exception as e:
        logger.error(f"Error retrieving session from Stripe: {e}")
        return False

    if session.get("payment_status") != "paid":
        logger.info(f"Session {session_id} is not paid. Skipping fulfillment.")
        return False

    metadata = session.get("metadata", {})
    user_id_str = metadata.get("cartID")  # cartID = user_id in your flow
    if not user_id_str:
        logger.warning(f"No 'cartID' found for session {session_id}. Cannot fulfill.")
        return False

    try:
        user_id = int(user_id_str)
    except ValueError:
        logger.error(f"Invalid user_id (cartID) '{user_id_str}' in session {session_id}.")
        return False

    # Optional: Check if this session is already fulfilled to avoid duplication
    # if is_session_already_fulfilled(session_id):
    #     logger.info(f"Session {session_id} was already fulfilled.")
    #     return True

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        logger.warning(f"No user found with id {user_id}. Cannot grant access.")
        return False

    try:
        user.has_platform_access = True
        db.commit()
        logger.info(f"User {user_id} granted access for session {session_id}.")
        # mark_session_as_fulfilled(session_id, db)  # if tracking
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating user {user_id} access: {e}")
        return False

    return True


def handle_invoice_payment_succeeded(invoice: dict, db: Session):
    """
    Called when a recurring subscription invoice is successfully paid.
    Typically:
      - Ensure the user still has access (or re-enable if it was suspended).
      - Extend subscription logic as needed.
    """
    logger.info(f"Handling successful invoice payment: {invoice['id']}")
    
    # You may store user_id in invoice['metadata']['user_id'],
    # or use the subscription's or customer's metadata.
    # The exact approach depends on how you create subscriptions.
    user_id = extract_user_id_from_invoice(invoice)
    if not user_id:
        logger.warning(f"Could not determine user_id for invoice {invoice['id']}")
        return

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        logger.warning(f"No user found with id {user_id} for invoice {invoice['id']}")
        return

    try:
        user.has_platform_access = True
        db.commit()
        logger.info(f"User {user_id} access confirmed for invoice {invoice['id']}.")
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating user {user_id} access: {e}")


def handle_invoice_payment_failed(invoice: dict, db: Session):
    """
    Called when a recurring subscription invoice fails to be paid.
    Typically:
      - Revoke or pause the user's access if there's no grace period.
      - Send notification to user to update payment info, etc.
    """
    logger.warning(f"Handling failed invoice payment: {invoice['id']}")

    user_id = extract_user_id_from_invoice(invoice)
    if not user_id:
        logger.warning(f"Could not determine user_id for invoice {invoice['id']}")
        return

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        logger.warning(f"No user found with id {user_id} for invoice {invoice['id']}")
        return

    try:
        # Immediately revoke access (or you might have a grace period).
        user.has_platform_access = False
        db.commit()
        logger.info(f"User {user_id} access revoked for failed invoice {invoice['id']}.")
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating user {user_id} access after payment fail: {e}")


def extract_user_id_from_invoice(invoice: dict) -> int:
    """
    Extract the user_id from the invoice object, e.g. from:
      - invoice['metadata']['user_id'], or
      - invoice['subscription'] => retrieve subscription object => subscription.metadata['user_id']
      - invoice['customer'] => retrieve Customer object => customer.metadata['user_id']
    Adjust based on your subscription creation flow.
    """
    # Example approach if storing user_id in invoice metadata:
    metadata = invoice.get("metadata", {})
    user_id_str = metadata.get("user_id")  # or cartID, if you prefer
    if user_id_str:
        try:
            return int(user_id_str)
        except ValueError:
            return None

    # If not found in invoice metadata, you might do a subscription lookup:
    subscription_id = invoice.get("subscription")
    if subscription_id:
        # subscription_obj = stripe.Subscription.retrieve(subscription_id, expand=["metadata"])
        # user_id_str = subscription_obj.metadata.get("user_id")
        # ... etc.
        pass

    # If still not found, you might do a customer lookup:
    # customer_id = invoice.get("customer")
    # if customer_id:
    #     customer_obj = stripe.Customer.retrieve(customer_id, expand=["metadata"])
    #     user_id_str = customer_obj.metadata.get("user_id")
    #     ...

    return None  # Return None if you can't find a user_id


# Optional helpers for idempotent fulfillments:
def is_session_already_fulfilled(session_id: str) -> bool:
    """
    Check if this session was already fulfilled to avoid double-processing.
    Requires a 'FulfilledSessions' table or similar.
    """
    return False

def mark_session_as_fulfilled(session_id: str, db: Session):
    """
    Mark a session as fulfilled by storing it in a 'FulfilledSessions' table.
    """
    pass