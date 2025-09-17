from __future__ import annotations
from typing import Dict, Optional, Union
import logging

log = logging.getLogger(__name__)

class ProviderManager:
    """Manages multiple providers and handles URL resolution logic"""

    def __init__(self, providers: Optional[Dict[str, object]] = None):
        self.providers = providers or {}

    def detect_provider_from_url(self, url: str) -> Optional[str]:
        """Detect which provider a URL belongs to"""
        if not url:
            return None

        # Real-Debrid detection
        if 'real-debrid.com' in url:
            return 'realdebrid'

        # AllDebrid detection
        if 'alldebrid.com' in url:
            return 'alldebrid'
        
        # TorBox detection
        if 'torbox.app' in url:
            return 'torbox'

        return None

    def construct_restricted_url(self, provider_name: str, provider_id: str) -> Optional[str]:
        """Construct a restricted URL from provider name and ID"""
        if provider_name == 'realdebrid':
            return f"https://real-debrid.com/d/{provider_id}"
        elif provider_name == 'premiumize':
            return f"https://premiumize.me/d/{provider_id}"
        elif provider_name == 'alldebrid':
            return f"https://alldebrid.com/dl/{provider_id}"

        # Add more providers here as needed

        return provider_id  # Fallback to using the ID as-is

    def resolve_url(self, url: str, provider_name: Optional[str] = None) -> Optional[Dict]:
        """
        Resolve a restricted URL to an unrestricted URL and metadata.

        Args:
            url: The restricted URL to resolve
            provider_name: Optional provider name hint

        Returns:
            Dict with 'download_url', 'name', 'size' or None if resolution fails
        """
        if not url:
            return None

        # Auto-detect provider if not specified
        if not provider_name:
            provider_name = self.detect_provider_from_url(url)

        if not provider_name:
            # Not a provider URL, return as-is
            return {
                'download_url': url,
                'name': 'file',
                'size': 0
            }

        provider = self.providers.get(provider_name)
        if not provider:
            log.warning(f"Provider '{provider_name}' not available")
            return {
                'download_url': url,  # Fallback to original URL
                'name': 'file',
                'size': 0
            }

        try:
            result = provider.resolve_link(url)
            if result and result.get('download_url'):
                return {
                    'download_url': result['download_url'],
                    'name': result.get('name') or result.get('filename') or 'file',
                    'size': int(result.get('size') or result.get('filesize') or 0)
                }
        except Exception as e:
            log.warning(f"Failed to resolve URL '{url}' with provider '{provider_name}': {e}")

        # Fallback to original URL
        return {
            'download_url': url,
            'name': 'file',
            'size': 0
        }

    def get_download_url(self, stored_url: Optional[str], provider_name: Optional[str] = None,
                        provider_id: Optional[str] = None) -> Optional[str]:
        """
        Get the appropriate download URL for storage in database.
        This returns the restricted URL that should be stored.

        Args:
            stored_url: Already stored URL (if any)
            provider_name: Provider name (if using provider)
            provider_id: Provider ID (if using provider)

        Returns:
            The restricted URL that should be stored in the database
        """
        # If we already have a stored URL, return it
        if stored_url:
            return stored_url

        # If we have provider info, construct the restricted URL
        if provider_name and provider_id:
            return self.construct_restricted_url(provider_name, provider_id)

        return None

