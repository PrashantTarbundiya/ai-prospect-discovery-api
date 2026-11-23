"""Run against a configured local server. Logs only counts, timings and coverage."""
import json
import time

import httpx

QUERIES = (
    "Football lovers in Washington DC in USA",
    "Digital marketing agency owners in New York USA",
    "Startup founders in London UK",
    "Cricket lovers in Ahmedabad India",
    "Restaurant owners in Dubai UAE",
)


def main():
    failed = False
    with httpx.Client(base_url="http://127.0.0.1:4000", timeout=180) as client:
        for query in QUERIES:
            start = time.monotonic()
            try:
                response = client.post("/prospect-discovery", json={"query": query})
                response.raise_for_status()
                data = response.json()
                if data["query"] != query or data["success"] is not True or data["total_prospects"] != len(data["prospects"]):
                    raise ValueError("Response contract mismatch")
                print(json.dumps({"query": query, "count": data["total_prospects"],
                                  "seconds": round(time.monotonic() - start, 2),
                                  "unavailable": response.headers.get("X-Unavailable-Sources", "")}))
            except (httpx.HTTPError, ValueError, KeyError) as error:
                print(f"{query} | {error}")
                failed = True
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
