"""Public demo backed by the FastAPI endpoint on this Streamlit server."""
import json

import httpx
import streamlit as st

st.set_page_config(page_title="Fieldwork · Prospect discovery", page_icon="🔎")
st.title("Fieldwork")
st.write("Find public profiles by name, handle, audience or topic.")
st.markdown("[API documentation](/docs)")

mode = st.radio("Search type", ["Find a person", "Topic or audience"], horizontal=True)
person = mode == "Find a person"
with st.form("discovery"):
    query = st.text_input(
        "Full name or @handle" if person else "Describe your audience",
        placeholder="Guido van Rossum" if person else "Startup founders in London",
        max_chars=400,
    )
    submitted = st.form_submit_button("Find profiles", type="primary")

if submitted:
    st.session_state.pop("last_result", None)
    if not query.strip() or not any(char.isalpha() for char in query):
        st.warning("Enter a name or topic containing at least one letter.")
    else:
        url = f"http://127.0.0.1:{st.get_option('server.port')}/prospect-discovery"
        payload = {"query": query.strip(), "mode": "person" if person else "discovery"}
        try:
            with st.spinner("Searching indexed public profiles…"), httpx.Client(timeout=150, trust_env=False) as client:
                response = client.post(url, json=payload)
            if response.is_success:
                st.session_state.last_result = (response.json(), response.headers.get("X-Unavailable-Sources"))
            else:
                detail = response.json().get("detail")
                st.error(detail if isinstance(detail, str) else f"Search failed (HTTP {response.status_code}).")
        except (httpx.HTTPError, ValueError):
            st.error("The discovery service could not complete this request. Please try again.")

if "last_result" in st.session_state:
    result, unavailable = st.session_state.last_result
    st.subheader(f"Matching profiles · {result['total_prospects']}")
    st.text(result["query"])
    if unavailable:
        st.warning(f"Partial search. Unavailable sources: {unavailable}.")
    if not result["prospects"]:
        st.info("No indexed profiles met the search criteria. Try another spelling, handle or audience.")
    for profile in result["prospects"]:
        with st.container(border=True):
            st.text(profile["name"])
            if profile.get("location"):
                st.text(profile["location"])
            if profile.get("description"):
                st.text(profile["description"])
            for link in profile["social_link"]:
                st.link_button(link["platform"], link["link"])
    st.download_button("Export JSON", json.dumps(result, ensure_ascii=False, indent=2),
                       "prospects.json", "application/json")
