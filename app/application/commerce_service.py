import base64
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.core.security import decrypt_secret, encrypt_secret, mask_secret
from app.application.notification_service import notification_service
from app.domain.orders.models import Order
from app.infrastructure.cache.redis_client import cache_client
from app.infrastructure.channels.cafe24 import (
    Cafe24Adapter,
    Cafe24AuthError,
    Cafe24OrderError,
    Cafe24OrderNotFound,
    Cafe24RateLimited,
    Cafe24TransientError,
)
from app.infrastructure.database.models import CommerceConnectionModel

ACCESS_TOKEN_TTL = timedelta(hours=2)
REFRESH_TOKEN_TTL = timedelta(days=14)
ACCESS_TOKEN_SKEW = timedelta(seconds=60)  # refresh slightly before actual expiry

OAUTH_STATE_TTL_SECONDS = 600  # 10 min one-time state

# Customer-facing messages (never leak raw Cafe24 errors)
MSG_ORDER_NOT_FOUND = "주문번호를 다시 확인해 주세요."
MSG_RATE_LIMITED = "잠시 후 다시 시도해 주세요."
MSG_TRANSIENT = "주문 조회가 일시 점검 중입니다. 잠시 후 다시 시도해 주세요."
MSG_REAUTH_REQUIRED = "주문 조회가 일시 점검 중입니다. 빠른 시일 내 다시 연동해 드릴게요."
MSG_NOT_CONNECTED = "주문 조회가 아직 연동되지 않았습니다. 스토어 관리자에게 문의해 주세요."


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class CommerceService:
    """Per-mall live commerce (Cafe24) OAuth connection + token + order lookup."""

    # ---------------- Connection CRUD ----------------

    async def get_connection(
        self, session: AsyncSession, mall_id: str
    ) -> Optional[CommerceConnectionModel]:
        res = await session.execute(
            select(CommerceConnectionModel).where(CommerceConnectionModel.mall_id == mall_id)
        )
        return res.scalar_one_or_none()

    async def save_keys(
        self,
        session: AsyncSession,
        mall_id: str,
        cafe24_mall_id: str,
        client_id: str,
        client_secret: str,
    ) -> CommerceConnectionModel:
        """Store (encrypt) API keys. Does NOT grant access yet -> status stays pending
        unless it was already connected (re-saving keys keeps an existing grant)."""
        conn = await self.get_connection(session, mall_id)
        if conn is None:
            conn = CommerceConnectionModel(
                id=secrets.token_hex(16),
                mall_id=mall_id,
                platform="cafe24",
            )
            session.add(conn)

        conn.cafe24_mall_id = cafe24_mall_id
        conn.client_id = client_id
        conn.client_secret_encrypted = encrypt_secret(client_secret) if client_secret else None
        conn.client_secret_masked = mask_secret(client_secret)
        # Keep existing tokens unless this is a brand-new connection
        if conn.status not in ("connected",):
            conn.status = "pending"
        await session.commit()
        await session.refresh(conn)
        return conn

    # ---------------- OAuth state (CSRF) ----------------

    async def create_oauth_state(self, mall_id: str) -> str:
        state = secrets.token_urlsafe(32)
        await cache_client.set(
            f"cafe24_oauth_state:{state}", mall_id, expire_seconds=OAUTH_STATE_TTL_SECONDS
        )
        return state

    async def consume_oauth_state(self, state: str) -> Optional[str]:
        key = f"cafe24_oauth_state:{state}"
        mall_id = await cache_client.get(key)
        if mall_id:
            await cache_client.delete(key)  # one-time use
        return mall_id

    # ---------------- Token exchange & refresh ----------------

    def _token_endpoint(self, cafe24_mall_id: str) -> str:
        return f"https://{cafe24_mall_id}.cafe24api.com/api/v2/oauth/token"

    async def _post_token(
        self, cafe24_mall_id: str, client_id: str, client_secret: str, data: Dict[str, str]
    ) -> dict:
        auth = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        headers = {
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                self._token_endpoint(cafe24_mall_id), data=data, headers=headers
            )
            resp.raise_for_status()
            return resp.json()

    async def exchange_code_for_tokens(
        self,
        session: AsyncSession,
        conn: CommerceConnectionModel,
        code: str,
        redirect_uri: str,
    ) -> bool:
        client_secret = decrypt_secret(conn.client_secret_encrypted)
        if not client_secret:
            logger.error(f"Commerce token exchange failed: no decryptable secret for {conn.mall_id}")
            return False
        try:
            tok = await self._post_token(
                conn.cafe24_mall_id,
                conn.client_id,
                client_secret,
                {
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                },
            )
        except Exception as e:
            logger.error(f"Cafe24 token exchange error for {conn.mall_id}: {e}")
            return False
        return await self._persist_tokens(session, conn, tok)

    async def _persist_tokens(
        self, session: AsyncSession, conn: CommerceConnectionModel, tok: dict
    ) -> bool:
        access = tok.get("access_token")
        refresh = tok.get("refresh_token")
        if not access:
            logger.error(f"Cafe24 token response missing access_token for {conn.mall_id}")
            return False

        now = _utcnow()
        access_exp = now + timedelta(seconds=int(tok.get("expires_in", 7200) or 7200))
        refresh_exp = now + timedelta(
            seconds=int(tok.get("refresh_token_expires_in", REFRESH_TOKEN_TTL.total_seconds()) or REFRESH_TOKEN_TTL.total_seconds())
        )

        conn.access_token_encrypted = encrypt_secret(access)
        if refresh:
            conn.refresh_token_encrypted = encrypt_secret(refresh)
            conn.refresh_token_expires_at = refresh_exp
        conn.access_token_expires_at = access_exp
        conn.status = "connected"
        await session.commit()
        await session.refresh(conn)
        return True

    async def refresh_access_token(
        self, session: AsyncSession, conn: CommerceConnectionModel
    ) -> bool:
        refresh_token = decrypt_secret(conn.refresh_token_encrypted)
        client_secret = decrypt_secret(conn.client_secret_encrypted)
        if not refresh_token or not client_secret:
            return False
        try:
            tok = await self._post_token(
                conn.cafe24_mall_id,
                conn.client_id,
                client_secret,
                {"grant_type": "refresh_token", "refresh_token": refresh_token},
            )
        except Exception as e:
            logger.error(f"Cafe24 token refresh error for {conn.mall_id}: {e}")
            return False
        return await self._persist_tokens(session, conn, tok)

    async def _ensure_valid_access_token(
        self, session: AsyncSession, conn: CommerceConnectionModel
    ) -> Optional[str]:
        """Return a valid access token, auto-refreshing if expired. Marks
        refresh_expired (and notifies merchant) when the refresh token is dead."""
        access = decrypt_secret(conn.access_token_encrypted)
        exp = _ensure_aware(conn.access_token_expires_at)

        if access and exp and exp - ACCESS_TOKEN_SKEW > _utcnow():
            return access

        # Access token missing/expired -> try refresh
        refresh_exp = _ensure_aware(conn.refresh_token_expires_at)
        refresh_token = decrypt_secret(conn.refresh_token_encrypted)
        if not refresh_token or (refresh_exp and refresh_exp <= _utcnow()):
            await self._mark_refresh_expired(session, conn)
            return None

        if await self.refresh_access_token(session, conn):
            return decrypt_secret(conn.access_token_encrypted)
        return None

    async def _mark_refresh_expired(
        self, session: AsyncSession, conn: CommerceConnectionModel
    ) -> None:
        """Flag the connection as needing re-authorization and alert the merchant once."""
        already = conn.status == "refresh_expired"
        conn.status = "refresh_expired"
        await session.commit()
        if not already:
            try:
                await notification_service.notify_merchant_alert(
                    session,
                    conn.mall_id,
                    alert_type="CAFE24_REAUTH_REQUIRED",
                    title="카페24 재연동 필요",
                    message=(
                        "주문 조회용 갱신 토큰(2주)이 만료되어 실시간 주문·배송 조회가 "
                        "일시 중단되었습니다. 챗봇공장 쇼룸에서 '카페24 권한 허용'을 "
                        "다시 한 번 눌러 주세요."
                    ),
                )
            except Exception as e:  # never break the customer path
                logger.warning(f"[Commerce] reauth alert failed for {conn.mall_id}: {e}")

    # ---------------- Live order lookup ----------------

    async def lookup_order(
        self, session: AsyncSession, mall_id: str, order_id: str
    ) -> Tuple[Optional[Order], Optional[str]]:
        """Look up a real order via the mall's Cafe24 token.

        Returns (order, None) on success, or (None, customer_msg) on any failure.
        Auto-refreshes the access token once on auth error.
        """
        conn = await self.get_connection(session, mall_id)
        if conn is None or conn.status == "pending":
            return None, MSG_NOT_CONNECTED
        if conn.status == "refresh_expired":
            return None, MSG_REAUTH_REQUIRED

        access = await self._ensure_valid_access_token(session, conn)
        if not access:
            # status was flipped to refresh_expired inside _ensure_valid_access_token
            return None, MSG_REAUTH_REQUIRED

        adapter = Cafe24Adapter(mall_id=conn.cafe24_mall_id)
        try:
            payload = await adapter.fetch_order_payload(order_id, access)
            from app.infrastructure.channels.cafe24 import build_order_from_payload

            order = build_order_from_payload(order_id, conn.cafe24_mall_id, payload)
            return order, None
        except Cafe24OrderNotFound:
            return None, MSG_ORDER_NOT_FOUND
        except Cafe24RateLimited:
            logger.warning(f"Cafe24 rate limit for mall={mall_id}")
            return None, MSG_RATE_LIMITED
        except Cafe24AuthError:
            # Access token may have just expired -> refresh once and retry
            if await self.refresh_access_token(session, conn):
                access2 = decrypt_secret(conn.access_token_encrypted)
                try:
                    payload = await adapter.fetch_order_payload(order_id, access2)
                    from app.infrastructure.channels.cafe24 import build_order_from_payload

                    order = build_order_from_payload(order_id, conn.cafe24_mall_id, payload)
                    return order, None
                except Cafe24OrderNotFound:
                    return None, MSG_ORDER_NOT_FOUND
                except Cafe24RateLimited:
                    return None, MSG_RATE_LIMITED
                except Cafe24TransientError:
                    return None, MSG_TRANSIENT
                except Cafe24AuthError:
                    conn.status = "refresh_expired"
                    await session.commit()
                    return None, MSG_REAUTH_REQUIRED
            conn.status = "refresh_expired"
            await session.commit()
            return None, MSG_REAUTH_REQUIRED
        except Cafe24TransientError:
            return None, MSG_TRANSIENT
        except Cafe24OrderError:
            return None, MSG_TRANSIENT

    async def list_selling_product_detail_urls(
        self,
        session: AsyncSession,
        mall_id: str,
        store_base_url: str,
        max_items: int = 2000,
    ) -> List[str]:
        """List selling product detail URLs via Cafe24 Admin API when OAuth is connected.

        Builds stable Cafe24 detail URLs: {origin}/product/detail.html?product_no=N
        Returns [] when not connected / token missing / API error (caller keeps crawl URLs).
        """
        conn = await self.get_connection(session, mall_id)
        if conn is None or conn.status != "connected" or not conn.cafe24_mall_id:
            return []
        access = await self._ensure_valid_access_token(session, conn)
        if not access:
            return []

        parsed = __import__("urllib.parse", fromlist=["urlparse"]).urlparse(store_base_url)
        origin = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
        if not parsed.scheme or not parsed.netloc:
            return []

        headers = {
            "Authorization": f"Bearer {access}",
            "Content-Type": "application/json",
            "X-Cafe24-Api-Version": "2024-06-01",
        }
        urls: List[str] = []
        offset = 0
        limit = 100
        base = f"https://{conn.cafe24_mall_id}.cafe24api.com/api/v2/admin/products"
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                while len(urls) < max_items:
                    resp = await client.get(
                        base,
                        headers=headers,
                        params={
                            "limit": limit,
                            "offset": offset,
                            "display": "T",
                            "selling": "T",
                            "fields": "product_no,product_name",
                        },
                    )
                    if resp.status_code == 401:
                        if await self.refresh_access_token(session, conn):
                            access = decrypt_secret(conn.access_token_encrypted)
                            headers["Authorization"] = f"Bearer {access}"
                            continue
                        break
                    if resp.status_code != 200:
                        logger.warning(
                            "[Commerce] Cafe24 products list failed mall=%s status=%s",
                            mall_id,
                            resp.status_code,
                        )
                        break
                    data = resp.json() or {}
                    products = data.get("products") or data.get("resource") or []
                    if not products:
                        break
                    for p in products:
                        no = p.get("product_no")
                        if no is None:
                            continue
                        urls.append(f"{origin}/product/detail.html?product_no={no}")
                        if len(urls) >= max_items:
                            break
                    if len(products) < limit:
                        break
                    offset += limit
        except Exception as e:
            logger.warning("[Commerce] Cafe24 products list error mall=%s: %s", mall_id, e)
            return []

        logger.info(
            "[Commerce] Cafe24 API product URLs mall=%s count=%d", mall_id, len(urls)
        )
        return urls

    # ---------------- Rate limiting (per conversation) ----------------

    _rate_store: Dict[str, List[float]] = {}

    def _rate_allow(self, session_key: str, limit: int = 5, window_sec: int = 60) -> bool:
        """Sliding-window limiter. True = allowed, False = over the per-conversation limit."""
        now = time.time()
        bucket = self._rate_store.setdefault(session_key, [])
        cutoff = now - window_sec
        bucket = [t for t in bucket if t > cutoff]
        if len(bucket) >= limit:
            self._rate_store[session_key] = bucket
            return False
        bucket.append(now)
        self._rate_store[session_key] = bucket
        return True


commerce_service = CommerceService()
