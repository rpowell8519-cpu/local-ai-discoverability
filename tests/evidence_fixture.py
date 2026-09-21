"""A coworking client that lacks pricing, FAQ and booking information beside three visible competitors that have them.

Shaped exactly like what the website audit and review import save, so the real analysis engines run on it.
"""
import json

import pandas as pd

T = "target"
LEADERS = ["l1", "l2", "l3"]
NAMES = {T: "WRAP Coworking", "l1": "Plus X Innovation Brighton", "l2": "Runway East Brighton", "l3": "PLATF9RM Brighton"}
PROPOSITIONS = ["Coworking", "Private offices", "Meeting rooms", "Event spaces", "Team away days", "Sustainable working space", "Flexible membership"]


def _audit(pid, day="2026-09-10", **flags):
    base = dict(id=f"run-{pid}", google_place_id=pid, business_name=NAMES[pid], audit_status="completed", is_https=True, has_title=True,
                has_meta_description=True, has_canonical=True, has_local_business_schema=False, has_contact_signals=True,
                has_address_signals=True, has_service_pages=True, has_menu_page=False, has_pricing_page=False, has_faq_content=False,
                has_booking_link=False, has_social_links=True, sitemap_url="x", pages_discovered=20, pages_crawled=20, robots_status="found",
                requested_url=f"https://{pid}.example/", final_url=f"https://{pid}.example/", schema_types="[]", social_links="[]", issues="[]",
                website_completeness_score=60, started_at=pd.Timestamp(day), completed_at=pd.Timestamp(day))
    base.update(flags)
    return base


def audits():
    return pd.DataFrame([
        _audit(T),
        _audit("l1", "2026-09-08", has_pricing_page=True, has_faq_content=True, has_booking_link=True, has_local_business_schema=True),
        _audit("l2", "2026-09-09", has_pricing_page=True, has_booking_link=True),
        _audit("l3", "2026-09-10", has_pricing_page=True, has_faq_content=True, has_booking_link=True),
    ])


def _page(url, title, text):
    return dict(url=url, final_url=url, http_status=200, page_title=title, meta_description="", canonical_url=url, headings=json.dumps([title]),
                schema_types="[]", detected_signals="{}", issues="[]", internal_links_count=10, text_excerpt=text, crawled_at=pd.Timestamp("2026-09-10"))


def pages_by_run():
    return {
        "run-target": pd.DataFrame([_page("https://target.example/", "WRAP coworking Brighton", "Flexible coworking desks and private offices in Brighton. Contact us."),
                                    _page("https://target.example/spaces", "Our spaces", "Private offices and meeting rooms available. Call to enquire.")]),
        "run-l1": pd.DataFrame([_page("https://l1.example/", "Plus X coworking", "Coworking memberships from £150 a month. Book a tour. Sustainable working offices. Event spaces and team away days."),
                                _page("https://l1.example/pricing", "Pricing", "Hot desk £150, dedicated desk £250, private office from £600. FAQ: can I bring a guest? Book online.")]),
        "run-l2": pd.DataFrame([_page("https://l2.example/", "Runway East coworking", "Coworking and private offices from £199. Book a viewing. Meeting rooms by the hour. Team away days.")]),
        "run-l3": pd.DataFrame([_page("https://l3.example/", "PLATF9RM", "Coworking, offices and events in Brighton. Prices from £120. FAQ. Book a desk. Sustainable workspace with green credentials.")]),
    }


def reviews(target=True, leaders=True):
    rows = []
    def row(pid, i, text, rating, reply):
        rows.append(dict(google_place_id=pid, business_name=NAMES[pid], review_id=f"{pid}{i}", review_text=text, review_rating=rating, review_timestamp=1,
                         review_datetime_utc=pd.Timestamp("2026-08-01"), review_likes=0, author_title="a", author_reviews_count=1, owner_answer=reply, review_link=""))
    if target:
        for i, (t, r) in enumerate([("Nice space but the wifi was slow and no one answered the phone", 3), ("Friendly staff, good coffee", 5),
                                    ("Hard to find prices, had to email twice to book a room", 3)]):
            row(T, i, t, r, None)
    if leaders:
        for p in LEADERS:
            for i, (t, r) in enumerate([("Booked a meeting room online in seconds, great value", 5), ("Lovely community events and friendly staff", 5),
                                        ("Easy to book and clear pricing", 4)]):
                row(p, i, t, r, "Thanks!")
    return pd.DataFrame(rows)


def leaders():
    return [{"google_place_id": p, "business_name": NAMES[p], "recommendations": n} for p, n in (("l1", 30), ("l2", 23), ("l3", 33))]
