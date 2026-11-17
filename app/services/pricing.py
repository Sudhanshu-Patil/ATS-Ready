"""What is for sale, what a credit buys, and the per-job limits that keep a credit from becoming unlimited AI use.

One job credit unlocks one job (one job description) completely, within the caps below. A resume-only credit unlocks
just that job's resume. Typical model cost of a fully used job is about 2 rupees and the caps keep the worst case near
5 rupees, so the cheapest pack (10 rupees) can never lose money. Caps are config so they can be tuned from real usage
(Admin page, tokens per kind) without a code change.
"""
from typing import Dict

# Free on signup (after the email is verified), once per person.
SIGNUP_JOB_CREDITS = 1
SIGNUP_RESUME_CREDITS = 2
# The person who invited someone gets this when the invited person verifies and starts their first job.
REFERRAL_JOB_CREDITS = 1
REFERRAL_REWARD_CAP = 25

# Credit packs. Credits never expire. Prices in minor units (paise / cents), shown GST-inclusive.
PACKS: Dict[str, Dict] = {
    "single":  {"label": "Single",   "credits": 1,  "inr": 1000,  "usd": 0},
    "starter": {"label": "Starter",  "credits": 6,  "inr": 4900,  "usd": 299},
    "hunt":    {"label": "Job hunt", "credits": 15, "inr": 9900,  "usd": 599},
    "power":   {"label": "Power",    "credits": 35, "inr": 19900, "usd": 1199},
}

# What one unlocked job may use, per kind of generation. "answers" counts questions.
JOB_CAPS: Dict[str, int] = {
    "resume": 3, "cover_letter": 3, "answers": 40, "interview_prep": 2, "referral": 5, "follow_up": 3,
}

# Level a job must be unlocked to for each kind: a resume-only credit covers just the resume.
REQUIRED_LEVEL: Dict[str, str] = {
    "resume": "resume", "cover_letter": "full", "answers": "full", "interview_prep": "full",
    "referral": "full", "follow_up": "full",
}

LABELS: Dict[str, str] = {
    "resume": "resumes", "cover_letter": "cover letters", "answers": "answers", "interview_prep": "interview preps",
    "referral": "referral messages", "follow_up": "follow-up drafts",
}


def catalog() -> Dict:
    """What the pricing UI shows."""
    return {
        "packs": [{"id": pid, "label": p["label"], "credits": p["credits"], "inr": p["inr"], "usd": p["usd"],
                   "per_credit_inr": round(p["inr"] / 100 / p["credits"], 1)} for pid, p in PACKS.items()],
        "signup": {"job": SIGNUP_JOB_CREDITS, "resume": SIGNUP_RESUME_CREDITS},
        "referral": {"job": REFERRAL_JOB_CREDITS, "cap": REFERRAL_REWARD_CAP},
        "job_includes": JOB_CAPS,
    }
