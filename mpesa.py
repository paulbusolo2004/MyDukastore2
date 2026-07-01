import requests
import base64
from datetime import datetime

# ==================================
# DARAJA SANDBOX CREDENTIALS
# ==================================

CONSUMER_KEY = "qvYa71MgrkNRwXtGt27XgvLcXTOYJKAYQKmImrikckjMXNUd"
CONSUMER_SECRET = "PkhJbIzUCQopAexE5yYzdexRTP9jFWD8mafSeZ86j4iGi9RMdzxnB36KQ8WSJ0eT"

BUSINESS_SHORT_CODE = "174379"

PASSKEY = "bfb279f9aa9bdbcf158e97dd71a467cd2e0c893059b10f78e6b72ada1ed2c919"

# ==================================
# GET ACCESS TOKEN
# ==================================

def get_access_token():

    url = (
        "https://sandbox.safaricom.co.ke/"
        "oauth/v1/generate?grant_type=client_credentials"
    )

    try:

        response = requests.get(
            url,
            auth=(CONSUMER_KEY, CONSUMER_SECRET)
        )

        print("TOKEN STATUS:", response.status_code)
        print("TOKEN RESPONSE:", response.text)

        response.raise_for_status()

        return response.json()["access_token"]

    except Exception as e:

        print("ACCESS TOKEN ERROR:", str(e))

        raise


# ==================================
# SEND STK PUSH
# ==================================

def stk_push(phone, amount):

    access_token = get_access_token()

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")

    password = base64.b64encode(
        (
            BUSINESS_SHORT_CODE +
            PASSKEY +
            timestamp
        ).encode()
    ).decode()

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    payload = {
        "BusinessShortCode": BUSINESS_SHORT_CODE,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": int(amount),
        "PartyA": phone,
        "PartyB": BUSINESS_SHORT_CODE,
        "PhoneNumber": phone,

        # Temporary callback for testing
        "CallBackURL": "https://abc123.ngrok-free.app/mpesa-callback",

        "AccountReference": "Ecommerce",
        "TransactionDesc": "Order Payment"
    }

    try:

        response = requests.post(
            "https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest",
            json=payload,
            headers=headers
        )

        print("STK STATUS:", response.status_code)
        print("STK RESPONSE:", response.text)

        return response.json()

    except Exception as e:

        print("STK PUSH ERROR:", str(e))

        return {
            "error": str(e)
        }