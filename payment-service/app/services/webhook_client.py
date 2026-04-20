import asyncio
from typing import Dict, Any
from ipaddress import ip_address, IPv4Address, IPv6Address
from urllib.parse import urlparse
import httpx


class WebhookDeliveryError(Exception):
    """Raised when webhook delivery fails after all retries"""
    pass


class WebhookClientError(Exception):
    """Raised when webhook returns 4xx error (no retry)"""
    pass


class WebhookClient:
    """HTTP client for webhook delivery with retry logic"""
    
    def __init__(self) -> None:
        self.timeout = 5.0  # HTTP request timeout
        self.max_retries = 3
        self.backoff_delays = [1, 2, 4]  # Exponential backoff
    
    def _validate_webhook_url(self, url: str) -> None:
        """
        Validate webhook URL to prevent SSRF attacks
        
        Блокирует:
        - Private IP ranges (RFC 1918, RFC 4193)
        - Loopback addresses (127.0.0.0/8, ::1)
        - Link-local addresses (169.254.0.0/16, fe80::/10)
        - Localhost
        - Неподдерживаемые схемы (не http/https)
        
        Args:
            url: URL для проверки
            
        Raises:
            WebhookClientError: Если URL небезопасен
        """
        try:
            parsed = urlparse(url)
            
            # Проверка схемы
            if parsed.scheme not in ('http', 'https'):
                raise WebhookClientError(
                    "Invalid URL scheme: only http/https allowed"
                )
            
            # Проверка наличия hostname
            if not parsed.hostname:
                raise WebhookClientError("Invalid URL: missing hostname")
            
            # Блокировка localhost по имени
            if parsed.hostname.lower() in ('localhost', 'localhost.localdomain'):
                raise WebhookClientError("Localhost URLs are not allowed")
            
            # Попытка распарсить как IP адрес
            try:
                ip = ip_address(parsed.hostname)
                
                # Блокировка private IP ranges
                if isinstance(ip, (IPv4Address, IPv6Address)):
                    if ip.is_private:
                        raise WebhookClientError("Private IP addresses are not allowed")
                    if ip.is_loopback:
                        raise WebhookClientError("Loopback addresses are not allowed")
                    if ip.is_link_local:
                        raise WebhookClientError("Link-local addresses are not allowed")
                    if ip.is_reserved:
                        raise WebhookClientError("Reserved IP addresses are not allowed")
                        
            except ValueError:
                # Не IP адрес, это доменное имя - разрешаем
                # (DNS resolution происходит на стороне httpx, дополнительная
                # проверка resolved IP потребует синхронного DNS lookup)
                pass
                
        except WebhookClientError:
            raise
        except Exception:
            raise WebhookClientError("Invalid webhook URL format")
    
    async def send_webhook(self, url: str, payload: Dict[str, Any]) -> None:
        """
        Send webhook with retry logic
        
        - 3 attempts with exponential backoff (1s, 2s, 4s)
        - Retry on 5xx, timeout, connection errors
        - No retry on 4xx (client errors)
        
        Args:
            url: Webhook URL
            payload: JSON payload to send
            
        Raises:
            WebhookClientError: On 4xx errors (no retry)
            WebhookDeliveryError: After exhausting all retries
        """
        # SECURITY: Validate URL before sending to prevent SSRF
        self._validate_webhook_url(url)
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for attempt in range(self.max_retries):
                try:
                    response = await client.post(
                        url,
                        json=payload,
                        headers={"Content-Type": "application/json"}
                    )
                    
                    # Success: 2xx status
                    if 200 <= response.status_code < 300:
                        return
                    
                    # Client error 4xx: no retry
                    if 400 <= response.status_code < 500:
                        # SECURITY: Не раскрываем response.text в exception
                        raise WebhookClientError(
                            f"Client error {response.status_code}"
                        )
                    
                    # Server error 5xx: retry
                    if attempt < self.max_retries - 1:
                        await asyncio.sleep(self.backoff_delays[attempt])
                        continue
                    
                except (httpx.TimeoutException, httpx.ConnectError):
                    # Network errors: retry
                    if attempt < self.max_retries - 1:
                        await asyncio.sleep(self.backoff_delays[attempt])
                        continue
                    
                    # SECURITY: Не раскрываем детали exception в сообщении
                    raise WebhookDeliveryError(
                        f"Failed after {self.max_retries} attempts"
                    )
            
            raise WebhookDeliveryError(
                f"Failed after {self.max_retries} attempts"
            )
