import os
import requests
import stripe
from flask import Flask, render_template, redirect, url_for, request, abort
from dotenv import load_dotenv

load_dotenv()

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
        success_url=url_for('payment_complete', _external=True),
        cancel_url = url_for('cancel', _external=True),
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

        if response.status_code != 200:
            print("Failed to call NeatQ", response.status_code, response.text)


    return '', 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv("PORT", default=8080)))
