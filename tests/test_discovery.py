import json
import unittest

import httpx
from fastapi.testclient import TestClient

from app.evidence import extract, published_contacts
from app.main import create_app
from app.platforms import profile_link
from app.providers import DEFAULT_MODEL, Hit, Settings
from app.schemas import Intent
from checks.live_queries import QUERIES

# Synthetic provider fixtures. Identifiers and snippets are for tests only.
CASES = [
    ("football", "fan", "Washington DC", "District of Columbia", "USA"),
    ("digital marketing agency", "owner", "New York", "New York", "USA"),
    ("startup", "founder", "London", None, "UK"),
    ("cricket", "fan", "Ahmedabad", "Gujarat", "India"),
    ("restaurant", "owner", "Dubai", "Dubai", "UAE"),
]


def intent_for(i):
    interest, role, city, state, country = CASES[i]
    return {"interest": interest, "audience": f"{interest} {role}", "target_type": "individual",
            "requirements": [[interest], [role]],
            "location": {"city": city, "state": state, "country": country, "aliases": [city]}}


def hit_for(i):
    interest, role, city, _, _ = CASES[i]
    return {"title": "Sample Person - LinkedIn", "link": "https://www.linkedin.com/in/fixture-person/?trk=feed",
            "snippet": f"I am a {interest} {role} based in {city}. My email: sample@example.com. "
                       "My Instagram: https://instagram.com/fixture_person."}


class Providers:
    def __init__(self, i=0):
        self.i = i
        self.calls = []
        self.results = [hit_for(i)]
        self.unavailable = set()
        self.fail_intent = None

    def __call__(self, request):
        payload = json.loads(request.content)
        self.calls.append((request.url.host, payload))
        if request.url.host == "openrouter.ai":
            if self.fail_intent is not None:
                return httpx.Response(200, json=self.fail_intent)
            args = json.dumps(intent_for(self.i))
            return httpx.Response(200, json={"choices": [{"message": {"tool_calls": [
                {"type": "function", "function": {"name": "record_intent", "arguments": args}}]}}]})
        if request.url.host != "google.serper.dev":
            raise AssertionError("Unexpected outbound destination")
        if any(scope in payload["q"] for scope in self.unavailable):
            return httpx.Response(429, headers={"Retry-After": "90"})
        return httpx.Response(200, json={"organic": self.results})


def client_for(providers, settings=None):
    config = settings or Settings("mock-router", "mock-search", DEFAULT_MODEL)
    return TestClient(create_app(config, httpx.MockTransport(providers)))


class DiscoveryTests(unittest.TestCase):
    def test_five_assessment_queries(self):
        for i, query in enumerate(QUERIES):
            with self.subTest(query=query):
                upstream = Providers(i)
                with client_for(upstream) as client:
                    response = client.post("/prospect-discovery", json={"query": query})
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertEqual(response.json(), {"success": True, "query": query, "total_prospects": 1,
                        "prospects": [{"name": "Sample Person", "location": CASES[i][2], "social_link": [
                            {"platform": "LinkedIn", "link": "https://linkedin.com/in/fixture-person"},
                            {"platform": "Email", "link": "mailto:sample@example.com"}]}]})
                    self.assertEqual(len(upstream.calls), 8)
                    host, model = upstream.calls[0]
                    self.assertEqual(host, "openrouter.ai")
                    self.assertEqual(model["model"], DEFAULT_MODEL)
                    self.assertEqual(model["tool_choice"], "required")
                    self.assertEqual(model["tools"][0]["function"]["name"], "record_intent")
                    self.assertNotIn("Sample Person", json.dumps(model))
                    for _, body in upstream.calls[1:]:
                        self.assertIn(CASES[i][2], body["q"])
                    cached = client.post("/prospect-discovery", json={"query": query.upper()})
                    self.assertEqual(cached.json()["query"], query.upper())
                    self.assertEqual(len(upstream.calls), 8)

    def test_consolidation_and_same_name_collision(self):
        upstream = Providers()
        upstream.results += [
            {**hit_for(0), "link": "https://instagram.com/fixture_person/"},
            {**hit_for(0), "link": "https://x.com/otherfixture", "snippet": "Football fan in Washington DC."},
        ]
        with client_for(upstream) as client:
            data = client.post("/prospect-discovery", json={"query": QUERIES[0]}).json()
        self.assertEqual(data["total_prospects"], 2)
        self.assertEqual([x["platform"] for x in data["prospects"][0]["social_link"]], ["LinkedIn", "Email", "Instagram"])

    def test_empty_and_partial(self):
        upstream = Providers()
        upstream.results = []
        upstream.unavailable.add("site:x.com")
        with client_for(upstream) as client:
            response = client.post("/prospect-discovery", json={"query": QUERIES[0]})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["X-Unavailable-Sources"], "X")
            self.assertEqual(response.json()["prospects"], [])
            upstream.unavailable.clear()
            upstream.results = [hit_for(0)]
            response = client.post("/prospect-discovery", json={"query": QUERIES[0]})
            self.assertNotIn("X-Unavailable-Sources", response.headers)
            self.assertEqual(response.json()["total_prospects"], 1)

    def test_limits_and_provider_errors(self):
        upstream = Providers()
        upstream.unavailable.add("")
        with client_for(upstream) as client:
            res = client.post("/prospect-discovery", json={"query": QUERIES[0]})
            self.assertEqual(res.status_code, 503)
            upstream.fail_intent = {"choices": []}
            res = client.post("/prospect-discovery", json={"query": QUERIES[0]})
            self.assertEqual(res.status_code, 502)

    def test_timeout(self):
        def timeout(request):
            raise httpx.ReadTimeout("test timeout", request=request)
        with client_for(timeout) as client:
            self.assertEqual(client.post("/prospect-discovery", json={"query": QUERIES[0]}).status_code, 504)

    def test_person_search_uses_display_name_not_mentions(self):
        upstream = Providers()
        upstream.results = [
            {"title": "José García - Engineer | LinkedIn", "link": "https://linkedin.com/in/jose-one",
             "snippet": "Builds open source tools."},
            {"title": "José García (@jose_two) • Instagram", "link": "https://instagram.com/jose_two"},
            {"title": "Another Person - LinkedIn", "link": "https://linkedin.com/in/another",
             "snippet": "I worked with José García."},
            {"title": "José García - Instagram", "link": "https://instagram.com/p/post", "snippet": "José García"},
            {"title": "José García - Fan account", "link": "https://x.com/fan", "snippet": "Fan account"},
        ]
        with client_for(upstream, Settings("", "test-search", DEFAULT_MODEL)) as client:
            body = {"mode": "person", "query": "jose garcia"}
            response = client.post("/prospect-discovery", json=body)
            self.assertEqual(response.status_code, 200, response.text)
            people = response.json()["prospects"]
            self.assertEqual(len(people), 2)
            self.assertEqual(people[0]["description"], "Builds open source tools.")
            self.assertEqual(people[1]["social_link"][0]["link"], "https://instagram.com/jose_two")
            self.assertEqual({host for host, _ in upstream.calls}, {"google.serper.dev"})
            self.assertTrue(all('"jose garcia"' in q["q"] for _, q in upstream.calls))
            handle = client.post("/prospect-discovery", json={"query": "@jose_two", "mode": "person"})
            self.assertEqual(handle.json()["total_prospects"], 1)
            # A person result must never satisfy a cached audience search of the same text.
            self.assertEqual(client.post("/prospect-discovery", json={"query": "jose garcia"}).status_code, 503)

    def test_topic_without_audience_or_location(self):
        plan = {"audience": "Gemini developers", "interest": "Gemini", "target_type": "either",
                "location": {"city": None, "state": None, "country": None, "aliases": []},
                "requirements": [["Gemini"]]}
        upstream = Providers()
        upstream.fail_intent = {"choices": [{"message": {"tool_calls": [{"function": {
            "name": "record_intent", "arguments": json.dumps(plan)}}]}}]}
        upstream.results = [{**hit_for(0), "snippet": "I build apps using Gemini."}]
        with client_for(upstream) as client:
            for query in ("new gemini model", "AI"):
                response = client.post("/prospect-discovery", json={"query": query})
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()["total_prospects"], 1)
                self.assertIsNone(response.json()["prospects"][0]["location"])

    def test_semantically_invalid_query(self):
        upstream = Providers()
        upstream.fail_intent = {"choices": [{"message": {"tool_calls": [{"function": {"name": "reject_query", "arguments": "{}"}}]}}]}
        with client_for(upstream) as client:
            self.assertEqual(client.post("/prospect-discovery", json={"query": "good morning"}).status_code, 422)
        self.assertEqual(len(upstream.calls), 1)

    def test_config_input_and_docs(self):
        upstream = Providers()
        with client_for(upstream, Settings("", "", DEFAULT_MODEL)) as client:
            for body in [{}, {"query": "  "}, {"query": "12345"}, {"query": "a" * 401}]:
                self.assertEqual(client.post("/prospect-discovery", json=body).status_code, 422)
            self.assertEqual(client.post("/prospect-discovery", json={"query": QUERIES[0]}).status_code, 503)
            self.assertEqual(list(client.get("/openapi.json").json()["paths"]), ["/prospect-discovery"])
            self.assertEqual(client.get("/docs").status_code, 200)
            home = client.get("/", follow_redirects=False)
            self.assertEqual(home.status_code, 200)
            self.assertIn('id="query-form"', home.text)
            for asset in ["style.css", "discovery.js", "atlas.webp", "mark.svg"]:
                self.assertEqual(client.get("/assets/" + asset).status_code, 200)
            self.assertEqual(upstream.calls, [])

    def test_relevance_and_contact_ownership(self):
        intent = Intent(**intent_for(2))
        for snippet in ["Owner based in London", "Startup founder based in Leeds",
                        "Startup investor, not a founder, in London", "Startup founder visiting London"]:
            self.assertIsNone(extract(Hit("Sample Person - LinkedIn", hit_for(0)["link"], snippet), intent), snippet)
        self.assertEqual(published_contacts("Contact my agent at agent@example.com"), [])
        self.assertEqual(published_contacts("My phone: 123. My email: malformed@."), [])
        contacts = published_contacts("My phone: +44 20 7946 0123. My WhatsApp: https://wa.me/442079460123.")
        self.assertEqual([x.link for x in contacts], ["tel:+442079460123", "https://wa.me/442079460123"])

    def test_platform_routes(self):
        for name, url in [
            ("LinkedIn", "https://in.linkedin.com/in/fixture"), ("X", "https://twitter.com/fixture"),
            ("YouTube", "https://youtube.com/@fixture"), ("Instagram", "https://instagram.com/fixture"),
            ("Facebook", "https://facebook.com/profile.php?id=123456"),
            ("Threads", "https://threads.net/@fixture"), ("Google", "https://example.com/about"),
        ]:
            self.assertEqual(profile_link(url).platform, name)
        for url in ["https://google.com/search?q=test", "https://linkedin.com/jobs/fixture", "https://x.com/i",
                    "https://youtube.com/watch?v=fixture", "https://instagram.com/p/fixture",
                    "https://facebook.com/groups/fixture", "https://threads.com/@a/post/123",
                    "https://linkedin.com.evil.example/in/fixture", "http://127.0.0.1/",
                    "javascript:alert(1)", "https://evil.example@x.com/name"]:
            self.assertIsNone(profile_link(url), url)
