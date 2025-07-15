import os
import logging
import argparse
import pycountry
from tqdm import tqdm
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Iterator

from elasticsearch import Elasticsearch, exceptions as es_exceptions
from newsdataapi import NewsDataApiClient
from newsdataapi.newsdataapi_client import NewsdataException

# --- Constants and Global Configuration ---

# Use a more robust way to define the log file path
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'news_ingestion.log')

# Constants are uppercase by convention
COUNTRY_FALLBACKS = {
    'brunei': 'BN', 'cape verde': 'CV', 'dr congo': 'CD',
    'ivory coast': 'CI', 'kosovo': 'XK', 'macau': 'MO',
    'macedonia': 'MK', 'micronesia': 'FM', 'russia': 'RU',
    'turkey': 'TR', 'vatican': 'VA'
}

# --- Configuration Class ---

@dataclass
class Config:
    # Elasticsearch Credentials
    cloud_id: str
    elastic_password: str
    news_api_key: str  # Move this up above any field with a default value
    elastic_index: str = "bytesview_news"

    # API Query Parameters
    query: Optional[str] = None
    qInTitle: Optional[str] = None
    country: List[str] = field(default_factory=list)
    category: List[str] = field(default_factory=list)
    language: List[str] = field(default_factory=list)
    domain: List[str] = field(default_factory=list)
    timeframe: Optional[str] = None
    size: Optional[int] = 10
    domainurl: List[str] = field(default_factory=list)
    excludedomain: List[str] = field(default_factory=list)
    timezone: Optional[str] = None
    full_content: bool = False
    image: bool = False
    video: bool = False
    prioritydomain: Optional[str] = None
    scroll: bool = False
    max_result: Optional[int] = None
    qInMeta: Optional[str] = None
    
    # Application settings
    num_pages: int = 20
    fetch_all_pages: bool = False

    @classmethod
    def from_args(cls):
        """Factory method to create a Config instance from command-line arguments."""
        parser = argparse.ArgumentParser(description='Fetch and ingest news data into Elasticsearch.')
        
        # Required arguments - prefer environment variables with CLI override
        parser.add_argument('--cloud_id', type=str, default=os.getenv('ELASTIC_CLOUD_ID'), help='Cloud ID for Elasticsearch. Can also be set via ELASTIC_CLOUD_ID env var.')
        parser.add_argument('--elastic_password', type=str, default=os.getenv('ELASTIC_PASSWORD'), help='Password for Elasticsearch. Can also be set via ELASTIC_PASSWORD env var.')
        parser.add_argument('--news_api_key', type=str, default=os.getenv('NEWS_API_KEY'), help='API Key for NewsData.io. Can also be set via NEWS_API_KEY env var.')
        parser.add_argument('--elastic_index', type=str, default="bytesview_news", help='Target Elasticsearch index name.')

        # API filtering arguments
        parser.add_argument('--query', type=str, help='Search query for news articles.')
        parser.add_argument('--qInTitle', type=str, help='Search query for news titles.')
        parser.add_argument('--country', nargs='*', default=[], help='List of country codes to filter news by.')
        parser.add_argument('--category', nargs='*', default=[], help='List of categories to filter news.')
        parser.add_argument('--language', nargs='*', default=[], help='List of languages to filter news.')
        parser.add_argument('--timeframe', type=str, help='Timeframe for fetching news (e.g., "24h" or start_date_end_date).')
        parser.add_argument('--size', type=int, default=50, help='Number of results to return per page.')
        
        # Application behavior arguments
        parser.add_argument('--num_pages', type=str, default='20', help='Number of pages to fetch. Use "all" to fetch until no more results are available.')
        
        # Add other arguments from the original script as needed...
        parser.add_argument('--full_content', action='store_true', help='Flag to fetch full content.')
        
        args = parser.parse_args()

        # Validate required arguments that were not provided by any means
        if not all([args.cloud_id, args.elastic_password, args.news_api_key]):
            raise ValueError("Cloud ID, Elastic Password, and News API Key are required. "
                             "Provide them via command-line arguments or environment variables.")
        
        fetch_all = (args.num_pages.lower() == 'all')

        return cls(
            cloud_id=args.cloud_id,
            elastic_password=args.elastic_password,
            elastic_index=args.elastic_index,
            news_api_key=args.news_api_key,
            query=args.query,
            qInTitle=args.qInTitle,
            country=args.country,
            category=args.category,
            language=args.language,
            timeframe=args.timeframe,
            size=args.size,
            full_content=args.full_content,
            num_pages=0 if fetch_all else int(args.num_pages),
            fetch_all_pages=fetch_all
        )

# --- Service Classes ---

class ElasticsearchService:
    """Handles all communication with Elasticsearch."""
    def __init__(self, cloud_id: str, password: str):
        try:
            self.es_client = Elasticsearch(
                cloud_id=cloud_id,
                basic_auth=("elastic", password),
                retry_on_timeout=True,
                max_retries=3
            )
            self.es_client.info()  # Check connection
            logging.info("Successfully connected to Elasticsearch.")
        except es_exceptions.AuthenticationException:
            logging.error("Elasticsearch authentication failed. Check credentials.")
            raise
        except es_exceptions.ConnectionError:
            logging.error("Could not connect to Elasticsearch. Check Cloud ID and network.")
            raise

    def index_document(self, index_name: str, document: Dict[str, Any]):
        """Indexes a single document into the specified index."""
        try:
            self.es_client.index(index=index_name, document=document)
        except es_exceptions.ApiError as e:
            logging.error(f"Failed to index document into '{index_name}': {e}")
            # Depending on the error, you might want to re-raise or handle it
            
# --- Data Transformation Logic ---

def get_iso_code(country_name: str) -> Optional[str]:
    """
    Converts a country name to its ISO 3166-1 alpha-2 code.
    Includes a fallback dictionary for non-standard names.
    """
    if not isinstance(country_name, str):
        return None
    
    country_name_lower = country_name.lower()
    
    if country_name_lower in COUNTRY_FALLBACKS:
        return COUNTRY_FALLBACKS[country_name_lower]
    
    try:
        return pycountry.countries.lookup(country_name_lower).alpha_2
    except LookupError:
        logging.warning(f"Could not find ISO code for country: '{country_name}'")
        return None

def transform_news_article(article: Dict[str, Any]) -> Dict[str, Any]:
    """
    Cleans, enriches, and transforms a raw news article record.
    This function is pure and has no side effects.
    """
    # Use .get() for safe dictionary access
    country_name = article.get('country', [None])[0]
    sentiment = article.get('sentiment')

    # article['ingestion_timestamp_utc'] = datetime.utcnow()
    article['dateandtime'] = datetime.strptime(datetime.now().strftime('%Y-%m-%d %H:%M:%S'), '%Y-%m-%d %H:%M:%S') 
    article['country_code'] = get_iso_code(country_name) if country_name else None
    article['country'] = country_name  # Keep original country name
    
    # Flatten sentiment_stats if present and sentiment is valid
    sentiment_stats = article.get('sentiment_stats', {})
    if sentiment and sentiment_stats and sentiment in ['positive', 'negative', 'neutral']:
        for key in ['positive', 'negative', 'neutral']:
            article[f'sentiment_score_{key}'] = round(sentiment_stats.get(key, 0.0), 4)
    
    # Remove redundant or complex objects
    article.pop('sentiment_stats', None)
    
    return article

# --- Main Application Class ---

class NewsIngestionPipeline:
    """Orchestrates the process of fetching, transforming, and ingesting news data."""
    
    def __init__(self, config: Config, api_client: NewsDataApiClient, es_service: ElasticsearchService):
        self.config = config
        self.api_client = api_client
        self.es_service = es_service

    def _build_api_params(self) -> Dict[str, Any]:
        """Constructs the parameter dictionary for the NewsDataAPI client."""
        params = {
            "q": self.config.query,
            "qInTitle": self.config.qInTitle,
            "country": self.config.country,
            "category": self.config.category,
            "language": self.config.language,
            "timeframe": self.config.timeframe,
            "size": self.config.size,
            "full_content": self.config.full_content,
            # Add other params from config as needed
        }
        # Return a clean dictionary with no None values
        return {k: v for k, v in params.items() if v}

    def _fetch_news_pages(self) -> Iterator[Dict[str, Any]]:
        """A generator that yields pages of news results from the API."""
        page = None
        pages_fetched = 0
        api_params = self._build_api_params()
        
        while True:
            if not self.config.fetch_all_pages and pages_fetched >= self.config.num_pages:
                logging.info(f"Reached specified page limit of {self.config.num_pages}.")
                break

            try:
                response = self.api_client.news_api(page=page, **api_params)
                yield response
                
                page = response.get('nextPage')
                pages_fetched += 1

                if not page:
                    logging.info("No more pages to fetch from the API.")
                    break
            except NewsdataException as e:
                logging.error(f"An API error occurred: {e}")
                # Depending on the error, you might want to break or retry
                break
            except Exception as e:
                logging.error(f"An unexpected error occurred during API fetch: {e}")
                break

    def run(self):
        """Executes the entire ingestion pipeline."""
        logging.info("Starting news ingestion pipeline...")
        
        total_articles_processed = 0
        earliest_article_date = None

        page_iterator = self._fetch_news_pages()
        
        # Determine total for progress bar if not fetching all pages
        pbar_total = self.config.num_pages if not self.config.fetch_all_pages else None
        
        with tqdm(total=pbar_total, desc="Fetching API Pages") as pbar:
            for response_page in page_iterator:
                if response_page.get('status') == 'success':
                    articles = response_page.get('results', [])
                    if not articles:
                        logging.info("Received a successful response with 0 articles.")
                        continue
                        
                    for article in articles:
                        transformed_article = transform_news_article(article)
                        self.es_service.index_document(self.config.elastic_index, transformed_article)
                        
                        # Track oldest article
                        pub_date_str = transformed_article.get('pubDate')
                        if pub_date_str:
                            current_date = datetime.strptime(pub_date_str, '%Y-%m-%d %H:%M:%S')
                            if earliest_article_date is None or current_date < earliest_article_date:
                                earliest_article_date = current_date
                        
                        total_articles_processed += 1
                else:
                    logging.error(f"API response indicated failure: {response_page.get('results', {})}")
                
                pbar.update(1)
        
        logging.info("News ingestion pipeline finished.")
        logging.info(f"Total articles processed: {total_articles_processed}")
        if earliest_article_date:
            logging.info(f"Earliest article found was published at: {earliest_article_date.strftime('%Y-%m-%d %H:%M:%S')}")


# --- Entrypoint ---

def setup_logging():
    """Configures the root logger."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(LOG_FILE),
            logging.StreamHandler()  # Also log to console
        ]
    )

def main():
    """Main function to run the application."""
    setup_logging()
    try:
        # 1. Load Configuration
        config = Config.from_args()
        
        # 2. Initialize Services (Dependencies)
        news_api_client = NewsDataApiClient(apikey=config.news_api_key, max_retries=5, retry_delay=20)
        es_service = ElasticsearchService(cloud_id=config.cloud_id, password=config.elastic_password)
        
        # 3. Initialize and Run the Pipeline
        pipeline = NewsIngestionPipeline(
            config=config,
            api_client=news_api_client,
            es_service=es_service
        )
        pipeline.run()

    except (ValueError, es_exceptions.AuthenticationException, es_exceptions.ConnectionError) as e:
        logging.critical(f"A critical setup error occurred. The application will exit. Error: {e}")
        # In a real application, you might exit with a non-zero status code
        # sys.exit(1)
    except Exception as e:
        logging.critical(f"An unexpected critical error occurred: {e}", exc_info=True)
        # sys.exit(1)

if __name__ == "__main__":
    main()