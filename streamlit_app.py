"""Streamlit Community Cloud Live Demo for AI Prospect Discovery API."""
import asyncio
import json
import os

import httpx
import streamlit as st

from app.providers import Settings
from app.service import DiscoveryService

# Page configuration
st.set_page_config(
    page_title="AI Prospect Discovery · Live Demo",
    page_icon="🔎",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Apply Streamlit secrets to environment if available
if hasattr(st, "secrets"):
    try:
        for k, v in st.secrets.items():
            if isinstance(v, str) and k not in os.environ:
                os.environ[k] = v
    except Exception:
        pass


def get_current_settings(custom_openrouter=None, custom_serper=None, custom_model=None):
    base = Settings.load()
    router_key = custom_openrouter.strip() if custom_openrouter else base.router_key
    search_key = custom_serper.strip() if custom_serper else base.search_key
    model = custom_model.strip() if custom_model else base.model
    return Settings(router_key=router_key, search_key=search_key, model=model)


async def execute_discovery(query: str, mode: str, settings: Settings):
    async with httpx.AsyncClient() as client:
        service = DiscoveryService(client, settings)
        outcome = await service.discover(query=query, mode=mode)
        return outcome.response.model_dump(), outcome.unavailable


# --- Sidebar ---
with st.sidebar:
    st.header("⚙️ Configuration")
    
    st.markdown(
        "This application connects to **OpenRouter** (for query understanding) and **Serper** (for multi-platform search)."
    )
    
    env_settings = Settings.load()
    has_router = bool(env_settings.router_key)
    has_serper = bool(env_settings.search_key)
    
    st.subheader("API Keys Status")
    st.write(f"• OpenRouter Key: {'✅ Configured' if has_router else '❌ Missing'}")
    st.write(f"• Serper Key: {'✅ Configured' if has_serper else '❌ Missing'}")
    
    with st.expander("🔑 Override API Keys", expanded=not (has_router and has_serper)):
        custom_router = st.text_input(
            "OpenRouter API Key",
            type="password",
            placeholder="sk-or-v1-...",
            help="Get from https://openrouter.ai/settings/keys",
        )
        custom_serper = st.text_input(
            "Serper API Key",
            type="password",
            placeholder="Enter Serper key...",
            help="Get from https://serper.dev/",
        )
        custom_model = st.selectbox(
            "LLM Model",
            [
                "nvidia/nemotron-3-ultra-550b-a55b:free",
                "google/gemini-2.5-flash-lite",
                "openai/gpt-4.1-mini",
            ],
            index=0,
            help="Recommended free or low-cost model for query understanding",
        )
    
    st.divider()
    st.subheader("📌 Project Links")
    st.markdown("[GitHub Repository](https://github.com/PrashantTarbundiya/ai-prospect-discovery-api)")
    st.markdown("[Serper Search](https://serper.dev/) · [OpenRouter](https://openrouter.ai/)")


# --- Main UI ---
st.title("🔎 AI-Powered Multi-Platform Prospect Discovery")
st.caption("Discover verified public profiles across Google, LinkedIn, X, YouTube, Instagram, Facebook, Threads, WhatsApp, and Email.")

mode_choice = st.radio(
    "Discovery Mode",
    ["Topic or Audience (Natural Language)", "Find a Person (Exact Name or Handle)"],
    horizontal=True,
)
is_person = "Find a Person" in mode_choice
mode_val = "person" if is_person else "discovery"

with st.form("discovery_form"):
    if is_person:
        query_input = st.text_input(
            "Full Name or Social Handle",
            placeholder="e.g. Guido van Rossum or @gvanrossum",
            max_chars=400,
        )
    else:
        query_input = st.text_input(
            "Natural Language Discovery Query",
            placeholder="e.g. Football lovers in Washington DC in USA or Startup founders in London UK",
            max_chars=400,
        )
    
    col1, col2 = st.columns([1, 5])
    with col1:
        submitted = st.form_submit_button("🔍 Find Prospects", type="primary", use_container_width=True)

if submitted:
    clean_query = query_input.strip()
    if not clean_query or not any(c.isalpha() for c in clean_query):
        st.warning("Please enter a search query containing at least one letter.")
    else:
        active_settings = get_current_settings(
            custom_openrouter=custom_router if 'custom_router' in locals() and custom_router else None,
            custom_serper=custom_serper if 'custom_serper' in locals() and custom_serper else None,
            custom_model=custom_model if 'custom_model' in locals() and custom_model else None,
        )
        
        if not active_settings.search_key:
            st.error("Missing Serper API Key. Please provide it in the sidebar or via environment variables.")
        elif mode_val == "discovery" and not active_settings.router_key:
            st.error("Missing OpenRouter API Key. Please provide it in the sidebar or via environment variables.")
        else:
            with st.spinner("Searching multi-platform sources and verifying public profiles…"):
                try:
                    result, unavailable = asyncio.run(
                        execute_discovery(clean_query, mode_val, active_settings)
                    )
                    st.session_state["discovery_result"] = (result, unavailable)
                except Exception as exc:
                    st.error(f"Search failed: {exc}")

# --- Render Results ---
if "discovery_result" in st.session_state:
    result, unavailable = st.session_state["discovery_result"]
    total = result.get("total_prospects", 0)
    prospects = result.get("prospects", [])
    
    st.divider()
    
    col_stat1, col_stat2, col_stat3 = st.columns([2, 2, 2])
    with col_stat1:
        st.metric("Total Prospects Found", total)
    with col_stat2:
        st.metric("Mode", "Person Lookup" if is_person else "Audience Discovery")
    with col_stat3:
        if unavailable:
            st.warning(f"Partial sources: {', '.join(unavailable)}")
        else:
            st.success("All platform sources operational")
            
    if total == 0:
        st.info("No verified public profiles matched all criteria in this search. Try refining the location, spelling, or keywords.")
    else:
        for idx, prospect in enumerate(prospects, start=1):
            with st.container(border=True):
                head_col, loc_col = st.columns([3, 1])
                with head_col:
                    st.markdown(f"### {idx}. {prospect.get('name', 'Unknown')}")
                with loc_col:
                    loc = prospect.get("location")
                    if loc:
                        st.markdown(f"📍 **{loc}**")
                        
                desc = prospect.get("description")
                if desc:
                    st.markdown(f"*{desc}*")
                    
                links = prospect.get("social_link", [])
                if links:
                    st.markdown("**Public Links & Contacts:**")
                    link_cols = st.columns(min(len(links), 6))
                    for i, link_item in enumerate(links):
                        platform = link_item.get("platform", "Link")
                        url = link_item.get("link", "#")
                        with link_cols[i % len(link_cols)]:
                            st.link_button(f"🔗 {platform}", url, use_container_width=True)
                            
        st.download_button(
            label="📥 Download Structured JSON",
            data=json.dumps(result, ensure_ascii=False, indent=2),
            file_name="prospects.json",
            mime="application/json",
        )
        
    with st.expander("📄 View Structured JSON Response"):
        st.json(result)
