import streamlit as st
import requests
import pandas as pd
import plotly.express as px
from datetime import datetime
import time
import random
import io

st.set_page_config(
    page_title="Semantic Scholar Publication Trends",
    page_icon="📚",
    layout="wide"
)

st.title("📚 Semantic Scholar Publication Trends")
st.markdown("Analyze research publication trends over time using Semantic Scholar's database or your own data.")

# Tab selection for API search vs. data upload
tab1, tab2 = st.tabs(["🔍 API Search", "📤 Upload Data"])

with tab1:
    # Form for search parameters
    with st.form("search_form"):
        col1, col2, col3 = st.columns(3)
        
        with col1:
            topics = st.text_area("Enter research topics (one per line)", 
                                placeholder="artificial intelligence\nmachine learning\ndeep learning")
        
        with col2:
            current_year = datetime.now().year
            start_year = st.number_input("Start Year", min_value=1900, max_value=current_year, value=2010)
        
        with col3:
            end_year = st.number_input("End Year", min_value=1900, max_value=current_year, value=current_year)
        
        # # Search field options
        # st.subheader("Search Fields")
        # col1, col2, col3 = st.columns(3)
        
        # with col1:
        #     search_title = st.checkbox("Title", value=True)
        # with col2:
        #     search_abstract = st.checkbox("Abstract", value=True)
        # with col3:
        #     search_keywords = st.checkbox("Author Keywords", value=True)
        
        # if not any([search_title, search_abstract, search_keywords]):
        #     st.warning("At least one search field must be selected")
        
        include_citations = st.checkbox("Include citation counts", value=False)
        
        # Add controls for API settings
        col1, col2 = st.columns(2)
        with col1:
            min_delay = st.slider("Minimum delay between requests (seconds)", 1, 10, 2)
        with col2:
            max_delay = st.slider("Maximum delay between requests (seconds)", min_delay, 15, min_delay + 3)
        
        submitted = st.form_submit_button("Search")

with tab2:
    st.header("Upload Your Own Data")
    
    st.markdown("""
    Upload a CSV file with your own publication data to visualize trends.
    
    **Required columns:**
    - `Topic`: The research topic or category
    - `Year`: The publication year
    - `Publications`: Number of publications
    
    **Optional columns:**
    - `Average Citations`: Average citation count (if available)
    """)
    
    # File uploader
    uploaded_file = st.file_uploader("Choose a CSV file", type=['csv'])
    
    # Example file download
    example_data = {
        "Topic": ["AI", "AI", "AI", "Machine Learning", "Machine Learning", "Machine Learning"],
        "Year": [2020, 2021, 2022, 2020, 2021, 2022],
        "Publications": [150, 200, 300, 250, 350, 400],
        "Average Citations": [5.2, 4.1, 2.3, 6.8, 5.5, 3.2]
    }
    example_df = pd.DataFrame(example_data)
    
    # Create downloadable example
    csv = example_df.to_csv(index=False)
    st.download_button(
        label="Download example CSV template",
        data=csv,
        file_name="example_data_template.csv",
        mime="text/csv",
    )
    
    # Preview data if uploaded
    if uploaded_file is not None:
        try:
            # Read the data
            df_upload = pd.read_csv(uploaded_file)
            
            # Validate required columns
            required_columns = ["Topic", "Year", "Publications"]
            if not all(col in df_upload.columns for col in required_columns):
                st.error(f"Missing required columns. Please ensure your CSV has: {', '.join(required_columns)}")
            else:
                st.success("Data uploaded successfully!")
                st.write("Preview of your data:")
                st.dataframe(df_upload.head())
                
                # Store the uploaded dataframe in session state for later use
                st.session_state.uploaded_df = df_upload
        except Exception as e:
            st.error(f"Error reading the file: {str(e)}")

# Function to build field-specific query
def build_query(topic, search_title, search_abstract, search_keywords):
    query_parts = []
    
    if search_title:
        query_parts.append(f"title:{topic}")
    if search_abstract:
        query_parts.append(f"abstract:{topic}")
    if search_keywords:
        query_parts.append(f"keywords:{topic}")
    
    # If no fields selected, default to general search
    if not query_parts:
        return topic
    
    # Join with OR operator
    return " OR ".join(query_parts)

# Function to query Semantic Scholar API with exponential backoff for rate limits
def search_semantic_scholar(query, year, include_citations=False, max_retries=3):
    base_url = "https://api.semanticscholar.org/graph/v1/paper/search"
    
    params = {
        "query": query,
        "year": str(year),
        "limit": 1,  # We only need count information
        "fields": "year"
    }
    
    headers = {
        "Accept": "application/json"
    }
    
    # Try with exponential backoff
    retry_count = 0
    while retry_count <= max_retries:
        try:
            response = requests.get(base_url, params=params, headers=headers)
            
            # Check for rate limit error
            if response.status_code == 429:
                retry_count += 1
                if retry_count > max_retries:
                    return 0, 0, f"Rate limit exceeded after {max_retries} retries"
                
                # Exponential backoff with jitter
                wait_time = (3 ** retry_count) + random.uniform(0, 1)
                st.warning(f"Rate limit hit. Waiting {wait_time:.2f} seconds before retry {retry_count}/{max_retries}...")
                time.sleep(wait_time)
                continue
                
            response.raise_for_status()
            data = response.json()
            
            # Extract publication count
            total = data.get('total', 0)
            
            # If citation counts requested, make additional API calls
            citation_count = 0
            error_msg = None
            if include_citations and total > 0:
                try:
                    # This is a simplified approach - for a real app you'd need to handle pagination
                    citation_params = {
                        "query": query,
                        "year": str(year),
                        "limit": 100,  # Get a sample of papers
                        "fields": "citationCount"
                    }
                    
                    citation_response = requests.get(base_url, params=citation_params, headers=headers)
                    citation_response.raise_for_status()
                    citation_data = citation_response.json()
                    
                    if 'data' in citation_data:
                        papers = citation_data['data']
                        if papers:
                            citation_count = sum(paper.get('citationCount', 0) for paper in papers) / len(papers)
                except Exception as e:
                    # Continue even if we can't get citation data
                    error_msg = f"Got publication count but couldn't retrieve citation data: {str(e)}"
            
            return total, citation_count, error_msg
        
        except requests.exceptions.RequestException as e:
            retry_count += 1
            if retry_count > max_retries or "429" not in str(e):
                return 0, 0, f"API Error: {str(e)}"
            
            # Exponential backoff with jitter for connection errors
            wait_time = (2 ** retry_count) + random.uniform(0, 1)
            st.warning(f"API error. Waiting {wait_time:.2f} seconds before retry {retry_count}/{max_retries}...")
            time.sleep(wait_time)
    
    return 0, 0, "Max retries exceeded"

# Function to create plots based on type selected
def create_plot(df, plot_type, x, y, color, title, labels):
    if plot_type == "Line Plot":
        fig = px.line(
            df, 
            x=x, 
            y=y, 
            color=color,
            markers=True,
            title=title,
            labels=labels
        )
    elif plot_type == "Bar Plot":
        fig = px.bar(
            df, 
            x=x, 
            y=y, 
            color=color,
            title=title,
            labels=labels,
            barmode="group"
        )
    elif plot_type == "Area Plot":
        fig = px.area(
            df, 
            x=x, 
            y=y, 
            color=color,
            title=title,
            labels=labels
        )
    
    fig.update_layout(
        xaxis=dict(tickmode='linear', dtick=max(1, len(df[x].unique())//10)),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    
    return fig

# Function to display visualizations
def display_visualizations(df, data_source="API"):
    # Display results
    st.header(f"Publication Trends ({data_source} Data)")
    
    # Show interactive table
    st.dataframe(df)
    
    # Create visualization
    st.header("Visualization")
    
    # Select plot type for publications
    plot_types = ["Line Plot", "Bar Plot", "Area Plot"]
    selected_plot_type = st.radio("Select plot type for publication trends:", plot_types, horizontal=True)
    
    # Create publication plot based on selected type
    pub_fig = create_plot(
        df, 
        selected_plot_type,
        x="Year", 
        y="Publications", 
        color="Topic",
        title="Publication Trends Over Time",
        labels={"Publications": "Number of Publications", "Year": "Year"}
    )
    
    st.plotly_chart(pub_fig, use_container_width=True)
    
    # Citation visualization if 'Average Citations' column exists
    if "Average Citations" in df.columns:
        # Select plot type for citations
        citation_plot_type = st.radio("Select plot type for citation trends:", plot_types, horizontal=True)
        
        citation_fig = create_plot(
            df, 
            citation_plot_type,
            x="Year", 
            y="Average Citations", 
            color="Topic",
            title="Average Citations Per Paper Over Time",
            labels={"Average Citations": "Average Citations", "Year": "Year"}
        )
        
        st.plotly_chart(citation_fig, use_container_width=True)
    
    # Download button for CSV
    csv = df.to_csv(index=False)
    st.download_button(
        label="Download data as CSV",
        data=csv,
        file_name="publication_trends.csv",
        mime="text/csv",
    )

# Handle API Search Tab
if submitted and topics:
    topic_list = [topic.strip() for topic in topics.split('\n') if topic.strip()]
    
    if start_year > end_year:
        st.error("Start year must be less than or equal to end year.")
    else:
        years = list(range(start_year, end_year + 1))
        
        # Create progress bar
        progress_bar = st.progress(0)
        status_text = st.empty()
        error_placeholder = st.empty()
        
        # # Display search field selection
        # fields_selected = []
        # if search_title:
        #     fields_selected.append("Title")
        # if search_abstract:
        #     fields_selected.append("Abstract")
        # if search_keywords:
        #     fields_selected.append("Author Keywords")
        
        st.info(f"Searching in Title and Abstract ...")
        
        # Create dataframe to store results
        results = []
        errors = []
        total_iterations = len(topic_list) * len(years)
        current_iteration = 0
        
        for topic in topic_list:
            for year in years:
                # Build field-specific query
                query = topic
                print(f"THE FULL QUERY IS: {query}")
                
                status_text.text(f"Searching for '{topic}' in {year}...")
                
                # Add a delay with randomization to avoid hitting API rate limits
                delay = random.uniform(min_delay, max_delay)
                time.sleep(delay)
                
                pub_count, citation_avg, error_msg = search_semantic_scholar(query, year, include_citations)
                
                if error_msg:
                    errors.append(f"Error for '{topic}' in {year}: {error_msg}")
                    if len(errors) <= 5:  # Show only first few errors
                        error_placeholder.error(errors[-1])
                
                result = {
                    "Topic": topic,
                    "Year": year,
                    "Publications": pub_count
                }
                
                if include_citations:
                    result["Average Citations"] = citation_avg
                
                results.append(result)
                
                # Update progress
                current_iteration += 1
                progress_bar.progress(current_iteration / total_iterations)
        
        # Clear status text and progress bar
        status_text.empty()
        progress_bar.empty()
        
        # Show summary of errors if any
        if errors:
            with st.expander(f"⚠️ {len(errors)} errors occurred during search"):
                for error in errors:
                    st.error(error)
        
        # Create dataframe from results
        df = pd.DataFrame(results)
        
        # Display results and visualizations
        display_visualizations(df, "API")

# Handle Upload Data Tab
if "uploaded_df" in st.session_state and uploaded_file is not None:
    # Load the data from session state
    df_upload = st.session_state.uploaded_df
    
    # Make sure Year is treated as an integer if it's not already
    if df_upload["Year"].dtype != "int64":
        try:
            df_upload["Year"] = df_upload["Year"].astype(int)
        except:
            st.warning("Could not convert Year column to integers. Make sure years are valid numbers.")
    
    # Display visualizations
    display_visualizations(df_upload, "Uploaded")

# If no submission or upload, display default
if (not submitted or not topics) and (uploaded_file is None):
    # Show example when app first loads
    st.info("Enter research topics and search parameters, or upload your own data to analyze publication trends.")
    
    # Example visualization
    example_data = {
        "Year": list(range(2010, 2023)),
        "Topic": ["Example Topic"] * 13,
        "Publications": [100, 120, 150, 200, 250, 300, 400, 450, 500, 550, 600, 650, 700]
    }
    
    example_df = pd.DataFrame(example_data)
    
    # Add plot type selector for example
    plot_types = ["Line Plot", "Bar Plot", "Area Plot"]
    example_plot_type = st.radio("Select example plot type:", plot_types, horizontal=True)
    
    example_fig = create_plot(
        example_df,
        example_plot_type,
        x="Year", 
        y="Publications", 
        color="Topic",
        title="Example Visualization",
        labels={"Publications": "Number of Publications", "Year": "Year"}
    )
    
    st.plotly_chart(example_fig, use_container_width=True)

# Sidebar with information
st.sidebar.title("API Rate Limits")
st.sidebar.info("""
### Semantic Scholar API Limits
- Public API: ~100 requests per 5-minute window
- If you're hitting rate limits frequently, consider:
  1. Increasing the delay between requests
  2. Reducing the number of topics or years
  3. [Registering for an API key](https://www.semanticscholar.org/product/api)
""")

st.sidebar.title("Search Tips")
st.sidebar.info("""
### Field-Specific Search
- **Title**: Searches only in paper titles
- **Abstract**: Searches only in paper abstracts
- **Author Keywords**: Searches only in keywords provided by the authors

### Query Syntax
- The app uses Semantic Scholar's field-specific search syntax
- Example: `title:"machine learning" OR abstract:"machine learning"`
- Multiple fields are combined with OR operators
""")

st.sidebar.title("Data Upload")
st.sidebar.info("""
### CSV Format
Your CSV file should have these columns:
- `Topic`: Research topic/category
- `Year`: Publication year
- `Publications`: Number of publications
- `Average Citations`: (Optional) Average citation count

### Data Visualization
- Upload your own data to bypass API limits
- Perfect for pre-processed data or data from other sources
""")

# Footer
st.markdown("---")
st.markdown("This app uses the [Semantic Scholar API](https://api.semanticscholar.org/) to analyze research publication trends or visualize your uploaded data.")