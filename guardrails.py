"""Guardrails: what the system must never do, checked in code.

* check_request()      - founder free-text requests (catches trick prompts such as
                          "write 50 five-star reviews")
* check_idea()         - excluded product categories (physical goods; financial,
                          investment or crypto; health or legal advice)
* check_marketing()    - generated marketing copy (fake testimonials or reviews,
                          invented user counts, fake urgency, income promises)

These are deterministic pattern checks so they cannot be talked out of a
refusal. Every refusal is logged and offers an honest alternative.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Violation:
    rule: str
    message: str
    match: str = ""

    def as_dict(self) -> dict:
        return {"rule": self.rule, "message": self.message, "match": self.match}


def _rx(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


# --- requests the system refuses -------------------------------------------------------------
REQUEST_RULES: list[tuple[str, re.Pattern[str], str]] = [
    ("fake_reviews", _rx(r"\b(fake|made[- ]up|invented|glowing|positive|5[- ]?star|five[- ]?star)\s+(customer\s+|user\s+)?(reviews?|testimonials?|ratings?|endorsements?)\b"),
     "I won't create reviews or testimonials. Real ones can only come from real customers."),
    ("fake_reviews", _rx(r"\b(write|generate|create|make|produce|invent|post|give me)\s+(me\s+|us\s+)?(\d+|some|a few|several|many|dozens of|lots of|a bunch of)\s+(\w+[- ]?){0,3}(reviews?|testimonials?|ratings?)\b"),
     "I won't create reviews or testimonials. Real ones can only come from real customers."),
    ("fake_reviews", _rx(r"\b(write|generate|create|make|invent)\s+(a\s+|some\s+)?testimonials?\b"),
     "I won't create testimonials. Real ones can only come from real customers."),
    ("fake_reviews", _rx(r"\b(post|write|leave|submit|publish)\s+(\w+\s+){0,3}(reviews?|ratings?|testimonials?)\b[^.\n]{0,40}\bas\b[^.\n]{0,30}\b(customers?|users?|buyers?|clients?|people|someone else)\b"),
     "I won't post reviews under other people's names."),
    ("fake_signups", _rx(r"\b(fake|invent|fabricate|inflate|make up|pad)\b[^.\n]{0,40}\b(sign[- ]?ups?|users?|customers?|followers?|downloads?|waitlist|numbers|metrics|traction|data|results|interviews?|quotes?|survey responses?)\b"),
     "I won't invent sign-ups, users, metrics, interviews or results. Gates only use real observations."),
    ("fake_signups", _rx(r"\b(pretend\w*|say|claim\w*)\b[^.\n]{0,30}\b(we|i)\s+(have|had|got)\s+\d[\d,]*\s*(\w+\s+)?(users?|customers?|sign[- ]?ups?|downloads?)\b"),
     "I won't claim users or sign-ups that don't exist."),
    ("fake_urgency", _rx(r"\b(countdown|fake (deadline|scarcity|timer)|only \d+ (left|spots?|seats?)|limited[- ]time offer|offer (ends|expires)|act now|last chance)\b"),
     "I won't add countdown timers or fake urgency or scarcity."),
    ("income_promise", _rx(r"\b(guarantee[sd]?|promise[sd]?)\b[^.\n]{0,50}\b(income|profit|revenue|earnings?|money|returns?|success|sales)\b"),
     "I won't promise income, sales or success. I can report evidence and uncertainty instead."),
    ("income_promise", _rx(r"\b(make|earn)\s+\$?\d[\d,.]*\s*(k|m)?\s*(per|a|/|every)\s*(day|week|month|year)\b|\bget rich\b|\bpassive income guaranteed\b"),
     "I won't promise income, sales or success."),
    ("impersonation", _rx(r"\b(pretend\w*|pose|posing|act|impersonat\w*|pass (it|this) off|sign)\b[^.\n]{0,25}\b(as|to be)\b[^.\n]{0,40}\b(founder|ceo|customer|user|client|brand|company|bank|apple|google|microsoft|amazon|meta|openai|someone else|a real person)\b"),
     "I won't pose as the founder, a customer or another brand."),
    ("impersonation", _rx(r"\b(write|post|send)\b[^.\n]{0,40}\b(as if (it'?s )?from|on behalf of|in the name of)\b"),
     "I won't write as someone else. Drafts are always labelled as drafts for the founder to send."),
    ("money_movement", _rx(r"\b(charge|bill|refund|pay out|transfer|send money|move money|withdraw)\s+(the |a |my |our |their |all |every )?(customers?|buyers?|clients?|cards?|money|funds|accounts?|payments?)\b"),
     "I don't hold, move, charge or refund money. Payments in this prototype are MOCKED."),
    ("money_movement", _rx(r"\b(process|take|collect|accept)\s+(real\s+)?(card\s+)?(payments?|money)\b"),
     "I don't take or process payments. Payments in this prototype are MOCKED."),
    ("credentials", _rx(r"\b(store|save|collect|ask(\s+\w+){0,3}\s+for|record|keep)\b[^.\n]{0,40}\b(passwords?|card numbers?|credit cards?|cvv|bank (account|details)|iban|routing numbers?|ssn)\b"),
     "I don't collect or store passwords, card numbers or bank details."),
    ("account_creation", _rx(r"\b(create|open|register|sign up for|set up)\s+(an?\s+|my\s+|our\s+|the\s+)?(stripe|paypal|shopify|gumroad|lemon ?squeezy|bank|merchant|payment)\s*(accounts?)?\b|\bsign (me|us) up\b"),
     "I don't create accounts. The founder creates any account they need."),
    ("paywall", _rx(r"\b(paywall|lock|hide)\b[^.\n]{0,40}\b(core|main|basic)\b[^.\n]{0,20}\b(features?|functionality)\b"),
     "I won't hide core features behind a paywall."),
]

# --- excluded product categories -------------------------------------------------------------
CATEGORY_RULES: list[tuple[str, re.Pattern[str], str]] = [
    ("physical_goods", _rx(r"\b(physical (product|goods|item)s?|t-?shirts?|mugs?|merch(andise)?|apparel|clothing line|jewel(le)?ry|furniture|cosmetics|candles?|hardware device|3d[- ]printed|dropshipping|print[- ]on[- ]demand|ship(ping)? (it|them|orders|products|boxes) to)\b"),
     "Physical goods are excluded: the pipeline only handles digital products."),
    ("financial", _rx(r"\b(crypto(currency|currencies)?|bitcoin|ethereum|blockchain tokens?|nfts?|token sale|defi|trading (bot|signals?)|stock picks?|investment (advice|fund|product|tips)|forex|day trading|loans?|lending|micro-?finance|insurance (product|policy|policies)|credit score repair|robo-?advisor|financial advice)\b"),
     "Financial, investment and crypto products are excluded."),
    ("health_advice", _rx(r"\b(medical advice|medical diagnos(is|es)|diagnose (illness|diseases?|symptoms|conditions|patients)|symptom checker|treatment plans?|therapy (app|sessions?|advice)|mental health (advice|treatment)|prescri(be|ption)s?|supplements?|weight[- ]loss (plan|program)|diet plans? for|cure for|healthcare advice|nutrition advice)\b"),
     "Health-advice products are excluded."),
    ("legal_advice", _rx(r"\b(legal advice|lawyer (bot|ai)|ai lawyer|contract review service|lawsuit|litigation|immigration advice|visa advice|legal consultation|draft (your )?(wills?|contracts) for|legal documents? for clients)\b"),
     "Legal-advice products are excluded."),
]

# --- generated marketing copy ------------------------------------------------------------------
MARKETING_RULES: list[tuple[str, re.Pattern[str], str]] = [
    ("testimonial", _rx(r"[\"“][^\"”]{12,240}[\"”]\s*(?:[-–—]|\bsays\b)\s*[A-Z][a-z]+"),
     "Looks like a testimonial quote attributed to a person; only real, consented quotes may be used."),
    ("star_rating", _rx(r"★{3,}|\b[45](\.\d)?\s*/\s*5\s*stars?\b|\b(five|5)[- ]star\b|\brated\s+[45](\.\d)?\b"),
     "Star ratings are only allowed when they are real and sourced."),
    ("invented_count", _rx(r"\b(join|trusted by|used by|loved by|over|more than)\s+\d[\d,.]*\s*(k|\+)?\s*\+?\s*(happy\s+)?(users?|customers?|designers?|people|teams?|founders?|members?|creators?|freelancers?|students?)\b"),
     "User counts must come from real data; none exist yet."),
    ("fake_urgency", _rx(r"\b(limited[- ]time|only \d+ (left|spots?|seats?|copies)|offer (ends|expires)|ends (tonight|today|soon)|countdown|hurry|act now|last chance|don'?t miss out|selling fast)\b"),
     "No countdown timers or fake urgency."),
    ("income_promise", _rx(r"\b(guarantee[sd]?\s+(results?|income|success|sales|clients|profit)|you will (earn|make)|make \$\d|earn \$\d|double your (income|revenue|sales)|10x your)\b"),
     "No income or success promises."),
]


def _scan(text: str, rules: list[tuple[str, re.Pattern[str], str]]) -> list[Violation]:
    found: list[Violation] = []
    seen: set[str] = set()
    for rule, pattern, message in rules:
        match = pattern.search(text or "")
        if match and rule not in seen:
            seen.add(rule)
            found.append(Violation(rule=rule, message=message, match=match.group(0)[:120]))
    return found


def check_request(text: str) -> list[Violation]:
    return _scan(text, REQUEST_RULES)


def check_idea(text: str) -> list[Violation]:
    return _scan(text, CATEGORY_RULES)


def check_marketing(text: str) -> list[Violation]:
    return _scan(text, MARKETING_RULES)


HONEST_ALTERNATIVES = {
    "fake_reviews": "After real customers use the product, I can draft a short, optional feedback request for the founder to send.",
    "fake_signups": "I can set up the waitlist and tracking so every sign-up is real and counted once.",
    "fake_urgency": "I can write a clear, honest call to action with the real availability date.",
    "income_promise": "I can show the evidence so far, its uncertainty, and the next test.",
    "impersonation": "I can draft a message for the founder to review, edit and send under their own name.",
    "money_movement": "Payments are MOCKED here; a real payment provider would be set up by the founder outside this system.",
    "credentials": "I can collect only an email address for the waitlist, with consent.",
    "account_creation": "I can list the accounts the founder might need and what each costs.",
    "paywall": "Core features stay open; I can suggest optional extras instead.",
}


def refusal_message(violations: list[Violation]) -> str:
    lines = ["I can't do that. It breaks a rule this system never breaks:"]
    for v in violations:
        lines.append(f"- {v.message}")
    alts = [HONEST_ALTERNATIVES[v.rule] for v in violations if v.rule in HONEST_ALTERNATIVES]
    if alts:
        lines.append("")
        lines.append("What I can do instead: " + " ".join(dict.fromkeys(alts)))
    return "\n".join(lines)
