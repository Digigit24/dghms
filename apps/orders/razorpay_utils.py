"""
Razorpay Integration Utilities

Handles Razorpay payment gateway integration including:
- Order creation
- Payment verification
- Webhook signature verification
"""
import razorpay
import hmac
import hashlib
from decimal import Decimal
from .models import RazorpayConfig


class RazorpayClient:
    """
    Wrapper class for Razorpay client operations

    Provides methods for creating orders, verifying payments, and handling webhooks.
    Uses tenant-specific configuration from RazorpayConfig model.
    """

    def __init__(self, tenant_id):
        """
        Initialize Razorpay client for specific tenant

        Args:
            tenant_id (UUID): Tenant UUID

        Raises:
            ValueError: If Razorpay not configured for tenant
        """
        try:
            config = RazorpayConfig.objects.get(
                tenant_id=tenant_id,
                is_active=True
            )
            self.client = razorpay.Client(
                auth=(config.razorpay_key_id, config.razorpay_key_secret)
            )
            self.config = config
            self.webhook_secret = config.razorpay_webhook_secret
            self.auto_capture = config.auto_capture
        except RazorpayConfig.DoesNotExist:
            raise ValueError(f"Razorpay not configured for tenant {tenant_id}")

    def create_order(self, amount, currency='INR', receipt=None, notes=None):
        """
        Create Razorpay order

        Args:
            amount (Decimal): Amount in rupees (will be converted to paise)
            currency (str): Currency code (default: INR)
            receipt (str): Order receipt/reference
            notes (dict): Additional metadata

        Returns:
            dict: Razorpay order response containing:
                - id: Razorpay order ID
                - entity: 'order'
                - amount: Amount in paise
                - currency: Currency code
                - receipt: Receipt number
                - status: 'created'
                - created_at: Timestamp

        Raises:
            razorpay.errors.BadRequestError: Invalid request parameters
            razorpay.errors.ServerError: Razorpay server error
        """
        # Convert amount to paise (Razorpay uses smallest currency unit)
        amount_paise = int(Decimal(str(amount)) * 100)

        order_data = {
            'amount': amount_paise,
            'currency': currency,
            'receipt': receipt or '',
            'payment_capture': 1 if self.auto_capture else 0
        }

        if notes:
            order_data['notes'] = notes

        return self.client.order.create(data=order_data)

    def verify_payment_signature(self, razorpay_order_id, razorpay_payment_id, razorpay_signature):
        """
        Verify Razorpay payment signature

        This method verifies that the payment response is authentic and not tampered with.

        Args:
            razorpay_order_id (str): Order ID from Razorpay
            razorpay_payment_id (str): Payment ID from Razorpay
            razorpay_signature (str): Signature from Razorpay

        Returns:
            bool: True if signature is valid, False otherwise
        """
        try:
            params_dict = {
                'razorpay_order_id': razorpay_order_id,
                'razorpay_payment_id': razorpay_payment_id,
                'razorpay_signature': razorpay_signature
            }
            self.client.utility.verify_payment_signature(params_dict)
            return True
        except razorpay.errors.SignatureVerificationError:
            return False

    def verify_webhook_signature(self, payload, signature):
        """
        Verify webhook signature from Razorpay

        Webhooks are authenticated using HMAC-SHA256 signature.
        This ensures the webhook is genuinely from Razorpay.

        Args:
            payload (bytes): Raw webhook payload
            signature (str): X-Razorpay-Signature header value

        Returns:
            bool: True if signature is valid, False otherwise
        """
        expected_signature = hmac.new(
            self.webhook_secret.encode('utf-8'),
            payload,
            hashlib.sha256
        ).hexdigest()

        # Use constant-time comparison to prevent timing attacks
        return hmac.compare_digest(expected_signature, signature)

    def fetch_payment(self, payment_id):
        """
        Fetch payment details from Razorpay

        Args:
            payment_id (str): Razorpay payment ID

        Returns:
            dict: Payment details including status, amount, method, etc.
        """
        return self.client.payment.fetch(payment_id)

    def fetch_order(self, order_id):
        """
        Fetch order details from Razorpay

        Args:
            order_id (str): Razorpay order ID

        Returns:
            dict: Order details including status, amount, payments, etc.
        """
        return self.client.order.fetch(order_id)

    def fetch_all_payments_for_order(self, order_id):
        """
        Fetch all payment attempts for an order

        Args:
            order_id (str): Razorpay order ID

        Returns:
            dict: List of payment attempts
        """
        return self.client.order.payments(order_id)

    def get_public_key(self):
        """
        Get Razorpay public key ID for frontend integration

        Returns:
            str: Razorpay Key ID (safe to expose to frontend)
        """
        return self.config.razorpay_key_id
