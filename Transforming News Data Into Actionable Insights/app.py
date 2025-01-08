import requests
import pandas as pd
import streamlit as st
import plotly.express as px
from datetime import datetime, timedelta

from config import load_api_key

# Configuration and Setup
st.set_page_config(page_title="News Intelligence Dashboard", layout="wide")

# API Configuration
NEWSDATA_API_KEY = load_api_key()

class NewsAnalyzer:
    def __init__(self, api_key):
        self.api_key = api_key
        
    def validate_params(self, keyword, from_date=None, to_date=None):
        """
        Validate input parameters before making an API request.

        This function checks the validity of the input parameters for a news search query.
        It ensures that a keyword is provided and that the date range, if specified,
        is within acceptable limits and properly formatted.

        Parameters:
        keyword (str): The search keyword for the news query. Must not be empty.
        from_date (str, optional): The start date for the news search in 'YYYY-MM-DD' format.
        to_date (str, optional): The end date for the news search in 'YYYY-MM-DD' format.

        Returns:
        list: A list of error messages. An empty list indicates no validation errors.
        """
        errors = []

        if not keyword:
            errors.append("Keyword is required")

        # Only validate dates if both are provided
        if from_date and to_date:
            try:
                start_date = datetime.strptime(from_date, '%Y-%m-%d')
                end_date = datetime.strptime(to_date, '%Y-%m-%d')

                # Check if date range is within allowed limits (e.g., 2 years)
                if (end_date - start_date).days > 730:
                    errors.append("Date range cannot exceed 30 days")
            except ValueError:
                errors.append("Invalid date format. Use YYYY-MM-DD")

        return errors
        
    def fetch_and_analyze_news(self, keyword, ai_region, from_date=None, to_date=None):
        """
        Fetch news from Newsdata.io API with progress tracking and error handling.

        Parameters:
        keyword (str): The keyword to search for in the news articles.
        ai_region (str): The region to filter news articles by.
        from_date (str, optional): The start date for filtering news articles.
        to_date (str, optional): The end date for filtering news articles.

        Returns:
        list: A list of dictionaries representing the fetched and analyzed news articles.
        """
        # Validate parameters first
        validation_errors = self.validate_params(keyword, from_date, to_date)
        if validation_errors:
            st.error("Validation errors:\n" + "\n".join(validation_errors))
            return []

        base_url = "https://newsdata.io/api/1/archive"
        params = {
            "apikey": self.api_key,
            "q": keyword,
        }

        # Only add date parameters if they're valid
        if from_date:
            params["from_date"] = from_date
        if to_date:
            params["to_date"] = to_date

        all_results = []
        total_pages = None
        current_page = 0

        try:
            progress_text = st.empty()
            progress_bar = st.progress(0)

            # Make the initial request
            response = requests.get(base_url, params=params)

            if response.status_code == 422:
                error_msg = response.json().get('results', {}).get('message', 'Invalid request parameters')
                st.error(f"API Error (422): {error_msg}")
                st.info("Please check your search parameters and try again")
                return []

            elif response.status_code == 200:
                data = response.json()

                if not data.get('results'):
                    st.warning("No results found for the specified criteria")
                    return []

                # Filter results based on ai_region
                filtered_results = []
                for article in data.get('results', []):
                    # Safely get and process ai_region
                    ai_regions = article.get('ai_region')
                    if ai_regions is None:
                        ai_regions = []
                    elif isinstance(ai_regions, str):
                        ai_regions = [ai_regions]  # Convert single string to list

                    # Convert regions to lowercase for comparison
                    article_regions = [r.lower() for r in ai_regions if r]

                    # Include article if no region filter or if region matches
                    if not ai_region or any(ai_region.lower() in r for r in article_regions):
                        filtered_results.append(article)

                all_results.extend(filtered_results)

                # Estimate total pages
                total_results = data.get('totalResults', 0)
                total_pages = total_results // 50
                current_page = 0

                progress_text.text(f"Fetching page {current_page} of approximately {total_pages} pages...")
                progress_bar.progress(current_page / total_pages if total_pages > 0 else 0)

                # Handle pagination using nextPage token
                while data.get('nextPage'):  
                    current_page += 1
                    params['page'] = data['nextPage']

                    progress_text.text(f"Fetching page {current_page} of approximately {total_pages} pages...")
                    progress_bar.progress(min(current_page / total_pages if total_pages > 0 else 0, 1.0))

                    response = requests.get(base_url, params=params)
                    if response.status_code == 200:
                        data = response.json()
                        new_results = []
                        for article in data.get('results', []):
                            # Safely get and process ai_region
                            ai_regions = article.get('ai_region')
                            if ai_regions is None:
                                ai_regions = []
                            elif isinstance(ai_regions, str):
                                ai_regions = [ai_regions]  # Convert single string to list

                            # Convert regions to lowercase for comparison
                            article_regions = [r.lower() for r in ai_regions if r]

                            # Include article if no region filter or if region matches
                            if not ai_region or any(ai_region.lower() in r for r in article_regions):
                                new_results.append(article)
                        if not new_results:
                            break
                        all_results.extend(new_results)
                    else:
                        st.error(f"Error fetching page {current_page}: Status code {response.status_code}")
                        break

                progress_text.text(f"Completed! Fetched {len(all_results)} articles from {current_page} pages.")
                progress_bar.progress(1.0)

            else:
                st.error(f"Error: Received status code {response.status_code}")

            return all_results

        except requests.exceptions.RequestException as e:
            st.error(f"Network error: {str(e)}")
            return []
        except Exception as e:
            st.error(f"Error fetching news: {str(e)}")
            return []

def process_news_data(news_data):
    """
    Process raw news data into a structured DataFrame with enhanced fields.

    This function takes raw news data, typically from an API response, and transforms
    it into a pandas DataFrame. It extracts relevant information from each article,
    handles special cases like the 'ai_region' field, and adds additional date-based
    features.

    Parameters:
    news_data (list): A list of dictionaries, where each dictionary represents a news article
                      with fields such as title, link, ai_region, sentiment, etc.

    Returns:
    pandas.DataFrame: A DataFrame containing processed news data with the following columns:
        - title: The title of the article
        - link: URL link to the full article
        - ai_region: Comma-separated string of AI-identified regions
        - sentiment: Sentiment of the article (e.g., positive, negative, neutral)
        - source_id: Identifier for the news source
        - pubDate: Publication date and time
        - category: List of categories the article belongs to
        - description: Brief description or summary of the article
        - content: Full content of the article
        - date: Extracted date from pubDate
        - hour: Extracted hour from pubDate
        - day_of_week: Day of the week derived from pubDate

    The returned DataFrame is deduplicated based on the 'title' field, keeping the first occurrence.
    If the input news_data is empty, an empty DataFrame is returned.
    """
    if not news_data:
        return pd.DataFrame()

    processed_data = []

    for article in news_data:
        # Handle ai_region
        ai_regions = article.get('ai_region')
        if ai_regions is None:
            ai_regions = []
        elif isinstance(ai_regions, str):
            ai_regions = [ai_regions]

        # Extract basic article information
        record = {
            'title': article.get('title', ''),
            'link': article.get('link', ''),
            'ai_region': ', '.join(ai_regions),
            'sentiment': article.get('sentiment', 'neutral'),
            'source_id': article.get('source_id', ''),
            'pubDate': pd.to_datetime(article.get('pubDate', '')),
            'category': article.get('category', []),
            'description': article.get('description', ''),
            'content': article.get('content', '')
        }

        processed_data.append(record)

    df = pd.DataFrame(processed_data)

    # Convert publication date to datetime
    df['pubDate'] = pd.to_datetime(df['pubDate'])

    # Create date-based features
    df['date'] = df['pubDate'].dt.date
    df['hour'] = df['pubDate'].dt.hour
    df['day_of_week'] = df['pubDate'].dt.day_name()

    return df.drop_duplicates(subset='title', keep='first')

def main():
    """
    Launch the News Intelligence Dashboard application.

    This function initializes and renders the Streamlit-based dashboard, allowing users to analyze 
    news articles by keyword, region, and date range. It provides options to filter, visualize, 
    and download the analyzed data.

    Features:
    1. Sidebar inputs for search parameters:
        - Keyword (required)
        - Region filter (optional)
        - Date range (up to 2 years)
    2. Real-time data fetching from the Newsdata.io API.
    3. Progress tracking and error handling during data retrieval.
    4. Sentiment analysis, temporal trends, and source distribution visualizations.
    5. Display of latest articles in a tabular format with download capability.

    Parameters:
    None

    Returns:
    None
    """
    st.title("News Intelligence Dashboard")
    st.write("Analyze news sentiment and track organizations in real-time")
    
    # Initialize analyzer
    analyzer = NewsAnalyzer(NEWSDATA_API_KEY)
    
    # Sidebar inputs
    st.sidebar.header("Search Parameters")
    keyword = st.sidebar.text_input("Enter keyword (required)")
    
    # Add country selector with common options
    countries = [
    "", "afghanistan", "albania", "algeria", "andorra", "angola", "antigua & deps", "argentina",
    "armenia", "australia", "austria", "azerbaijan", "bahamas", "bahrain", "bangladesh",
    "barbados", "belarus", "belgium", "belize", "benin", "bhutan", "bolivia", 
    "bosnia herzegovina", "botswana", "brazil", "brunei", "bulgaria", "burkina", 
    "burundi", "cambodia", "cameroon", "canada", "cape verde", "central african rep", 
    "chad", "chile", "china", "colombia", "comoros", "congo", "congo {democratic rep}", 
    "costa rica", "croatia", "cuba", "cyprus", "czech republic", "denmark", "djibouti", 
    "dominica", "dominican republic", "east timor", "ecuador", "egypt", "el salvador", 
    "equatorial guinea", "eritrea", "estonia", "ethiopia", "fiji", "finland", "france", 
    "gabon", "gambia", "georgia", "germany", "ghana", "greece", "grenada", "guatemala", 
    "guinea", "guinea-bissau", "guyana", "haiti", "honduras", "hungary", "iceland", "india", 
    "indonesia", "iran", "iraq", "ireland", "israel", "italy", "ivory coast", 
    "jamaica", "japan", "jordan", "kazakhstan", "kenya", "kiribati", "korea north", 
    "korea south", "kosovo", "kuwait", "kyrgyzstan", "laos", "latvia", "lebanon", "lesotho", 
    "liberia", "libya", "liechtenstein", "lithuania", "luxembourg", "macedonia", 
    "madagascar", "malawi", "malaysia", "maldives", "mali", "malta", "marshall islands", 
    "mauritania", "mauritius", "mexico", "micronesia", "moldova", "monaco", "mongolia", 
    "montenegro", "morocco", "mozambique", "myanmar", "namibia", "nauru", "nepal", 
    "netherlands", "new zealand", "nicaragua", "niger", "nigeria", "norway", "oman", 
    "pakistan", "palau", "panama", "papua new guinea", "paraguay", "peru", "philippines", 
    "poland", "portugal", "qatar", "romania", "russian federation", "rwanda", 
    "st kitts & nevis", "st lucia", "saint vincent & the grenadines", "samoa", "san marino", 
    "sao tome & principe", "saudi arabia", "senegal", "serbia", "seychelles", "sierra leone", 
    "singapore", "slovakia", "slovenia", "solomon islands", "somalia", "south africa", 
    "south sudan", "spain", "sri lanka", "sudan", "suriname", "swaziland", "sweden", 
    "switzerland", "syria", "taiwan", "tajikistan", "tanzania", "thailand", "togo", "tonga", 
    "trinidad & tobago", "tunisia", "turkey", "turkmenistan", "tuvalu", "uganda", "ukraine", 
    "united arab emirates", "united kingdom", "united states", "uruguay", "uzbekistan", 
    "vanuatu", "vatican city", "venezuela", "vietnam", "yemen", "zambia", "zimbabwe"
]
    region = st.sidebar.selectbox("Select region (optional)", countries)
    
    # Date range with validation
    max_date = datetime.now()
    min_date = max_date - timedelta(days=730)
    date_range = st.sidebar.date_input(
        "Select date range (max 2 years)",
        [min_date, max_date],
        min_value=min_date,
        max_value=max_date
    )
    
    search_button = st.sidebar.button("Search News")
    
    if search_button and keyword:
        if len(date_range) == 2:
            from_date, to_date = date_range
            
            # Fetch and analyze news
            with st.spinner("Fetching news data..."):
                news_data = analyzer.fetch_and_analyze_news(
                    keyword,
                    region,
                    from_date.strftime('%Y-%m-%d'),
                    to_date.strftime('%Y-%m-%d')
                )
                
                df = process_news_data(news_data)
                
                if not df.empty:
                    # Display total articles fetched
                    st.success(f"Successfully analyzed {len(df)} news articles.")
                    
                    # Create dashboard layout with metrics
                    metrics_col1, metrics_col2, metrics_col3, metrics_col4 = st.columns(4)
                    
                    with metrics_col1:
                        st.metric("Total Articles", len(df))
                    with metrics_col2:
                        st.metric("Unique Sources", df['source_id'].nunique())
                    with metrics_col3:
                        st.metric("Regions Covered", df['ai_region'].nunique())
                    with metrics_col4:
                        time_span = (df['pubDate'].max() - df['pubDate'].min()).days
                        st.metric("Days Covered", time_span)

                    # Create visualization layout
                    st.subheader("News Analysis Dashboard")
                    tab1, tab2, tab3 = st.tabs(["Sentiment Analysis", "Temporal Analysis", "Content Analysis"])
                    
                    with tab1:
                        col1, = st.columns(1)
                        
                        with col1:
                            # Sentiment distribution
                            sentiment_counts = df['sentiment'].value_counts()
                            fig_sentiment = px.pie(
                                values=sentiment_counts.values,
                                names=sentiment_counts.index,
                                title='Sentiment Distribution',
                                color_discrete_sequence=px.colors.qualitative.Set3
                            )
                            st.plotly_chart(fig_sentiment, use_container_width=True)
                            
                    
                    with tab2:
                        col3, = st.columns(1)
                        
                        with col3:
                            # Publication time analysis
                            hourly_dist = df['hour'].value_counts().sort_index()
                            fig_time = px.line(
                                x=hourly_dist.index,
                                y=hourly_dist.values,
                                title='Publication Time Distribution',
                                labels={'x': 'Hour of Day', 'y': 'Number of Articles'},
                                color_discrete_sequence=px.colors.qualitative.Set1
                            )
                            # Customize x-axis to show all hours
                            fig_time.update_xaxes(tickmode='linear', tick0=0, dtick=1)
                            st.plotly_chart(fig_time, use_container_width=True)                 
                    
                    with tab3:
                        col5, = st.columns(1)
                        
                        with col5:
                            # Source distribution
                            source_counts = df['source_id'].value_counts().head(10)
                            fig_source = px.bar(
                                x=source_counts.index,
                                y=source_counts.values,
                                title='Top 10 News Sources',
                                labels={'x': 'Source', 'y': 'Count'},
                                color_discrete_sequence=px.colors.qualitative.Set2
                            )
                            st.plotly_chart(fig_source, use_container_width=True)
                            
                    
                    # News table
                    st.subheader("Latest News Articles")
                    # Convert links to markdown
                    df['title'] = df.apply(
                        lambda x: f"[{x['title']}]({x['link']})", axis=1
                    )
                    
                    # Show the most recent articles first
                    df_display = df.sort_values('pubDate', ascending=False)
                    st.markdown(df_display[['title', 'ai_region', 'sentiment', 'pubDate']].head(10).to_markdown(index=False))
                    
                    # Download button for full data
                    csv = df.to_csv(index=False)
                    st.download_button(
                        label="Download data...",
                        data=csv,
                        file_name="news_analysis.csv",
                        mime="text/csv"
                    )
                else:
                    st.warning("No data found for the specified parameters.")
        else:
            st.error("Please select both start and end dates")
    elif search_button:
        st.error("Please enter a keyword to search")

if __name__ == "__main__":
    main()