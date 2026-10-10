import pytest
from apps.practices.models import Practice, BookingRules
from apps.conversations.models import Conversation
from apps.conversations.state_machine import ConciergeStateMachine

@pytest.mark.django_db
def test_streamlined_scheduling_and_name_change():
    practice = Practice.objects.create(
        name="Raleigh Comprehensive & Cosmetic Dentistry",
        slug="raleigh-test-clinic",
        phone="(919) 555-0100"
    )
    BookingRules.objects.get_or_create(practice=practice)
    conv = Conversation.objects.create(practice=practice)
    sm = ConciergeStateMachine(conv, practice)

    # 1. Start -> Intent
    res1 = sm.process_message("Hi, I need a new patient exam")
    assert "full name" in res1['message'].lower()

    # 2. Name provided
    res2 = sm.process_message("Divyanshu")
    assert "Divyanshu" in res2['message']
    assert "phone number or email" in res2['message'].lower()

    # 3. Email provided -> Streamlined scheduling question (NO "Thanks, Divyanshu! What day works best...")
    res3 = sm.process_message("divyanshu@example.com")
    assert "what day works best for your visit (e.g., thursday" not in res3['message'].lower()
    assert "what time of day or day works best for your visit" in res3['message'].lower()

    # 4. User provides time (e.g. 11:11 am) -> Straight to Confirmation
    res4 = sm.process_message("11:11 am")
    assert "confirm" in res4['message'].lower()
    assert "11:11 AM" in res4['message']
    assert "Divyanshu" in res4['message']

    # 5. User changes name!
    res5 = sm.process_message("Actually my name is Divyanshu Dubey")
    assert "Divyanshu Dubey" in res5['message']
    assert conv.patient_name == "Divyanshu Dubey"

    # 6. User confirms appointment
    res6 = sm.process_message("Yes looks great")
    assert "submitted" in res6['message'].lower()
    assert conv.state == Conversation.STATE_SUBMITTED
