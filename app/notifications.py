from app.models import utc_now


MAX_ATTEMPTS = 3


class NotificationDeliveryError(Exception):
    pass


def deliver(channel, recipient):
    """Provider boundary. Replace this adapter with SES, SNS or a webhook client."""
    if channel == "email" and "@" not in recipient:
        raise NotificationDeliveryError("Invalid email recipient")
    if channel == "webhook" and not recipient.startswith(("http://", "https://")):
        raise NotificationDeliveryError("Invalid webhook URL")
    if channel not in {"email", "sms", "webhook"}:
        raise NotificationDeliveryError("Unsupported notification channel")
    if "fail.test" in recipient:
        raise NotificationDeliveryError("Notification provider unavailable")


def attempt_delivery(notification):
    if notification.status == "sent":
        return notification
    if notification.attempts >= MAX_ATTEMPTS:
        raise NotificationDeliveryError("Maximum delivery attempts reached")

    notification.attempts += 1
    try:
        deliver(notification.channel, notification.recipient)
    except NotificationDeliveryError as error:
        notification.status = "failed"
        notification.last_error = str(error)
    else:
        notification.status = "sent"
        notification.last_error = None
        notification.sent_at = utc_now()
    return notification
