# Live provider check

The five assessment queries ran on 23 November 2026 through the FastAPI route using its test client, the configured NVIDIA Nemotron 3 Ultra free model on OpenRouter and actual Google searches through Serper. No outbound HTTP transport was mocked in this run. The table records returned candidates and application elapsed time. Individual relevance and profile ownership were not manually audited.

| Query | HTTP | Prospects | Seconds | Unavailable search scopes |
| --- | ---: | ---: | ---: | --- |
| Football lovers in Washington DC in USA | 200 | 0 | 18.2 | None |
| Digital marketing agency owners in New York USA | 200 | 0 | 19.7 | None |
| Startup founders in London UK | 200 | 2 | 15.7 | None |
| Cricket lovers in Ahmedabad India | 200 | 1 | 16.3 | None |
| Restaurant owners in Dubai UAE | 200 | 1 | 19.0 | None |

The zero counts indicate that the pipeline retained no qualifying profiles from those search batches. Search indexes, snippets and model-generated criteria can change on later runs. This log records aggregate results and omits personal contact details.

An independent Uvicorn loopback check returned HTTP 200 for Swagger UI and HTTP 422 for a blank query, and confirmed the discovery route in the OpenAPI document.
