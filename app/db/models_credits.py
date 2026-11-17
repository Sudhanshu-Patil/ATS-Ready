"""Credits, payments and referrals. Re-exported from app.db.models."""
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


def _now():
    return datetime.utcnow()


def _uuid():
    return uuid.uuid4()


class CreditLedger(Base):
    """Every balance change, once. idempotency_key is unique, so a retry, a double click or a replayed webhook can
    never charge or grant twice."""
    __tablename__ = "credit_ledger"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id         = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    kind            = Column(String(10), nullable=False)            # job | resume
    delta           = Column(Integer, nullable=False)
    reason          = Column(String(20), nullable=False)            # signup|purchase|referral|unlock|refund|admin|migration
    application_id  = Column(UUID(as_uuid=True), ForeignKey("applications.id", ondelete="SET NULL"), nullable=True)
    payment_id      = Column(UUID(as_uuid=True), nullable=True)
    idempotency_key = Column(String(120), unique=True, nullable=False)
    balance_after   = Column(Integer, nullable=False)
    created_at      = Column(DateTime, default=_now, nullable=False)


class Payment(Base):
    __tablename__ = "payments"

    id                  = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id             = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    provider            = Column(String(12), nullable=False)        # razorpay | paypal
    provider_order_id   = Column(String(100), unique=True, nullable=False)
    provider_payment_id = Column(String(100), unique=True, nullable=True)
    pack_id             = Column(String(20), nullable=False)
    amount_minor        = Column(Integer, nullable=False)           # paise or cents
    currency            = Column(String(3), nullable=False)
    status              = Column(String(12), default="created", nullable=False)   # created | paid | failed
    created_at          = Column(DateTime, default=_now, nullable=False)
    paid_at             = Column(DateTime, nullable=True)


class Referral(Base):
    __tablename__ = "referrals"

    id          = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    referrer_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    referee_id  = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    status      = Column(String(10), default="pending", nullable=False)       # pending | rewarded | void
    created_at  = Column(DateTime, default=_now, nullable=False)
    rewarded_at = Column(DateTime, nullable=True)
