from __future__ import annotations

import hmac
import secrets
from datetime import timedelta
from hashlib import sha256

from app.config import settings
from app.models import OrderTrack, Rfq, utc_now

TRACKABLE_RFQ_STATUSES = {"ACCEPTED", "PAID", "SHIPPED", "RECEIVED"}
OTP_TTL = timedelta(hours=1)


def hash_otp(code: str) -> str:
    secret = (settings.secret_key or "demo-otp").encode("utf-8")
    return hmac.new(secret, (code or "").encode("utf-8"), sha256).hexdigest()


def otp_matches(code: str, digest: str | None) -> bool:
    if not digest:
        return False
    return hmac.compare_digest(hash_otp(code), digest)


def generate_otp() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def generate_shipment_code() -> str:
    return f"DEMO-SHP-{secrets.token_hex(4).upper()}"


def otp_is_expired(track: OrderTrack | None, now=None) -> bool:
    if track is None or track.otp_expires_at is None:
        return False
    current = now or utc_now()
    expires = track.otp_expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=current.tzinfo)
    return current > expires


def assign_otp(track: OrderTrack) -> str:
    code = generate_otp()
    now = utc_now()
    track.otp_code = code
    track.otp_hash = hash_otp(code)
    track.otp_created_at = now
    track.otp_expires_at = now + OTP_TTL
    track.otp_verified = False
    track.updated_at = now
    return code


def sync_track_from_rfq(track: OrderTrack, rfq: Rfq) -> None:
    status = rfq.status
    track.current_status = status
    if status == "PAID":
        track.payment_status = "CONFIRMED"
        track.payment_at = track.payment_at or utc_now()
    elif status == "SHIPPED":
        track.payment_status = "CONFIRMED"
        track.shipment_status = "SHIPPED"
        track.shipped_at = track.shipped_at or utc_now()
        if not track.shipment_code:
            track.shipment_code = generate_shipment_code()
        if not track.otp_hash:
            assign_otp(track)
    elif status == "RECEIVED":
        track.payment_status = "CONFIRMED"
        track.shipment_status = "SHIPPED"
        track.received_status = "RECEIVED"
        track.otp_verified = True
        track.completed = True
        now = utc_now()
        track.received_at = track.received_at or now
        track.completed_at = track.completed_at or now
    track.updated_at = utc_now()


def ensure_track(db, rfq: Rfq) -> OrderTrack | None:
    if rfq.status not in TRACKABLE_RFQ_STATUSES:
        return rfq.track
    if rfq.track is not None:
        if rfq.track.current_status != rfq.status:
            sync_track_from_rfq(rfq.track, rfq)
        return rfq.track
    track = OrderTrack(
        rfq_id=rfq.id,
        client_user_id=rfq.client_user_id,
        supplier_user_id=rfq.supplier_user_id,
        current_status="ACCEPTED",
        payment_status="PENDING",
        shipment_status="NOT_SHIPPED",
        received_status="NOT_RECEIVED",
        completed=False,
    )
    sync_track_from_rfq(track, rfq)
    db.add(track)
    db.flush()
    rfq.track = track
    return track


def tracking_payload(rfq: Rfq, viewer=None) -> dict | None:
    track = rfq.track
    if track is None:
        return None
    expired = otp_is_expired(track)
    demo_otp = None
    if (
        viewer is not None
        and getattr(viewer, "id", None) == track.client_user_id
        and track.shipment_status == "SHIPPED"
        and not track.otp_verified
        and not expired
    ):
        demo_otp = track.otp_code
    return {
        "rfq_id": rfq.id,
        "current_status": track.current_status,
        "payment_status": track.payment_status,
        "shipment_status": track.shipment_status,
        "received_status": track.received_status,
        "completed": track.completed,
        "payment_at": track.payment_at,
        "shipped_at": track.shipped_at,
        "received_at": track.received_at,
        "completed_at": track.completed_at,
        "shipment_code": track.shipment_code,
        "demo_otp": demo_otp,
        "otp_expires_at": track.otp_expires_at,
        "otp_verified": track.otp_verified,
        "otp_expired": expired and not track.otp_verified,
    }
