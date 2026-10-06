"""The "your results are ready" email for a customer free check.

Sent once, by the worker, straight after a check's results are saved. It is transactional: it tells
the owner that the thing they asked for is ready, and nothing else. It carries the headline count and
a link back to the results page; it never includes raw answers, other owners' data or a sales pitch.

Sending needs RESEND_API_KEY and FREE_CHECK_EMAIL_FROM (an address on a domain verified in Resend).
Without both, nothing is sent and the check is unaffected.
"""
from __future__ import annotations

import html
import json
import logging
import urllib.error
import urllib.request
from typing import Any

log = logging.getLogger("free_check_email")

RESEND_URL = "https://api.resend.com/emails"
DEFAULT_SITE_URL = "https://foundinbrighton.ai"


def email_settings(environ) -> dict[str, str] | None:
    api_key = str(environ.get("RESEND_API_KEY") or "").strip()
    sender = str(environ.get("FREE_CHECK_EMAIL_FROM") or "").strip()
    if not api_key or not sender:
        return None
    site = str(environ.get("FREE_CHECK_SITE_URL") or DEFAULT_SITE_URL).strip().rstrip("/")
    return {"api_key": api_key, "sender": sender, "site_url": site}


def build_results_email(*, business_name: str, projection: dict[str, Any], site_url: str) -> dict[str, str]:
    """Subject, plain text and HTML. Every figure comes from the saved projection."""
    name = " ".join(str(business_name).split())[:120]
    valid = int(projection["valid_answers"])
    expected = int(projection["expected_answers"])
    recommended = int(projection["target"]["recommended_answers"])
    link = f"{site_url}/visibility-check"
    if recommended:
        headline = f"{name} was recommended in {recommended} of {valid} answers."
    else:
        headline = f"{name} was not recommended in the {valid} completed answers."
    partial = (f" {expected - valid} of {expected} answers could not be collected and are left out."
               if valid < expected else "")
    context = ("That is a snapshot of five customer questions put to three AI providers on one day, "
               "not a measure of every search." + partial)
    how = ("Open the link and sign in with this email address. We will send you a fresh sign-in link; "
           "there is no password.")
    text = "\n\n".join([
        "Your free AI visibility check is ready.",
        headline,
        context,
        f"See who was recommended, by provider and by question:\n{link}",
        how,
        "You are receiving this because you ran a free visibility check with this email address. "
        "We do not send marketing emails.",
        "Found.in.Brighton",
    ])
    safe = html.escape
    body = f"""<div style="background:#f5f2e9;padding:32px 16px;font-family:Arial,Helvetica,sans-serif;color:#203c33;">
  <div style="max-width:520px;margin:0 auto;background:#fffdf8;border:1px solid #cbd1c3;border-radius:12px;padding:32px;">
    <p style="margin:0 0 24px;font-size:20px;font-weight:bold;color:#244b3b;">Found.in.Brighton</p>
    <h1 style="margin:0 0 16px;font-size:24px;line-height:1.3;color:#203c33;">Your visibility check is ready</h1>
    <p style="margin:0 0 16px;font-size:18px;line-height:1.5;color:#203c33;"><strong>{safe(headline)}</strong></p>
    <p style="margin:0 0 24px;font-size:16px;line-height:1.6;color:#4d5f56;">{safe(context)}</p>
    <p style="margin:0 0 24px;">
      <a href="{safe(link, quote=True)}" style="display:inline-block;background:#244b3b;color:#ffffff;text-decoration:none;font-size:16px;font-weight:bold;padding:14px 24px;border-radius:8px;">See my results</a>
    </p>
    <p style="margin:0;font-size:14px;line-height:1.6;color:#4d5f56;">{safe(how)}</p>
  </div>
  <p style="max-width:520px;margin:16px auto 0;font-size:12px;line-height:1.6;color:#4d5f56;text-align:center;">
    You are receiving this because you ran a free visibility check with this email address. We do not send marketing emails.
  </p>
</div>"""
    return {"subject": f"Your AI visibility check for {name} is ready", "text": text, "html": body}


def send_results_email(*, to: str, business_name: str, projection: dict[str, Any],
                       settings: dict[str, str], opener=urllib.request.urlopen) -> bool:
    """Send through Resend. Returns whether it was accepted; never raises, never logs the address."""
    message = build_results_email(business_name=business_name, projection=projection,
                                  site_url=settings["site_url"])
    request = urllib.request.Request(
        RESEND_URL, method="POST",
        data=json.dumps({"from": settings["sender"], "to": [to], **message}).encode(),
        headers={"Authorization": f"Bearer {settings['api_key']}", "Content-Type": "application/json"})
    try:
        with opener(request, timeout=15) as response:
            return 200 <= response.status < 300
    except urllib.error.HTTPError as error:
        log.warning("Results email was rejected (HTTP %s)", error.code)
    except Exception as error:  # A failed notification must never fail a completed check.
        log.warning("Results email could not be sent (%s)", type(error).__name__)
    return False
