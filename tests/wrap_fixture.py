"""Client summary data shaped like the first real WRAP run.

The first live run failed with "Page 4 is too long" because comparison names and evidence lines wrap.
These are that run's numbers, so the failure stays covered.
"""
def wrap_summary(**over):
    qs = [("q1", "Coworking", "Recommend places in Brighton for coworking.", 3),
          ("q2", "Private offices", "Recommend places in Brighton for private offices.", 4),
          ("q3", "Meeting rooms", "Recommend places in Brighton for meeting rooms.", 1),
          ("q4", "Event spaces", "Recommend places in Brighton for event spaces.", 0),
          ("q5", "Team away days", "Recommend places in Brighton for team away days.", 0),
          ("q6", "Co working near Brighton station", "Recommend places for co working near Brighton station", 9),
          ("q7", "Sustainable working offices in Brighton", "Sustainable working offices in Brighton", 7),
          ("q8", "Flexible working spaces in Brighton", "Flexible working spaces in Brighton", 6)]
    d = {
        "schema_version": 1, "business_name": "WRAP- Coworking, Meeting Rooms & Offices", "short_name": "WRAP",
        "draft": True, "location": "Brighton and Hove", "audit_date": "2026-09-21",
        "target_id": "ChIJO49ZdfyPdUgRx2HnXZqBjD0", "repetitions": 3, "counting_rule": "unique_business_per_response",
        "web_search_enabled": True, "owner_reviewed_questions": True, "evidence_basis": "saved_response_records",
        "source_note": "Saved AI visibility run fef3cf4a-5e91-4b3d-8f2f-23172febd2a5, tested 2026-09-21. Counts are calculated from the saved answers.",
        "providers": [{"id": "claude", "name": "Claude", "model": "claude-sonnet-5", "complete": 24, "appearances": 8},
                      {"id": "gemini", "name": "Gemini", "model": "gemini-3.6-flash", "complete": 24, "appearances": 10},
                      {"id": "openai", "name": "OpenAI", "model": "gpt-5.6-terra", "complete": 24, "appearances": 12}],
        "questions": [{"id": i, "label": l, "text": t, "complete": 9, "appearances": a} for i, l, t, a in qs],
        "businesses": [{"id": "ChIJO49ZdfyPdUgRx2HnXZqBjD0", "name": "WRAP- Coworking, Meeting Rooms & Offices", "appearances": 30},
                       {"id": "plusx", "name": "Plus X Innovation Brighton", "appearances": 30},
                       {"id": "runway", "name": "Runway East Brighton | Office Space", "appearances": 23},
                       {"id": "platf9rm", "name": "PLATF9RM Brighton - Coworking, Offices & Events", "appearances": 8}],
        "evidence": [
            {"id": "E1", "observation": "robots.txt does not block the main AI search crawlers (ChatGPT search, Claude search, Perplexity, Google Search, Bing and Copilot).",
             "source": "https://wrap.space/robots.txt, read on 21 September 2026"},
            {"id": "E2", "observation": "The website shows the same postcode as the Google listing.",
             "source": "https://wrap.space/coworking-brighton/private-offices-and-meeting-rooms, saved 13 September 2026"}],
        "actions": [
            {"id": "action-1", "title": "Make event spaces easy to find and act on", "question_id": "q4", "status": "suggested_check", "evidence_ids": [],
             "task": "Review the pages and profiles that cover “Event spaces”. Where they are missing or unclear, add spaces and capacity, prices, availability, how to book a visit or a room, and facilities. Include only details the team can verify.",
             "owner": "Business owner supplies the facts; website provider publishes them",
             "done_when": "A customer can find the details and complete an enquiry or booking; the team has tested that route"},
            {"id": "action-2", "title": "Make team away days easy to find and act on", "question_id": "q5", "status": "suggested_check", "evidence_ids": [],
             "task": "Review the pages and profiles that cover “Team away days”. Where they are missing or unclear, add spaces and capacity, prices, availability, how to book a visit or a room, and facilities. Include only details the team can verify.",
             "owner": "Business owner supplies the facts; website provider publishes them",
             "done_when": "A customer can find the details and complete an enquiry or booking; the team has tested that route"},
            {"id": "action-3", "title": "Keep your business details accurate and consistent", "question_id": "q6", "status": "suggested_check", "evidence_ids": [],
             "task": "Your website and Google listing agree on the postcode. Check that your name, opening times, services and links also match on Google Business Profile, Apple Business, Bing Places and any workspace listing site you use. Correct differences and remove duplicate or out-of-date listings.",
             "owner": "Business owner, with the website provider", "done_when": "Details agree everywhere they appear"}],
        "limitations": ["2 business name(s) in the answers could not be matched to a verified business and are not shown.",
                        "A reviewer confirmed that the AI answers “WRAP” refer to this business."],
    }
    d.update(over)
    return d
