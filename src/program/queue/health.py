"""
Health monitoring for LavinMQ and queue services.

This module provides health checking functionality for the queue system,
focusing on LavinMQ connectivity and service availability.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import aiohttp
import pika
from loguru import logger

from program.settings.manager import settings_manager


@dataclass
class HealthStatus:
    """Health status for a service"""
    service: str
    status: str  # healthy, unhealthy, unknown
    last_check: datetime
    response_time_ms: Optional[float] = None
    error_message: Optional[str] = None
    details: Dict[str, Any] = None

    def __post_init__(self):
        if self.details is None:
            self.details = {}


class HealthChecker:
    """Monitors the health of LavinMQ and other services"""

    def __init__(self):
        self._status_cache: Dict[str, HealthStatus] = {}
        self._check_interval = timedelta(seconds=30)
        self._last_check = datetime.now() - self._check_interval
        self._timeout = 5  # seconds - reduced for faster checks

    def _parse_amqp(self) -> Tuple[str, Optional[str], Optional[str]]:
        """Parse AMQP URL and return (host, username, password)."""
        lavinmq_url = settings_manager.settings.lavinmq_url
        parsed = urlparse(lavinmq_url)
        host = parsed.hostname or "localhost"
        user = parsed.username
        password = parsed.password
        return host, user, password

    async def check_lavinmq_health(self) -> HealthStatus:
        """Check LavinMQ health via HTTP management API (simplified)"""
        try:
            lavinmq_url = settings_manager.settings.lavinmq_url
            if not lavinmq_url.startswith("amqp://"):
                raise ValueError(f"Invalid LavinMQ URL format: {lavinmq_url}")

            host, user, password = self._parse_amqp()
            management_url = f"http://{host}:15672/api/overview"

            start_time = datetime.now()

            auth = aiohttp.BasicAuth(user, password) if user and password else None
            timeout = aiohttp.ClientTimeout(total=self._timeout)
            async with aiohttp.ClientSession(timeout=timeout, auth=auth) as session:
                async with session.get(management_url) as response:
                    response_time = (datetime.now() - start_time).total_seconds() * 1000

                    if response.status == 200:
                        return HealthStatus(
                            service="lavinmq",
                            status="healthy",
                            last_check=datetime.now(),
                            response_time_ms=response_time,
                            details={"management_api": "accessible"}
                        )
                    else:
                        return HealthStatus(
                            service="lavinmq",
                            status="unhealthy",
                            last_check=datetime.now(),
                            response_time_ms=response_time,
                            error_message=f"HTTP {response.status}"
                        )

        except Exception as e:
            logger.debug(f"LavinMQ management API check failed: {e}")
            return HealthStatus(
                service="lavinmq",
                status="unhealthy",
                last_check=datetime.now(),
                error_message=str(e)
            )

    async def check_lavinmq_connection(self) -> HealthStatus:
        """Check LavinMQ connection via AMQP (simplified)"""
        try:
            start_time = datetime.now()
            lavinmq_url = settings_manager.settings.lavinmq_url

            # Simple connection test - just connect and disconnect
            connection = pika.BlockingConnection(pika.URLParameters(lavinmq_url))
            connection.close()

            response_time = (datetime.now() - start_time).total_seconds() * 1000

            return HealthStatus(
                service="lavinmq_connection",
                status="healthy",
                last_check=datetime.now(),
                response_time_ms=response_time,
                details={"connection_test": "passed"}
            )

        except Exception as e:
            logger.debug(f"LavinMQ connection check failed: {e}")
            return HealthStatus(
                service="lavinmq_connection",
                status="unhealthy",
                last_check=datetime.now(),
                error_message=str(e)
            )

    async def _get_consumers_map(self) -> Dict[str, int]:
        """Return a mapping of queue name -> consumers count via management API."""
        host, user, password = self._parse_amqp()
        url = f"http://{host}:15672/api/queues"
        auth = aiohttp.BasicAuth(user, password) if user and password else None
        timeout = aiohttp.ClientTimeout(total=self._timeout)
        async with aiohttp.ClientSession(timeout=timeout, auth=auth) as session:
            async with session.get(url) as response:
                if response.status != 200:
                    raise RuntimeError(f"Queues API HTTP {response.status}")
                data = await response.json()
                consumers: Dict[str, int] = {}
                for q in data:
                    name = q.get("name")
                    consumers[name] = int(q.get("consumers", 0))
                return consumers

    async def wait_for_workers_ready_async(
        self,
        expected_queues: List[str],
        *,
        min_consumers: int = 1,
        timeout_seconds: int = 60,
        poll_interval: float = 1.0,
    ) -> bool:
        """Wait until all expected queues have at least min_consumers.
        Uses LavinMQ management API.
        """
        end_time = datetime.now() + timedelta(seconds=timeout_seconds)
        while datetime.now() < end_time:
            try:
                consumers = await self._get_consumers_map()
                if all(consumers.get(q, 0) >= min_consumers for q in expected_queues):
                    logger.info(
                        f"All workers ready!"
                    )
                    return True
                else:
                    logger.debug(f"Waiting for workers...")
            except Exception as e:
                logger.debug(f"Worker readiness check failed: {e}")
            await asyncio.sleep(poll_interval)
        return False

    def wait_for_workers_ready(
        self,
        expected_queues: List[str],
        *,
        min_consumers: int = 1,
        timeout_seconds: int = 60,
        poll_interval: float = 1.0,
    ) -> bool:
        """Synchronous wrapper around wait_for_workers_ready_async."""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(
                    self.wait_for_workers_ready_async(
                        expected_queues,
                        min_consumers=min_consumers,
                        timeout_seconds=timeout_seconds,
                        poll_interval=poll_interval,
                    )
                )
            finally:
                loop.close()
        except Exception as e:
            logger.debug(f"Synchronous readiness check failed: {e}")
            return False

    async def check_all_services(self) -> Dict[str, HealthStatus]:
        """Check health of all services"""
        now = datetime.now()
        if now - self._last_check < self._check_interval:
            return self._status_cache.copy()

        tasks = [
            self.check_lavinmq_health(),
            self.check_lavinmq_connection()
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                service_name = ["lavinmq", "lavinmq_connection"][i]
                self._status_cache[service_name] = HealthStatus(
                    service=service_name,
                    status="unhealthy",
                    last_check=now,
                    error_message=str(result)
                )
            else:
                self._status_cache[result.service] = result

        self._last_check = now
        return self._status_cache.copy()

    def get_overall_health(self) -> str:
        """Get overall health status"""
        if not self._status_cache:
            return "unknown"

        unhealthy_services = [s for s in self._status_cache.values() if s.status == "unhealthy"]

        if unhealthy_services:
            return "unhealthy"
        elif all(s.status == "healthy" for s in self._status_cache.values()):
            return "healthy"
        else:
            return "degraded"

    def check_lavinmq_simple(self) -> bool:
        """Simple synchronous LavinMQ connection check"""
        try:
            lavinmq_url = settings_manager.settings.lavinmq_url
            connection = pika.BlockingConnection(pika.URLParameters(lavinmq_url))
            connection.close()
            return True
        except Exception:
            return False


# Global instance
health_checker = HealthChecker()
