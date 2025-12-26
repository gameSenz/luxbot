import os

import stripe
from flask import Flask, render_template, redirect, url_for, request
from dotenv import load_dotenv

load_dotenv()

stripe.api_key = os.getenv('STRIPE_SECRET_KEY')

app = Flask(__name__)

@app.route('/', methods=['GET', 'POST'])
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

if __name__ == '__main__':
    app.run()
