# Prospect Discovery API

## Design before implementation

The service accepts one audience description at `POST /prospect-discovery`. FastAPI's interactive `/docs` is the local interface. The public contract contains the original query, total, and prospect records with a name, optional location and an array of labelled links.

1. Validate and normalize the input. Ask the user to select the OpenRouter model. Keep its ID and both provider keys in environment configuration.
2. Use the selected NVIDIA Nemotron 3 Ultra free endpoint to call a typed function for audience, interest, geography, target type and groups of equivalent search terms. Pydantic validates the arguments.
3. Run one general Google search and six domain-scoped searches through Serper with bounded parallelism. Keep each result's title, indexed URL and excerpt together. A failed source can be skipped if another source succeeds.
4. Apply the model's concept groups to titles and snippets locally. Require evidence for each concept and the most specific requested place. Extract names from profile titles and contacts from explicitly labelled source text. This adaptation keeps discovered personal data out of NVIDIA's free endpoint.
5. Resolve duplicate canonical URLs and cross-referenced profiles. Shared names, phone numbers and generic inboxes are insufficient to establish identity across records.
6. Cache successful complete responses briefly. Document partial coverage in response headers. Keep keys and contact data out of application logs.

## Implementation and acceptance plan

- Build configuration, schemas, provider clients, profile rules and evidence selection.
- Wire the pipeline into FastAPI and expose the contract in Swagger.
- Exercise the five assessment queries with controlled provider responses, plus timeouts, malformed responses, unsupported profile links, duplicate identities, empty results and missing configuration.
- Run live examples when both API credentials and a model are configured. Record measured outcomes separately from test fixtures.
- Document startup, example requests, model trade-offs and deployment settings.

## Scope

This checkout is the local implementation. Publishing a public repository, deploying a paid endpoint, contacting the recruiter, and acting on social accounts are separate submission actions.
