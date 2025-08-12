import smtplib
from email.message import EmailMessage

SMTP_HOST = "smtp-relay.gmail.com"
SMTP_PORT = 587

msg = EmailMessage()
msg["From"] = "ops@yourdomain.com"
msg["To"] = "you@example.com"
msg["Subject"] = "Alert"
msg.set_content("Camera cam01 unreachable")

with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
    s.starttls()
    # If your relay is IP-allowed, no login required; else use SMTP auth per your policy
    s.send_message(msg)
