"""
Pydantic request/response models for AutoBid.bg backend.
Extracted from server.py to keep route handlers focused.
"""
from typing import List, Optional
from pydantic import BaseModel, Field, EmailStr


# ---------- Auth ----------
class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    name: str = Field(min_length=1, max_length=80)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: str
    email: str
    name: str
    role: str = "user"
    created_at: str


# ---------- Auctions ----------
class AuctionCreate(BaseModel):
    title: str
    make: str
    model: str
    year: int
    mileage_km: int
    fuel: str
    transmission: str
    body_type: str
    power_hp: int
    engine_cc: int
    color: str
    region: str
    city: str
    description: str
    images: List[str] = []
    images_exterior: List[str] = []
    images_wheels: List[str] = []
    images_bumper: List[str] = []
    images_interior: List[str] = []
    starting_bid_eur: float
    reserve_eur: Optional[float] = None
    duration_days: int = 10
    contact_email: EmailStr
    contact_phone: str = Field(min_length=5, max_length=32)


class BidCreate(BaseModel):
    amount_eur: float
    payment_method_id: Optional[str] = None  # mock Stripe payment method token


class BiddingCreditCreate(BaseModel):
    max_amount_eur: float = Field(gt=0)
    payment_method_id: str = Field(min_length=4)


class AdminDecision(BaseModel):
    reason: Optional[str] = None


class CommentCreate(BaseModel):
    text: str = Field(min_length=1, max_length=1200)


class AuctionUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    starting_bid_eur: Optional[float] = None
    reserve_eur: Optional[float] = None
    images: Optional[List[str]] = None
    images_exterior: Optional[List[str]] = None
    images_wheels: Optional[List[str]] = None
    images_bumper: Optional[List[str]] = None
    images_interior: Optional[List[str]] = None
    color: Optional[str] = None
    region: Optional[str] = None
    city: Optional[str] = None
    vin: Optional[str] = None


class AdminAuctionUpdate(BaseModel):
    """Full admin edit — allows changing every field on an auction."""
    title: Optional[str] = None
    description: Optional[str] = None
    make: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    mileage_km: Optional[int] = None
    fuel: Optional[str] = None
    transmission: Optional[str] = None
    body_type: Optional[str] = None
    power_hp: Optional[int] = None
    engine_cc: Optional[int] = None
    color: Optional[str] = None
    region: Optional[str] = None
    city: Optional[str] = None
    vin: Optional[str] = None
    images: Optional[List[str]] = None
    images_exterior: Optional[List[str]] = None
    images_wheels: Optional[List[str]] = None
    images_bumper: Optional[List[str]] = None
    images_interior: Optional[List[str]] = None
    starting_bid_eur: Optional[float] = None
    reserve_eur: Optional[float] = None
    current_bid_eur: Optional[float] = None
    ends_at: Optional[str] = None
    status: Optional[str] = None
    featured: Optional[bool] = None
    seller_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None


# ---------- Counter-offer / Negotiation ----------
class CounterOfferCreate(BaseModel):
    price_eur: float


class NegotiationRespond(BaseModel):
    accept: bool


class NegotiationOpening(BaseModel):
    """Seller's opening offer OR decision to pass."""
    price_eur: Optional[float] = None
    decline: bool = False


class NegotiationResponse(BaseModel):
    """Buyer's response — action = 'accept' | 'counter' | 'decline'."""
    action: str
    price_eur: Optional[float] = None


class NegotiationFinal(BaseModel):
    """Seller's final step (only if buyer countered)."""
    action: str  # "accept" | "decline"


class NegotiationMessage(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


# ---------- Users / Profile / Admin ----------
class ProfileUpdate(BaseModel):
    phone: Optional[str] = None
    sms_opt_in: Optional[bool] = None


class AdminUserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    is_verified_dealer: Optional[bool] = None
    role: Optional[str] = None  # "user" or "admin"


class SavedSearchCreate(BaseModel):
    name: str
    filters: dict


# ---------- Site Settings (CMS) ----------
class SiteSettingsUpdate(BaseModel):
    buyer_fee_pct: Optional[float] = None
    buyer_fee_min_eur: Optional[float] = None
    buyer_fee_max_eur: Optional[float] = None
    seo_title: Optional[str] = None
    seo_description: Optional[str] = None
    faq_content: Optional[str] = None
    terms_content: Optional[str] = None
    contacts_content: Optional[str] = None
    fees_content: Optional[str] = None
    how_it_works_content: Optional[str] = None
