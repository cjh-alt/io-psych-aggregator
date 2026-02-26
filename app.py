import streamlit as st
import pandas as pd
from google import genai
from datetime import datetime
from dateutil.relativedelta import relativedelta

# --- Page Configuration ---
st.set_page_config(page_title="I/O Psychology Research Aggregator - 2026 Onwards", layout="wide")
st.title("📚 I/O Psychology Research Aggregator - 2026 Onwards")

# --- Initialize Search State ---
if "search_executed" not in st.session_state:
    st.session_state.search_executed = False

# --- Load Data ---
@st.cache_data
def load_data():
    try:
        df = pd.read_csv("io_psych_articles.csv")
        df['Published Date'] = pd.to_datetime(df['Published Date'])
        return df
    except FileNotFoundError:
        st.error("Data file not found. Ensure the scraper has run successfully.")
        return pd.DataFrame()

df = load_data()

if not df.empty:
    # --- Sidebar Filters ---
    st.sidebar.header("Filter Articles")

    # 1. Date Filter
    date_options = {
        "Last Week": datetime.today() - relativedelta(weeks=1),
        "Last 30 Days": datetime.today() - relativedelta(days=30),
        "Last 90 Days": datetime.today() - relativedelta(days=90),
        "Last 6 Months": datetime.today() - relativedelta(months=6),
        "Last 12 Months": datetime.today() - relativedelta(months=12),
        "Last 2 Years": datetime.today() - relativedelta(years=2),
        "All Time": datetime.min
    }
    selected_date_label = st.sidebar.selectbox("Date Range", list(date_options.keys()))
    cutoff_date = date_options[selected_date_label]

    # 2. Journal Filter
    all_journals = sorted(df['Journal'].unique().tolist())
    selected_journals = st.sidebar.multiselect(
        "Journals", 
        options=["All Journals"] + all_journals, 
        default=[]
    )

    # 3. Topic Filter
    all_topics = sorted(list(set([topic.strip() for sublist in df['Topics'].dropna().str.split(',') for topic in sublist if topic.strip()])))
    # We change the default from '["All Topics"]' to an empty list '[]'
    selected_topics = st.sidebar.multiselect(
        "Topics (Select multiple)", 
        options=["All Topics"] + all_topics, 
        default=[]
    )

    # 4. Search Bar
    search_query = st.sidebar.text_input("Search Title or Abstract Keywords")

    # --- Sidebar Sorting ---
    st.sidebar.markdown("---")
    st.sidebar.header("Sort Results")
    sort_by = st.sidebar.selectbox("Sort by", ["Date (Newest First)", "Date (Oldest First)", "Journal (A-Z)", "Title (A-Z)"])

    # --- Sidebar API Key ---
    st.sidebar.markdown("---")
    st.sidebar.header("🧠 AI Settings")
    api_key = st.sidebar.text_input("Gemini API Key", type="password", help="Get a free key at aistudio.google.com")

    # --- Run Search Button ---
    st.sidebar.markdown("---")
    if st.sidebar.button("🔍 Run Search", type="primary", use_container_width=True):
        st.session_state.search_executed = True

    # --- Apply Filters ---
    filtered_df = df.copy()

    # Apply Date
    filtered_df = filtered_df[filtered_df['Published Date'] >= cutoff_date]

    # Apply Journal
    if "All Journals" not in selected_journals and selected_journals:
        filtered_df = filtered_df[filtered_df['Journal'].isin(selected_journals)]

    # Apply Topics
    if "All Topics" not in selected_topics and selected_topics:
        pattern = '|'.join(selected_topics)
        filtered_df = filtered_df[filtered_df['Topics'].str.contains(pattern, case=False, na=False)]

    # Apply Search
    if search_query:
        search_mask = filtered_df['Title'].str.contains(search_query, case=False, na=False) | \
                      filtered_df['Abstract'].str.contains(search_query, case=False, na=False)
        filtered_df = filtered_df[search_mask]

    # --- Apply Sorting ---
    if sort_by == "Date (Newest First)":
        filtered_df = filtered_df.sort_values(by="Published Date", ascending=False)
    elif sort_by == "Date (Oldest First)":
        filtered_df = filtered_df.sort_values(by="Published Date", ascending=True)
    elif sort_by == "Journal (A-Z)":
        filtered_df = filtered_df.sort_values(by="Journal", ascending=True)
    elif sort_by == "Title (A-Z)":
        filtered_df = filtered_df.sort_values(by="Title", ascending=True)

    # --- Display Results ---
    if not st.session_state.search_executed:
        # What shows up when the page first loads
        st.info("👋 Welcome to your I/O Psychology Research Aggregator! Adjust your filters in the sidebar and click **🔍 Run Search** to view articles.")
    else:
        # What shows up after you click the button
        st.subheader(f"Results: {len(filtered_df)} Articles")
        
        if not filtered_df.empty:
            earliest_date = filtered_df['Published Date'].min().strftime('%d/%m/%Y')
            latest_date = filtered_df['Published Date'].max().strftime('%d/%m/%Y')
            st.markdown(f"**Sourced articles from {earliest_date} - {latest_date}**")
        
        # --- AI Summary Generation ---
        st.markdown("---")
        if st.button("✨ Generate AI Summary of Results"):
            if not api_key:
                st.warning("⚠️ Please enter your Gemini API Key in the sidebar first.")
            elif len(filtered_df) == 0:
                st.warning("⚠️ No articles to summarize.")
            else:
                with st.spinner("Gemini is reading the articles and synthesizing themes..."):
                    try:
                        client = genai.Client(api_key=api_key.strip())
                        
                        # 1. Build the prompt instructions with strict guardrails
                        prompt = """
                        You are an expert Industrial/Organizational Psychologist. 
                        You are tasked with summarizing the following journal article abstracts. 
                        
                        CRITICAL INSTRUCTIONS:
                        1. STRICT ADHERENCE TO SOURCE: Base your primary synthesis ONLY on the substantive text provided in the abstracts below. Do not invent or infer findings that are not explicitly stated in the provided text.
                        2. IGNORE STUBS: Some abstracts may only contain citation data (e.g., "Volume 79, Issue 1", "EarlyView"). Ignore these completely when synthesizing the main findings.
                        3. INSUFFICIENT DATA: If all provided abstracts are stubs or lack substantive findings, explicitly state: "Insufficient information is available in the provided abstracts to generate a summary."
                        4. EXTERNAL KNOWLEDGE: If insufficient data, bring in outside theories or context to enrich the summary, but you MUST place this in a completely separate section at the very end titled: "Broader Context (Outside Sources)". Introduce this section by stating: 'Beyond the included sources, broader knowledge on this topic highlights the following:'
                        5. CITATIONS & LINKS REQUIRED: You must rigorously cite your sources for every theme or finding. 
                           - When summarizing the provided articles, cite them inline using Markdown links formatted like this: [[Title]](Link).
                           - When writing the 'Broader Context' section, explicitly list the external authors, core theories, or standard academic references you are drawing from.
                        
                        Format your response with clear headings and bullet points for readability.
                        
                        Here are the articles:
                        \n\n
                        """
                        
                        # 2. Add the filtered articles to the prompt (limiting to top 50)
                        articles_to_summarize = filtered_df.head(50)
                        for idx, row in articles_to_summarize.iterrows():
                            # We now pass the Link to Gemini so it knows exactly where the data came from
                            prompt += f"Title: {row['Title']}\nLink: {row['Link']}\nAbstract: {row['Abstract']}\n\n"
                            
                        response = client.models.generate_content(
                            model='gemini-2.5-flash',
                            contents=prompt
                        )
                        
                        st.success("Summary Generated!")
                        st.markdown(response.text)
                        
                    except Exception as e:
                        st.error(f"An error occurred while talking to Gemini: {e}")
                        
        st.markdown("---")

        for index, row in filtered_df.iterrows():
            with st.container():
                st.markdown(f"### [{row['Title']}]({row['Link']})")
                st.markdown(f"**Journal:** {row['Journal']}")
                st.markdown(f"**Published:** {row['Published Date'].strftime('%Y-%m-%d')}")
                
                # Format the DOI as a clickable link if we found one
                if pd.notna(row.get('DOI')) and row['DOI'] != "DOI Not Found":
                    st.markdown(f"**DOI:** [{row['DOI']}](https://doi.org/{row['DOI']})")
                    
                st.markdown(f"**Topics:** {row['Topics']}")
                
                with st.expander("Read Abstract"):
                    st.write(row['Abstract'])
                    
                st.markdown("---")