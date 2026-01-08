import os
from datetime import timezone, datetime

from supabase import create_client, Client
from supabase.client import ClientOptions
import requests
import stripe
from flask import Flask, render_template, redirect, url_for, request, abort
from dotenv import load_dotenv

load_dotenv()

supabase_url: str = os.environ.get("SUPABASE_URL")
supabase_key: str = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(
    supabase_url,
    supabase_key,
    options=ClientOptions(
        postgrest_client_timeout=10,
        storage_client_timeout=10,
        schema="public",
    )
)

stripe.api_key = os.getenv('STRIPE_SECRET_KEY')
stripe_webhook_key = os.getenv('STRIPE_WEBHOOK_SECRET')
port=8080
tenToken_id = 'price_1SiSKw1JlFuoKmRQmzTACToY'
twentyToken_id = 'price_1SilIH1JlFuoKmRQTD9zxIX3'

token_map = {
    "ten_tokens": tenToken_id,
    "twenty_tokens": twentyToken_id,
}

price_map = {
    tenToken_id: '10',
    twentyToken_id: '20',
}
app = Flask(__name__)

import os

@app.route("/health", methods=["GET"])
def health():
    return {"ok": True}, 200

# POST request in order to generate a checkout on Stripe through Discord Bot + User ID
@app.route('/create-checkout', methods=['POST'])
def create_checkout():
    print("create checkout")
    # JSON to hold the user's Discord ID from Bot Frontend
    data = request.get_json(silent=True) or {}

    discord_id = data.get('discord_id')
    if not discord_id:
        return abort(400, description="Discord ID not provided")

    product = data.get("product")
    if not product:
        return abort(400, description="Product not provided")

    price_id = token_map.get(product)
    if not price_id:
        return abort(400, description="Invalid product")

    #Stripe Checkout Session Obj, https://docs.stripe.com/api/checkout/sessions/object
    session = stripe.checkout.Session.create(
        line_items=[{"price": price_id, "quantity": 1}],
        mode='payment',
        success_url="https://luxbot-production-0bcb.up.railway.app/payment-complete",
        cancel_url="https://luxbot-production-0bcb.up.railway.app/cancel",
        metadata={
            'discord_id': str(discord_id),
            'product': product,
            'price_id': str(price_id),
        },
    )

    return {"payment_url": session.url, "session_id": session.id}, 200

# Success Message to user
@app.route('/payment-complete', methods=['GET'])
def payment_complete():
    return "Payment Complete, return to discord", 200

# Cancellation Message to User
@app.route("/cancel", methods=["GET"])
def cancel():
    return "Payment cancelled — return to Discord.", 200

# Webhook to verify checkout is complete, and payout tokens to User
@app.route('/stripe-webhook', methods=['POST'])
def stripe_webhook():
    # payload direct from webhook
    stripe_payload = request.get_data()
    # validate signature from stripe
    sig_header = request.headers.get('Stripe-Signature')
    if not sig_header:
        return abort(400, description="Signature not provided")
    event = None

    try:
        # Constructs Stripe Event Obj ft Validation
        event = stripe.Webhook.construct_event(
            payload=stripe_payload,
            sig_header=sig_header,
            secret=stripe_webhook_key
        )
    except ValueError as e:
        # Invalid payload
        print('Error parsing payload: {}'.format(str(e)))
        return abort(400, description="Invalid Payload")
    except stripe.error.SignatureVerificationError as e:
        # Invalid signature
        print('Error verifying webhook signature: {}'.format(str(e)))
        return abort(400, description="Invalid Signature")

    # Ensures that event received is a complete checkout session
    if event['type'] == 'checkout.session.completed':
        # Data has info on the session obj
        # https://docs.stripe.com/api/checkout/sessions/object
        session = event["data"]["object"]

        # Gets discord ID through metadata created with checkout session
        discord_id = session.get("metadata", {}).get("discord_id")
        if not discord_id:
            return abort(400, description="Discord ID not provided")
        # grabs price_id for interaction with dict
        price_id = session.get("metadata", {}).get("price_id")
        # product name for database purposes
        product = session.get("metadata", {}).get("product")
        # grabs unix timestamp from stripe, converts to UTC
        creation_unix = session.get("created")
        creation_date = datetime.fromtimestamp(creation_unix, tz=timezone.utc)
        # subtotal for validation
        subtotal = session.get("amount_subtotal")
        # unique checkout session id
        checkout_id = session.get("id")
        # receipt url
        receipt_url = None

        # tries to find receipt url
        try:
            pi_id = session.get("payment_intent")
            if pi_id:
                payment_intent = stripe.PaymentIntent.retrieve(pi_id)
                latest_charge_id = payment_intent.get("latest_charge")
                if latest_charge_id:
                    charge = stripe.Charge.retrieve(latest_charge_id)
                    receipt_url = charge.get("receipt_url")
        except Exception as e:
            print("Couldn't fetch receipt url", e)

        try:
            supabase.table("Order_History").insert({
                     "discord_id": discord_id,
                     "created_at": creation_date.isoformat(),
                     "product": product,
                     "checkout_id": checkout_id,
                     "subtotal": subtotal,
                     "receipt_url": receipt_url,
                     "notified": False,
            }).execute()
        # Checks for duplicate stripe webhooks
        except Exception as e:
            print("Duplicate webhook",checkout_id, e)
            return "",200
        # NeatQ API Integration to adjust user's points (aka Tokens)
        # https://api.neatqueue.com/docs#/Commands/add_stats_api_v2_add_stats_post
        # Generating JSON to send to API
        bot_payload = {
            "channel_id": 1442266661737725974,
            "stat": 'points',
            "value": int(price_map[price_id]),
            "user_id": int(discord_id),
            "role_id": None
        }
        # Authenticating API Key + Declaring JSON to be sent
        headers = {
            "Authorization": os.getenv("NEATQUEUE_KEY"),
            "Content-Type": "application/json",
            }
        # send a POST req to NeatQ to process point change
        response = requests.post(
            "https://api.neatqueue.com/api/v2/add/stats",
            json=bot_payload,
            headers=headers,
            timeout=10,
        )

        # applies payout, or advises user if NeatQ is having issues
        if response.status_code != 200:
            print("Failed to call NeatQ, Contact an Admin to receive tokens", response.status_code, response.text)
        else:
            supabase.table("Order_History") \
            .update({"payout": True}) \
            .eq("checkout_id", checkout_id) \
            .execute()


    return '', 200

@app.route("/checkout-status/<checkout_id>", methods=["GET"])
def checkout_status(checkout_id):
    secret_key = request.args.get("secret_key")
    if not secret_key or secret_key != os.getenv("POLL_SECRET"):
        return abort(401, description="Secret key not provided")

    res = (
        supabase.table("Order_History")
        .select("checkout_id,payout,product,receipt_url")
        .eq("checkout_id", checkout_id)
        .limit(1)
        .execute()
    )
    rows = getattr(res, "data", None) or []
    if not rows:
        return {"found": False}, 200

    row = rows[0]
    return {
        "found": True,
        "payout": bool(row.get("payout")),
        "product": row.get("product"),
        "receipt_url": row.get("receipt_url"),
    }

@app.route("/notified", methods=["POST"])
def notified():
    data = request.get_json(silent=True) or {}
    secret_key = data.get("secret_key")
    if not secret_key or secret_key != os.getenv("POLL_SECRET"):
        return abort(401, description="Secret key not provided")

    checkout_id = data.get("checkout_id")
    if not checkout_id:
        return abort(400, description="Checkout id not provided")

    (supabase.table("Order_History").update({"notified": True})
     .eq("checkout_id", checkout_id)
     .execute())
    return '', 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv("PORT", default=8080)))
