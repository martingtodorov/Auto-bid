"""
Pydantic request/response models for autoandbid.com backend.
Extracted from server.py to keep route handlers focused.
"""
from typing import List, Optional
from pydantic import BaseModel, Field, EmailStr


# ---------- Auth ----------
class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    name: str = Field(min_length=1, max_length=80)
    terms_accepted: bool = Field(default=False)
    terms_version: Optional[str] = Field(default="v1", max_length=20)


class UserLogin(BaseModel):
    email: EmailStr
    password: str
    remember: Optional[bool] = False


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
    region: Optional[str] = None
    city: str
    country: Optional[str] = "Bulgaria"
    description: str
    images: List[str] = []
    images_exterior: List[str] = []
    images_wheels: List[str] = []
    images_bumper: List[str] = []
    images_interior: List[str] = []
    starting_bid_eur: float
    reserve_eur: Optional[float] = None
    no_reserve: Optional[bool] = False
    buy_now_eur: Optional[float] = None  # Optional "Buy it now" price (net, without VAT)
    vat_status: Optional[str] = None  # "exempt" | "vat_inclusive"
    vat_rate_pct: Optional[float] = None  # e.g. 20.0 — used when vat_status == "vat_inclusive"
    price_net_eur: Optional[float] = None  # legacy, kept for back-compat
    price_gross_eur: Optional[float] = None  # legacy, kept for back-compat
    duration_days: int = 10
    contact_email: EmailStr
    contact_phone: str = Field(min_length=5, max_length=32)
    vin: str = Field(min_length=11, max_length=17)  # VIN — required for every listing


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
    no_reserve: Optional[bool] = None
    buy_now_eur: Optional[float] = None
    vat_status: Optional[str] = None
    vat_rate_pct: Optional[float] = None
    price_net_eur: Optional[float] = None
    price_gross_eur: Optional[float] = None
    images: Optional[List[str]] = None
    images_exterior: Optional[List[str]] = None
    images_wheels: Optional[List[str]] = None
    images_bumper: Optional[List[str]] = None
    images_interior: Optional[List[str]] = None
    color: Optional[str] = None
    region: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
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
    country: Optional[str] = None
    vin: Optional[str] = None
    images: Optional[List[str]] = None
    images_exterior: Optional[List[str]] = None
    images_wheels: Optional[List[str]] = None
    images_bumper: Optional[List[str]] = None
    images_interior: Optional[List[str]] = None
    starting_bid_eur: Optional[float] = None
    reserve_eur: Optional[float] = None
    no_reserve: Optional[bool] = None
    buy_now_eur: Optional[float] = None
    vat_status: Optional[str] = None
    vat_rate_pct: Optional[float] = None
    price_net_eur: Optional[float] = None
    price_gross_eur: Optional[float] = None
    current_bid_eur: Optional[float] = None
    starts_at: Optional[str] = None
    ends_at: Optional[str] = None
    status: Optional[str] = None
    featured: Optional[bool] = None
    is_archived: Optional[bool] = None
    seller_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    # Manual translations of `description` for RO/EN sites — set by admin only.
    # When non-empty, these override the auto-translation in `/auctions/{id}/description?lang=ro|en`.
    description_ro: Optional[str] = None
    description_en: Optional[str] = None


# ---------- Admin actions ----------
class CancelReason(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class MakeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=60)


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
    og_image_url: Optional[str] = None            # Phase 5: homepage OG image
    favicon_url: Optional[str] = None             # Site favicon (link rel=icon)
    maintenance_mode: Optional[bool] = None       # Phase 5: maintenance toggle
    maintenance_message: Optional[str] = None
    seo_title: Optional[str] = None
    seo_description: Optional[str] = None
    seo_title_bg: Optional[str] = None
    seo_title_ro: Optional[str] = None
    seo_title_en: Optional[str] = None
    seo_description_bg: Optional[str] = None
    seo_description_ro: Optional[str] = None
    seo_description_en: Optional[str] = None
    google_site_verification: Optional[str] = None
    bing_site_verification: Optional[str] = None
    google_analytics_id: Optional[str] = None
    faq_content: Optional[str] = None
    terms_content: Optional[str] = None
    contacts_content: Optional[str] = None
    fees_content: Optional[str] = None
    how_it_works_content: Optional[str] = None
    # Phase 7 — multi-lang CMS (fallback to non-suffixed for BG)
    faq_content_bg: Optional[str] = None
    faq_content_ro: Optional[str] = None
    faq_content_en: Optional[str] = None
    terms_content_bg: Optional[str] = None
    terms_content_ro: Optional[str] = None
    terms_content_en: Optional[str] = None
    contacts_content_bg: Optional[str] = None
    contacts_content_ro: Optional[str] = None
    contacts_content_en: Optional[str] = None
    fees_content_bg: Optional[str] = None
    fees_content_ro: Optional[str] = None
    fees_content_en: Optional[str] = None
    how_it_works_content_bg: Optional[str] = None
    how_it_works_content_ro: Optional[str] = None
    how_it_works_content_en: Optional[str] = None
    # Direct-HTML CMS варианти — имат приоритет над Markdown при render
    faq_html_bg: Optional[str] = None
    faq_html_ro: Optional[str] = None
    faq_html_en: Optional[str] = None
    terms_html_bg: Optional[str] = None
    terms_html_ro: Optional[str] = None
    terms_html_en: Optional[str] = None
    contacts_html_bg: Optional[str] = None
    contacts_html_ro: Optional[str] = None
    contacts_html_en: Optional[str] = None
    fees_html_bg: Optional[str] = None
    fees_html_ro: Optional[str] = None
    fees_html_en: Optional[str] = None
    how_it_works_html_bg: Optional[str] = None
    how_it_works_html_ro: Optional[str] = None
    how_it_works_html_en: Optional[str] = None
    # Phase 6 — Multi-language hero text (CMS-editable)
    hero_headline_bg: Optional[str] = None
    hero_subtitle_bg: Optional[str] = None
    hero_headline_ro: Optional[str] = None
    hero_subtitle_ro: Optional[str] = None
    hero_headline_en: Optional[str] = None
    hero_subtitle_en: Optional[str] = None



# ---------- Stripe (Super-Admin only) ----------
class StripeSettingsUpdate(BaseModel):
    """Admin CMS for Stripe keys. Secret + webhook_secret are write-only."""
    mode: Optional[str] = None  # "test" | "live"
    stripe_publishable_key_test: Optional[str] = None
    stripe_publishable_key_live: Optional[str] = None
    stripe_secret_key_test: Optional[str] = None
    stripe_secret_key_live: Optional[str] = None
    stripe_webhook_secret_test: Optional[str] = None
    stripe_webhook_secret_live: Optional[str] = None
    stripe_enabled: Optional[bool] = None


# ---------- Auth: password reset + 2FA ----------
class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6)
    new_password: str = Field(min_length=6, max_length=128)


class TwoFactorConfirm(BaseModel):
    code: str = Field(min_length=6, max_length=6)


class TwoFactorVerify(BaseModel):
    challenge_token: str
    code: str = Field(min_length=6, max_length=8)  # 8 = backup code


# ---------- Phase 3 moderation ----------
class InvalidateBidRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class BlockBidderRequest(BaseModel):
    user_id: str
    reason: Optional[str] = Field(default=None, max_length=500)


class InternalNote(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


# ---------- Phase 4 payments ----------
class BuyerFeeUpdate(BaseModel):
    status: str  # "unpaid" | "paid" | "waived" | "refunded"
    note: Optional[str] = Field(default=None, max_length=500)


# ---------- Phase 6 seller-initiated moderation requests ----------
class PromotionRequestCreate(BaseModel):
    """Seller asks to have their auction featured on the homepage."""
    note: Optional[str] = Field(default=None, max_length=600)


class TextChangeRequestCreate(BaseModel):
    """Seller requests a text / photo change on a live auction. Moderator must approve."""
    title: Optional[str] = Field(default=None, max_length=200)
    description: Optional[str] = Field(default=None, max_length=8000)
    note: Optional[str] = Field(default=None, max_length=600)


class ReorderImagesRequest(BaseModel):
    """Seller reorders images on their own auction (no approval needed)."""
    images: List[str] = Field(default_factory=list, max_length=40)


class ModerationDecision(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=600)
    # При одобряване на text_change заявка админът може да зададе и
    # ръчни преводи на описанието за RO/EN сайтовете.
    description_ro: Optional[str] = None
    description_en: Optional[str] = None

