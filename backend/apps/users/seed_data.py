"""
Centralized seed data definitions and helpers for HeyJarvis.

Demo accounts use well-known passwords, so they are only provisioned when
demo mode is enabled (ENABLE_DEMO_ACCOUNTS=true, defaulting to on only when
DEBUG is true). Production deployments get no demo logins unless explicitly
opted in.
"""
from typing import Optional, Dict, Any, List

DEMO_ACCOUNTS: Dict[str, Dict[str, Any]] = {
    'admin@raleighdentistry.com': {
        'password': 'Password123!',
        'role': 'AGENCY_ADMIN',
        'first_name': 'Agency',
        'last_name': 'Admin',
        'is_staff': False,
        'is_superuser': False,
        'practice_slug': 'raleigh-dentistry',
    },
    'doctor@raleighdentistry.com': {
        'password': 'Password123!',
        'role': 'PRACTICE_ADMIN',
        'first_name': 'Dr. Sarah',
        'last_name': 'Brody',
        'is_staff': False,
        'is_superuser': False,
        'practice_slug': 'raleigh-dentistry',
    },
    'brody@raleighdentistry.com': {
        'password': 'Password123!',
        'role': 'PRACTICE_ADMIN',
        'first_name': 'Dr. Sarah',
        'last_name': 'Brody',
        'is_staff': False,
        'is_superuser': False,
        'practice_slug': 'raleigh-dentistry',
    },
    'desk@raleighdentistry.com': {
        'password': 'Password123!',
        'role': 'FRONT_DESK',
        'first_name': 'Emma',
        'last_name': 'Davis',
        'is_staff': False,
        'is_superuser': False,
        'practice_slug': 'raleigh-dentistry',
    },
    'admin@raleighcomprehensive.com': {
        'password': 'raleigh2024!',
        'role': 'OWNER',
        'first_name': 'Office',
        'last_name': 'Manager',
        'is_staff': False,
        'is_superuser': False,
        'practice_slug': 'raleigh-comprehensive',
    },
    'desk@raleighcomprehensive.com': {
        'password': 'desk2024!',
        'role': 'FRONT_DESK',
        'first_name': 'Front',
        'last_name': 'Desk',
        'is_staff': False,
        'is_superuser': False,
        'practice_slug': 'raleigh-comprehensive',
    },
}

DEMO_PRACTICES: Dict[str, Dict[str, Any]] = {
    'raleigh-dentistry': {
        'name': 'Raleigh Comprehensive & Cosmetic Dentistry',
        'email': 'frontdesk@raleighdentistry.com',
        'phone': '(919) 555-0142',
        'address': '123 Oakwood Ave, Raleigh, NC 27601',
        'city': 'Raleigh',
        'state': 'NC',
        'zip_code': '27601',
        'timezone': 'America/New_York',
        'website': 'https://raleighdentistry.com',
        'active': True,
    },
    'raleigh-comprehensive': {
        'name': 'Raleigh Comprehensive & Cosmetic Dentistry',
        'email': 'frontdesk@raleighcomprehensive.com',
        'phone': '(919) 555-0142',
        'address': '123 Oakwood Ave, Raleigh, NC 27601',
        'city': 'Raleigh',
        'state': 'NC',
        'zip_code': '27601',
        'timezone': 'America/New_York',
        'website': 'https://raleighcomprehensive.com',
        'active': True,
    },
}


DEMO_ACCOUNT_LABELS = {
    'admin@raleighdentistry.com': 'Agency Admin',
    'doctor@raleighdentistry.com': 'Doctor (Practice Admin)',
    'desk@raleighdentistry.com': 'Front Desk',
}


def demo_accounts_enabled() -> bool:
    from django.conf import settings
    return bool(getattr(settings, 'DEMO_ACCOUNTS_ENABLED', False))


def public_demo_accounts() -> List[Dict[str, str]]:
    """Demo logins surfaced on the login page (only called when demo mode is on)."""
    return [
        {
            'email': email,
            'password': DEMO_ACCOUNTS[email]['password'],
            'role': DEMO_ACCOUNTS[email]['role'],
            'label': label,
        }
        for email, label in DEMO_ACCOUNT_LABELS.items()
    ]


def ensure_practice(slug: str):
    """Ensure practice and baseline settings exist."""
    from apps.practices.models import Practice, BookingRules, PracticeSettings
    data = DEMO_PRACTICES.get(slug, DEMO_PRACTICES['raleigh-dentistry'])
    practice, _ = Practice.objects.get_or_create(slug=slug, defaults=data)
    try:
        BookingRules.objects.get_or_create(
            practice=practice,
            defaults={
                'new_patient_duration': 90,
                'doctor_duration': 30,
                'hygiene_duration': 60,
                'emergency_duration': 60,
                'confirmation_hours': 48,
                'no_show_fee': 65.00,
                'financing_options': ['Cherry', 'CareCredit'],
            }
        )
    except Exception as e:
        print(f"Notice: BookingRules creation skipped/failed: {e}")

    try:
        PracticeSettings.objects.get_or_create(
            practice=practice,
            defaults={
                'default_from_name': practice.name,
                'default_from_email': practice.email,
            }
        )
    except Exception as e:
        print(f"Notice: PracticeSettings creation skipped/failed: {e}")

    return practice


def ensure_demo_account(email: str, requested_password: Optional[str] = None):
    """
    Ensure a demo account exists and has the designated password.
    Returns the User model instance if email matches demo config, else None.
    """
    from apps.users.models import User

    email_clean = (email or '').strip().lower()
    if email_clean not in DEMO_ACCOUNTS or not demo_accounts_enabled():
        return None

    info = DEMO_ACCOUNTS[email_clean]
    if requested_password is not None and requested_password.strip() != info['password']:
        return None

    practice = ensure_practice(info['practice_slug'])
    user = User.objects.filter(email__iexact=email_clean).first()
    if not user:
        user = User.objects.create(
            email=email_clean,
            username=email_clean,
            first_name=info['first_name'],
            last_name=info['last_name'],
            role=info['role'],
            is_staff=info['is_staff'],
            is_superuser=info['is_superuser'],
            is_active=True,
            practice=practice,
        )
    else:
        user.username = email_clean
        user.first_name = info['first_name']
        user.last_name = info['last_name']
        user.role = info['role']
        user.is_staff = info['is_staff']
        user.is_superuser = info['is_superuser']
        user.is_active = True
        if not user.practice:
            user.practice = practice

    user.set_password(info['password'])
    user.save()
    return user


def seed_all_demo_data() -> List[Dict[str, Any]]:
    """Seed demo practices, plus demo user accounts when demo mode is enabled."""
    results = []
    for slug in DEMO_PRACTICES:
        ensure_practice(slug)
    if not demo_accounts_enabled():
        return results
    for email in DEMO_ACCOUNTS:
        user = ensure_demo_account(email)
        if user:
            results.append({'email': user.email, 'role': user.role})
    return results
