"""
Utility functions for HeyJarvis.
"""
import random
import string
import re


def generate_confirmation_code(length: int = 8) -> str:
    """Generate a random confirmation code."""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))


def format_phone_number(phone: str) -> str:
    """Format a phone number to (XXX) XXX-XXXX."""
    digits = re.sub(r'\D', '', phone)
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    elif len(digits) == 11 and digits[0] == '1':
        return f"({digits[1:4]}) {digits[4:7]}-{digits[7:]}"
    return phone
