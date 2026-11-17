GATE FAILED: independent_discussions 0/5 (0%). Recommendation: STOP or PIVOT_BACK.

```
=== GATE REPORT ===
Phase / Step: 1.3 Define the market (Phase 1: Discover)
Gate type(s): A + E
Pre-set threshold(s): Independent public discussions of the problem in the last 24 months (independent_discussions) >= 5 discussions; Members of the largest verified community where the segment gathers (published audience, not eligible reach) (largest_community_members) >= 1000 members (locked on 2026-11-17 by founder, v1)
Actual result(s): independent_discussions = 0 (fail); largest_community_members = 201716 (pass) (source: Desk research: 1 evidence rows from free public sources (github, hacker_news, reddit, stackexchange, wikipedia, world_bank).)
Status: FAILED (0% of target)
Outcome: STOP (alternative: PIVOT_BACK)
Reasoning: Missed: 0/5 independent public discussions of the problem in the last 24 months (0% of target). The largest community criterion was met (201,716 members > 1,000), but the independent discussions metric fell below the locked stop band of 25%, triggering a STOP outcome.
What would change my mind: Evidence of at least 5 independent public discussions in the last 24 months would reverse the recommendation.
Founder decision required: yes - Recommended outcome: STOP. Accept it, or choose another outcome with a reason (logged as FOUNDER_OVERRIDE).
Log ID(s): P1-S3-0021
===================
```

## Measurement details

- **independent_discussions**: {'value': 0, 'by_source': {}, 'window_months': 24, 'method': 'rows labelled relevant by the model, counted once per thread (independence group) in code'}
- **largest_community_members**: {'value': 201716, 'community': {'name': 'graphicdesign Stack Exchange', 'url': 'https://graphicdesign.stackexchange.com', 'members': 201716, 'source': 'stackexchange', 'evidence_id': 'E-034', 'verified': True}, 'note': 'published audience, not eligible reach'}
- **coverage_notes**: ['reddit unavailable (blocked or rate-limited); Reddit discussions and subscriber counts were not checked']
