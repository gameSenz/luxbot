import os
import requests
import stripe
from flask import Flask, render_template, redirect, url_for, request, abort
from dotenv import load_dotenv

load_dotenv()

stripe.api_key = os.getenv('STRIPE_SECRET_KEY')
stripe_webhook_key = os.getenv('STRIPE_WEBHOOK_SECRET')
price_id = 'price_1SiSKw1JlFuoKmRQmzTACToY'

app = Flask(__name__)

import os
print("✅ RUNNING FILE:", os.path.abspath(__file__))

print("✅ LOADED UPDATED app.py WITH /ping")


@app.route("/ping", methods=["GET"])
def ping():
    return "pong", 200

@app.route('/create-checkout', methods=['POST'])
def create_checkout():
    data = request.get_json(silent=True) or {}
    discord_id = data['discord_id']
    if not discord_id:
        return abort(400, description="Discord ID not provided")

    session = stripe.checkout.Session.create(
        line_items=[{"price": price_id, "quantity": 1}],
        mode='payment',
        success_url=url_for('payment_complete', _external=True),
        cancel_url = url_for('cancel', _external=True),
        metadata={'discord_id': str(discord_id)},
    )

    return {"payment_url": session.url, "session_id": session.id}, 200


@app.route('/payment-complete', methods=['GET'])
def payment_complete():
    return "Payment Complete, return to discord", 200

@app.route("/cancel", methods=["GET"])
def cancel():
    return "Payment cancelled — return to Discord.", 200

@app.route('/stripe-webhook', methods=['POST'])
def stripe_webhook():
    stripe_payload = request.get_data()
    sig_header = request.headers.get('Stripe-Signature')
    if not sig_header:
        return abort(400, description="Signature not provided")
    event = None

    try:
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

    if event['type'] == 'checkout.session.completed':
        session = event["data"]["object"]

        discord_id = session.get("metadata", {}).get("discord_id")
        if not discord_id:
            return abort(400, description="Discord ID not provided")

        bot_payload = {
            "channel_id": 1442266661737725974,
            "stat": 'points',
            "value": 10,
            "user_id": int(discord_id),
            "role_id": None
        }

        headers = {
            "Authorization": os.getenv("NEATQUEUE_KEY"),
            "Content-Type": "application/json",
            }

        response = requests.post(
            "https://api.neatqueue.com/api/v2/add/stats",
            json=bot_payload,
            headers=headers,
            timeout=10,
        )

        if response.status_code != 200:
            print("Failed to call NeatQ", response.status_code, response.text)


    return '', 200

print("✅ ROUTES:", app.url_map)

if __name__ == '__main__':
    app.run(port=5001)
