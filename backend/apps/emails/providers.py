"""
Email providers for HeyJarvis.
"""
from abc import ABC, abstractmethod


class BaseEmailProvider(ABC):
    """Abstract base for email providers."""

    @abstractmethod
    def send(self, email_data: dict) -> bool:
        """Send an email. Returns True on success."""
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        pass


class GmailProvider(BaseEmailProvider):
    """Gmail OAuth2 provider."""
    def send(self, email_data: dict) -> bool:
        # TODO: Implement Google Gmail API send
        return False

    def get_provider_name(self) -> str:
        return 'gmail'


class OutlookProvider(BaseEmailProvider):
    """Microsoft Outlook/Graph API provider."""
    def send(self, email_data: dict) -> bool:
        # TODO: Implement Microsoft Graph API send
        return False

    def get_provider_name(self) -> str:
        return 'outlook'


class SMTPProvider(BaseEmailProvider):
    """SMTP provider."""
    def send(self, email_data: dict) -> bool:
        # TODO: Implement SMTP send
        return False

    def get_provider_name(self) -> str:
        return 'smtp'


def get_provider(provider_name: str = None) -> BaseEmailProvider:
    """Factory function to get the configured email provider."""
    import os
    provider = provider_name or os.environ.get('EMAIL_PROVIDER', 'gmail')
    providers = {
        'gmail': GmailProvider,
        'outlook': OutlookProvider,
        'smtp': SMTPProvider,
    }
    provider_class = providers.get(provider, SMTPProvider)
    return provider_class()
