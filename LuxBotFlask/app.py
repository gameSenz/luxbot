import os
import requests
import stripe
from flask import Flask, render_template, redirect, url_for, request, abort
from dotenv import load_dotenv

load_dotenv()

stripe.api_key = os.getenv('STRIPE_SECRET_KEY')
stripe_webhook_key = os.getenv('STRIPE_WEBHOOK_SECRET')

app = Flask(__name__)

@app.route('/', methods=['POST'])
def index():
    if request.method == 'POST':
        price_id = 'price_1SiSKw1JlFuoKmRQmzTACToY'

        price_obj = stripe.Price.retrieve(price_id)

        checkout_session = stripe.checkout.Session.create(
            line_items =
            [
                {
                'price': price_id,
                'quantity': 1,
                }
            ],
            mode='payment',
            success_url= url_for('success', _external=True) + '?session_id={CHECKOUT_SESSION_ID}',
            cancel_url = url_for('success', _external=True)
        )

        return redirect(checkout_session.url, code=303)

    return render_template('index.html')

@app.route('/success')
def success():
    session_id = request.args.get('session_id')

    session = stripe.checkout.Session.retrieve(session_id)

    if session.payment_status == 'paid':
        return f'Successfully paid! Session ID: {session_id}'
    else:
        return redirect(url_for('cancel'))

@app.route('/cancel')
def cancel():
    return 'Payment Cancelled'

@app.route('/stripe-webhook', methods=['POST'])
def stripe_webhook(request):
    payload = request.body
    sig_header = request.META['HTTP_STRIPE_SIGNATURE']
    event = None

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, stripe_webhook_key
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
#         send token
if __name__ == '__main__':
    app.run()
