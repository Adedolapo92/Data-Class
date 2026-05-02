#!/usr/bin/env python3
"""Quick SMTP test — run this to verify email is working before the full pipeline."""

import smtplib
import sys
from email.mime.text import MIMEText

import yaml


def test_email():
    with open("config.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    e = cfg["email"]
    host = e["smtp_host"]
    port = e["smtp_port"]
    username = e["username"]
    password = e["password"]
    to_addr = e["to_addr"]

    print(f"Connecting to {host}:{port} ...")
    print(f"Logging in as {username} ...")
    print(f"Sending test email to {to_addr} ...")

    msg = MIMEText("If you're reading this, your job search pipeline email is working!", "plain", "utf-8")
    msg["Subject"] = "[Job Pipeline] SMTP test — it works!"
    msg["From"] = username
    msg["To"] = to_addr

    try:
        with smtplib.SMTP(host, port, timeout=30) as server:
            server.set_debuglevel(1)   # prints every SMTP command
            server.starttls()
            server.login(username, password)
            server.sendmail(username, to_addr, msg.as_string())
        print("\n✓ Email sent successfully — check your inbox.")
    except smtplib.SMTPAuthenticationError:
        print("\n✗ Authentication failed.")
        print("  → Make sure you're using a Gmail App Password (not your login password).")
        print("  → Generate one at: myaccount.google.com/apppasswords")
        sys.exit(1)
    except smtplib.SMTPException as e:
        print(f"\n✗ SMTP error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    test_email()
