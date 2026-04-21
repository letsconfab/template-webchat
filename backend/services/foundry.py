"""Foundry service for syncing documents from a Foundry instance."""

import base64
from typing import List, Dict, Any, Optional

import httpx

from config import config


class FoundryService:
    """Service for interacting with a Foundry instance."""

    def __init__(self, base_url: str, access_token: str):
        self.base_url = base_url.rstrip("/")
        self.access_token = access_token
        self.client = httpx.AsyncClient(
            timeout=30.0, headers={"Authorization": f"Bearer {access_token}"}
        )

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()

    async def get_confabs(self) -> List[Dict[str, Any]]:
        """Get list of user's confabs from Foundry."""
        response = await self.client.get(f"{self.base_url}/confabs")
        response.raise_for_status()
        return response.json()

    async def get_confab(self, confab_id: int) -> Dict[str, Any]:
        """Get a specific confab by ID."""
        response = await self.client.get(f"{self.base_url}/confabs/{confab_id}")
        response.raise_for_status()
        return response.json()

    async def get_documents(self, confab_id: int) -> List[Dict[str, Any]]:
        """Get list of documents for a confab."""
        response = await self.client.get(
            f"{self.base_url}/confabs/{confab_id}/documents"
        )
        response.raise_for_status()
        return response.json()

    async def get_document_content(self, confab_id: int, document_id: int) -> bytes:
        """Get document content (base64 encoded)."""
        response = await self.client.get(
            f"{self.base_url}/confabs/{confab_id}/documents/{document_id}/versions/latest"
        )
        response.raise_for_status()
        data = response.json()
        # Content is base64 encoded in the response
        content_base64 = data.get("content_base64", "")
        return base64.b64decode(content_base64)

    async def get_document_metadata(
        self, confab_id: int, document_id: int
    ) -> Dict[str, Any]:
        """Get document metadata."""
        response = await self.client.get(
            f"{self.base_url}/confabs/{confab_id}/documents/{document_id}"
        )
        response.raise_for_status()
        return response.json()


async def create_foundry_service(foundry_url: str, access_token: str) -> FoundryService:
    """Factory function to create a Foundry service instance."""
    return FoundryService(foundry_url, access_token)
