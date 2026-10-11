"""
Practice knowledge: facts a practice approved for Concierge to share, plus the questions
Concierge could not answer (so the practice can add an answer once).
"""
import re

from django.db.models import F

STOPWORDS = {
    'a', 'an', 'the', 'is', 'are', 'do', 'does', 'did', 'you', 'your', 'i', 'me', 'my', 'we', 'our', 'can',
    'could', 'would', 'will', 'to', 'of', 'for', 'in', 'on', 'at', 'and', 'or', 'it', 'this', 'that', 'there',
    'what', 'when', 'where', 'how', 'who', 'which', 'why', 'have', 'has', 'any', 'with', 'be', 'am', 'if',
    'about', 'get', 'please', 'hi', 'hello', 'need', 'want', 'know', 'tell', 'much', 'many', 'offer', 'take',
    'accept', 'provide', 'give', 'there', 'office', 'practice', 'dentist', 'dental', 'question',
}
DEFERRAL_HINTS = (
    "not sure", "don't have", "do not have", "i'm not able", "i am not able", "unable to", "no information",
    "don't know", "do not know", "isn't something i", "can't answer", "cannot answer",
)
CATEGORY_LABELS = {
    'faq': 'Frequently asked questions', 'insurance': 'Insurance & payment', 'doctor': 'Doctors & team',
    'service': 'Services & treatments', 'policy': 'Policies', 'preparation': 'Visit preparation', 'other': 'Other',
}


def scrub(text: str) -> str:
    """Remove email addresses and phone numbers before storing a patient's question."""
    text = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b', '[email]', text or '')
    text = re.sub(r'(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}', '[phone]', text)
    return re.sub(r'\s+', ' ', text).strip()


def normalize(text: str) -> str:
    return re.sub(r'\s+', ' ', re.sub(r"[^a-z0-9\s]", ' ', (text or '').lower())).strip()[:300]


def tokens(text: str) -> set:
    out = set()
    for w in normalize(text).split():
        if w in STOPWORDS or len(w) < 3:
            continue
        out.add(w[:-1] if len(w) > 4 and w.endswith('s') else w)  # crude plural folding
    return out


def match_entry(practice, question: str):
    """Best active entry for a question, or None. Conservative: needs clear word overlap."""
    from .models import KnowledgeEntry
    q = tokens(question)
    if not q:
        return None
    best, best_score = None, 0.0
    for entry in KnowledgeEntry.objects.filter(practice=practice, is_active=True)[:300]:
        t = tokens(entry.title)
        c = tokens(entry.content)
        overlap_title = len(q & t)
        overlap_all = len(q & (t | c))
        if not overlap_all:
            continue
        score = overlap_title * 2 + overlap_all
        coverage = overlap_all / len(q)
        if coverage >= 0.5 and (overlap_title >= 1 or overlap_all >= 2) and score > best_score:
            best, best_score = entry, score
    return best


def knowledge_facts(practice, limit_chars: int = 6000) -> str:
    """Practice-approved knowledge for the assistant prompt, grouped by category and size-capped."""
    from .models import KnowledgeEntry
    entries = list(KnowledgeEntry.objects.filter(practice=practice, is_active=True).order_by('category', 'title')[:200])
    if not entries:
        return ''
    lines, used, current = [], 0, None
    for e in entries:
        if e.category != current:
            current = e.category
            lines.append(f"[{CATEGORY_LABELS.get(current, current)}]")
        line = f"- {e.title}: {e.content.strip()}"
        if used + len(line) > limit_chars:
            break
        lines.append(line)
        used += len(line)
    return '\n'.join(lines)


def looks_like_deferral(answer: str) -> bool:
    low = (answer or '').lower()
    return any(h in low for h in DEFERRAL_HINTS)


def record_unanswered(practice, question: str) -> None:
    """Remember a question Concierge had to pass on. Never raises (chat must not fail on this)."""
    from .models import UnansweredQuestion
    try:
        clean = scrub(question)[:300]
        norm = normalize(clean)
        if not practice or len(norm.split()) < 2:
            return
        obj, created = UnansweredQuestion.objects.get_or_create(practice=practice, normalized=norm, defaults={'question': clean})
        if not created:
            UnansweredQuestion.objects.filter(pk=obj.pk).update(times_asked=F('times_asked') + 1)
            if obj.status == 'answered':
                # The saved answer did not match this wording: show it again so it can be improved.
                UnansweredQuestion.objects.filter(pk=obj.pk).update(status='open')
    except Exception:
        import logging
        logging.getLogger(__name__).warning('Could not record unanswered question', exc_info=True)