# Prospect Discovery API

A local FastAPI service for finding public profiles by audience and location. OpenRouter interprets the audience description. Serper retrieves Google-indexed pages, and Python evaluates the evidence in each result. The service returns one JSON record per resolved identity.

## Run on Windows

From PowerShell:

```powershell
git clone https://github.com/PrashantTarbundiya/ai-prospect-discovery-api.git
cd ai-prospect-discovery-api
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

This checkout uses a private `.env` for credentials. For a fresh checkout, copy `.env.example` to `.env`, add the two keys and keep the configured model ID:

```dotenv
OPENROUTER_API_KEY=
OPENROUTER_MODEL=nvidia/nemotron-3-ultra-550b-a55b:free
SERPER_API_KEY=
```

Get your keys from [OpenRouter](https://openrouter.ai/settings/keys) and [Serper](https://serper.dev/). Environment variables take precedence over the file. Restart the server after changes.

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 4000
```

Open [Fieldwork](http://localhost:4000/). **Find a person** accepts a published full name or an @handle. Select **Find profiles** and use the source URL and indexed description to distinguish people with the same name. **Topic or audience** uses OpenRouter to interpret broader searches. Both modes support JSON export and the last 20 completed searches in tab history. [Interactive API documentation](http://localhost:4000/docs)

## Request and response

To look up a specific person, send `{"query":"Guido van Rossum","mode":"person"}` or `{"query":"@gvanrossum","mode":"person"}`. This mode only requires a Serper key. It searches the literal name or handle and checks it against indexed identity pages locally. Same-name matches are possible and ownership should be checked at the source. Results can include an indexed `description`. Searches without a mode keep the audience-discovery behavior.

Enter a topic such as `new gemini model` to discover profiles discussing or working on it. A named audience and a location are optional. Results link to public profiles; freshness of model releases is outside the profile search.

```powershell
$body = @{ query = 'Startup founders in London UK' } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri 'http://localhost:4000/prospect-discovery' -ContentType 'application/json' -Body $body | ConvertTo-Json -Depth 6
```

Example of a successful search with no qualifying evidence:

```json
{
  "success": true,
  "query": "Startup founders in London UK",
  "total_prospects": 0,
  "prospects": []
}
```

Example of a populated response from the **synthetic test fixture**:

```json
{
  "success": true,
  "query": "Startup founders in London UK",
  "total_prospects": 1,
  "prospects": [{
    "name": "Sample Person",
    "location": "London",
    "social_link": [
      {"platform": "LinkedIn", "link": "https://linkedin.com/in/fixture-person"},
      {"platform": "Email", "link": "mailto:sample@example.com"}
    ]
  }]
}
```

The production pipeline has no fixture fallback. HTTP 422 covers invalid audience requests, 429 covers excess concurrent requests, 502 covers malformed or unsuccessful upstream responses, 503 covers configuration, quota or provider unavailability, and 504 covers provider timeouts. If some searches fail, a 200 response carries the affected scopes in `X-Unavailable-Sources`. A total provider failure returns an error.

## Discovery coverage

| Output platform | Accepted evidence |
| --- | --- |
| Google | Indexed first-party homepage, about or contact page with identity and ownership cues. The link points to the website. |
| LinkedIn | Public `/in/` and `/company/` records, filtered for target type. |
| X | Public account handle, including legacy Twitter URLs. |
| YouTube | Channel ID, handle, user or custom channel page. |
| Instagram | Account profile URL and indexed biography. |
| Facebook | Named profile or page URL, or a numeric `profile.php?id=` URL. |
| Threads | Public handle on threads.com or threads.net. |
| WhatsApp | Explicitly labelled public wa.me or WhatsApp API number link in the qualifying profile excerpt. |
| Email / Phone | Explicitly attributed address or international phone in that excerpt. Output uses `mailto:` or `tel:`. |

The registry in `app/platforms.py` defines each social platform's search scope, hostnames and profile-route shape. New social adapters can reuse the search, evidence and merge pipeline. Search uses Serper's organic results and requires an active search key. The engine reads provider-returned titles, URLs and snippets. It has no platform login or profile-page crawler.

**What a match means.** The model proposes required concepts with alternatives and the narrowest requested place. Local checks look for evidence of every concept, the requested place when supplied, a plausible profile title, and person or organization signals. Names and contact values come from the result itself. Links are validated against the index and expected route shapes. Indexing can lag. The service does not verify account control, mailbox deliverability, telephone ownership or reachability. Geographic matching is lexical and can miss alternate spellings or confuse places with the same name. Titles and snippets may be shortened, ambiguous or unavailable. Non-English queries are accepted, although ownership and contact cues currently favor English. Missing evidence can legitimately yield zero results.

**Identity resolution.** The same canonical profile URL forms one identity. A same-name cross-platform merge also needs an explicitly self-labelled link to another independently discovered profile. Equal names, shared company inboxes, or similar handles alone do not cause a merge. This favors precision and can leave unlinked duplicates.

**Contact validity.** Email syntax is checked using email-validator. International phone numbers require an explicit country calling prefix and a plausible E.164-shaped digit count. Domestic numbers with ambiguous country context are omitted. WhatsApp numbers are taken from an explicitly published link.

## OpenRouter model research and recommendation

The configured model is the user's selection, **NVIDIA Nemotron 3 Ultra (free)** through OpenRouter. Its endpoint advertises function calling with required tool choice. The app asks for a typed intent or a rejection, then validates the function arguments with Pydantic. Retrieved names, snippets and contact details stay out of the LLM request. Enter audience descriptions without personal or confidential data, in line with the free endpoint's data-use notice. [Model card](https://openrouter.ai/nvidia/nemotron-3-ultra-550b-a55b:free) · [Endpoint capabilities](https://openrouter.ai/api/v1/models/nvidia/nemotron-3-ultra-550b-a55b:free/endpoints)

Prices are USD per million input/output tokens, checked against OpenRouter listings during implementation. Timing figures for alternatives are provider telemetry snapshots. Task-fit judgments are estimates. Accuracy on these five queries has not been measured against live models.

| Model | Input / output | Context | Speed evidence | Structured output and expected task fit |
| --- | --- | --- | --- | --- |
| NVIDIA Nemotron 3 Ultra free | $0 / $0 | 1M | Endpoint listing had no recent latency or throughput value | Tool calling with required selection and local JSON validation. Suitable for decomposing a query into concepts. Reasoning may add delay. |
| Google Gemini 2.5 Flash-Lite | $0.10 / $0.40 | 1M | Google AI Studio snapshot around 0.44 s latency and 175 tokens/s | Supports structured output and tools. Low-cost candidate for audience parsing and a manually selected fallback. |
| OpenAI GPT-4.1 Mini | $0.40 / $1.60 | 1M | OpenAI snapshot around 0.77 s latency and 67 tokens/s | Supports structured output and tools. Candidate to compare on complex roles, ambiguous locations and instruction following. |

Sources: [Gemini listing](https://openrouter.ai/google/gemini-2.5-flash-lite), [GPT-4.1 Mini listing](https://openrouter.ai/openai/gpt-4.1-mini), [OpenRouter structured-output guide](https://openrouter.ai/docs/guides/features/structured-outputs).

**Cost and speed.** On a cache miss, budget roughly 700–1,600 input tokens for instructions, tool schemas and query, and 200–700 output tokens for a short intent including variable reasoning usage. These are estimates. At 1,200 input and 400 output tokens the LLM portion costs $0 on the configured free endpoint, about $0.00028 on Flash-Lite, or $0.00112 on GPT-4.1 Mini. A complete uncached discovery also consumes seven Serper searches before any limited retries. Multiply seven by the unit price on your search plan. Search costs are independent of the free model. [Serper plans](https://serper.dev/)

The five live checks with the selected model took 15.7–19.7 seconds each, with a median of 18.2 seconds from request to response. These measurements include query interpretation and search. They cover one local run. Free-route queueing, rate limits and retries can change the timing. The HTTP client sets 60-second LLM and 12-second search timeouts per attempt. See [live run results](checks/live-results.md).

**Selection.** Use Nemotron for this prototype. Try Flash-Lite manually if free-route availability or latency is unsuitable. To evaluate accuracy before switching, run the same five queries with a fixed search evidence set, review extracted intent and relevant identities against a human-labelled set, and compare precision, recall, latency and cost. Complete responses are cached in memory for five minutes, up to 128 queries per process. Source filtering and matching are local, so costs do not grow with the number of candidate profiles sent to the LLM. Upstream 429/503 responses get at most one short retry. Partial or failed results are not cached.

## Verification and deployment

### Streamlit Community Cloud

Deploy the public GitHub repository with `streamlit_app.py` as the entrypoint and Python 3.13. In Advanced settings → Secrets, add the root-level TOML strings `OPENROUTER_API_KEY`, `SERPER_API_KEY` and `OPENROUTER_MODEL` using the values from your private configuration. Streamlit exports root-level secrets as environment variables. Keep the keys in the host's secret store.

The root URL opens the Streamlit search form. Append `/docs` for Swagger or send JSON to `POST /prospect-discovery` on the same host. The Streamlit launcher starts the existing FastAPI service through its ASGI lifespan. Both entry points use the same discovery implementation.

To preview the deployment locally, install `requirements.txt` and run `python -m streamlit run streamlit_app.py`. Free Community Cloud hosting and provider search quotas are separate. [Community Cloud deployment](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy)

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
# With the server running and both keys configured:
.\.venv\Scripts\python.exe checks\live_queries.py
```

The offline suite sends real HTTP requests through FastAPI's test client and replaces only outbound provider HTTP traffic. It exercises all five assessment queries, provider errors, local validation and cross-platform matches. The live runner sends the five queries through localhost and records result counts, elapsed time and partial coverage. See `checks/offline-test-log.txt` for the local test run. Live discovery requires your API credentials.

For a Python web host, install `requirements.txt`, set the three environment values as host secrets or configuration, and start `python -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT"` on a POSIX host that supplies `PORT`. Expose `/docs` for the interactive demo and `/prospect-discovery` for POST requests. Limit public access or request spend at the gateway before opening a credential-backed demo. The checked-in source is suitable for a local run or deployment to a Python host.
