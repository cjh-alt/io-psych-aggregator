import feedparser
import pandas as pd 
import os
from datetime import datetime, timedelta
from time import mktime
import requests
from bs4 import BeautifulSoup
import urllib.parse
import time
import re

# --- Topic Tagging Logic ---
TOPIC_KEYWORDS = {
    "AI/Technology": ["ai", "artificial intelligence", "machine learning", "technology", "algorithm", "automation", "llm", "chatgpt"],
    "Assessment": ["assessment", "testing", "psychometric", "measurement", "validation", "cognitive ability"],
    "Belonging": ["belonging", "connectedness", "isolation"],
    "Creativity": ["creativity", "innovation", "divergent thinking"],
    "Culture": ["culture", "climate", "norms", "values"],
    "Coaching": ["coaching", "mentoring", "executive coaching"],
    "Compensation/Benefits": ["compensation", "benefits", "pay", "salary", "reward", "remuneration"],
    "Conflict": ["conflict", "dispute", "negotiation", "mediation", "friction"],
    "Diversity/Inclusion": ["diversity", "inclusion", "equity", "systemic equity", "quotas", "targets", "minority", "bias", "dei"],
    "Job Design": ["job design", "job crafting", "job characteristics", "autonomy"],
    "Justice": ["justice", "fairness", "procedural justice", "distributive justice"],
    "Leadership": ["leadership", "leader", "manager", "supervisor", "transformational", "lmd"],
    "Learning/Training": ["learning", "training", "development", "instruction", "skill acquisition"],
    "Meta-Analysis": ["meta-analysis", "meta analysis", "systematic review"],
    "Motivation": ["motivation", "goal setting", "self-determination", "engagement"],
    "Organisational Development & Design": ["organizational development", "organisational development", "organizational design", "change management", "od"],
    "Performance/Productivity": ["performance", "productivity", "efficiency", "effectiveness", "task performance"],
    "Personality": ["personality", "big five", "traits", "individual differences", "temperament"],
    "Remote Work": ["remote work", "telecommuting", "hybrid", "work from home", "wfh", "virtual teams"],
    "Rehabilitation": ["rehabilitation", "return to work", "recovery", "accommodation"],
    "Safety": ["safety", "accidents", "hazards", "occupational safety", "safety climate"],
    "Selection/Recruitment": ["selection", "recruitment", "hiring", "applicant", "interview", "resume"],
    "Teams": ["team", "group", "teamwork", "collaboration", "shared leadership"],
    "Turnover/Burnout": ["turnover", "burnout", "quitting", "exhaustion", "retention", "attrition", "stress"],
    "Wellbeing": ["wellbeing", "well-being", "health", "wellness", "mental health", "flourishing"]
}

def assign_topics(title, abstract):
    """Scans text and returns a comma-separated list of matched topics."""
    text_to_search = f"{title} {abstract}".lower()
    found_topics = []
    
    for topic, keywords in TOPIC_KEYWORDS.items():
        if any(keyword.lower() in text_to_search for keyword in keywords):
            found_topics.append(topic)
            
    return ", ".join(found_topics) if found_topics else "Uncategorized"

def extract_doi(entry):
    """Hunts for a DOI in the RSS entry metadata or the URL link."""
    # 1. Check if the publisher politely handed it to us in the feed metadata
    if hasattr(entry, 'prism_doi'):
        return entry.prism_doi
    if hasattr(entry, 'dc_identifier') and '10.' in entry.dc_identifier:
        return entry.dc_identifier.replace('doi:', '').replace('urn:doi:', '')
        
    # 2. If not, we use regex to hunt for the standard DOI format (10.xxxx/xxxxx) in the link or ID
    search_string = f"{entry.get('link', '')} {entry.get('id', '')}"
    match = re.search(r'(10\.\d{4,9}/[-._;()/:a-zA-Z0-9]+)', search_string)
    
    if match:
        # Some URLs have trailing characters we don't want, so we clean it up
        return match.group(1).rstrip('/')
        
    return "DOI Not Found"

def fetch_full_abstract(url):
    """Visits the article webpage and attempts to scrape the full abstract using BeautifulSoup."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Check the metadata tags
            meta_tags = [
                soup.find('meta', attrs={'name': 'citation_abstract'}),
                soup.find('meta', attrs={'name': 'dc.description'}),
                soup.find('meta', attrs={'property': 'og:description'}),
                soup.find('meta', attrs={'name': 'description'})
            ]
            
            for tag in meta_tags:
                if tag and tag.get('content') and len(tag.get('content')) > 100:
                    return tag.get('content').strip()
                    
            # Check for an abstract div
            abstract_div = soup.find(lambda tag: tag.name in ['div', 'section', 'p'] and tag.get('class') and any('abstract' in c.lower() for c in tag.get('class')))
            if abstract_div:
                return abstract_div.get_text(strip=True)
                
    except Exception as e:
        pass 
    
    return None

# --- Master Feed Dictionary ---
JOURNAL_FEEDS = {
    "Journal of Applied Psychology": "https://content.apa.org/journals/apl.rss",
    "Journal of Occupational Health Psychology": "https://content.apa.org/journals/ocp.rss",
    "Consulting Psychology Journal": "https://content.apa.org/journals/cpb.rss",
    "Academy of Management Journal": "https://journals.aom.org/action/showFeed?type=etoc&feed=rss&jc=amj",
    "Academy of Management Review": "https://journals.aom.org/action/showFeed?type=etoc&feed=rss&jc=amr",
    "Journal of Organizational Behavior": "https://onlinelibrary.wiley.com/feed/10991379/most-recent",
    "Personnel Psychology": "https://onlinelibrary.wiley.com/feed/17446570/most-recent",
    "Journal of Occupational and Organizational Psychology": "https://onlinelibrary.wiley.com/feed/20448325/most-recent",
    "Human Resource Development Quarterly": "https://onlinelibrary.wiley.com/feed/15321096/most-recent",
    "Human Resource Management": "https://onlinelibrary.wiley.com/feed/1099050X/most-recent",
    "International Journal of Selection and Assessment": "https://onlinelibrary.wiley.com/feed/14682389/most-recent",
    "Journal of Management": "https://journals.sagepub.com/action/showFeed?type=etoc&feed=rss&jc=joma",
    "Administrative Science Quarterly": "https://journals.sagepub.com/action/showFeed?type=etoc&feed=rss&jc=asqa",
    "Australian Journal of Management": "https://journals.sagepub.com/action/showFeed?type=etoc&feed=rss&jc=auma",
    "Group & Organization Management": "https://journals.sagepub.com/action/showFeed?type=etoc&feed=rss&jc=goma",
    "Organizational Psychology Review": "https://journals.sagepub.com/action/showFeed?type=etoc&feed=rss&jc=opra",
    "Organizational Behavior and Human Decision Processes (OBHDP)": "https://rss.sciencedirect.com/publication/science/07495978",
    "The Leadership Quarterly": "https://rss.sciencedirect.com/publication/science/10489843",
    "Journal of Vocational Behavior": "https://rss.sciencedirect.com/publication/science/00018791",
    "European Journal of Work and Organizational Psychology": "https://www.tandfonline.com/action/showFeed?type=etoc&feed=rss&jc=pewo20",
    "Human Performance": "https://www.tandfonline.com/action/showFeed?type=etoc&feed=rss&jc=hhup20",
    "Work & Stress": "https://www.tandfonline.com/action/showFeed?type=etoc&feed=rss&jc=twst20",
    "Journal of Business and Psychology": "https://link.springer.com/search.rss?facet-journal-id=10869&channel-name=Journal%20of%20Business%20and%20Psychology",
    "Organization Science": "https://pubsonline.informs.org/action/showFeed?type=etoc&feed=rss&jc=orsc",
    "Journal of Managerial Psychology": "https://www.emerald.com/insight/publication/issn/0268-3946/rss",
    "Industrial and Organizational Psychology": "https://www.cambridge.org/core/rss/product/id/IOP",
    "Journal of Personnel Psychology": "https://econtent.hogrefe.com/action/showFeed?type=etoc&feed=rss&jc=jpp"
}

def fetch_recent_articles(feeds_dict, days_back=90):
    articles_data = []
    cutoff_date = datetime.now() - timedelta(days=days_back)
    print(f"Fetching articles published after {cutoff_date.strftime('%Y-%m-%d')}...")

    for journal, url in feeds_dict.items():
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    pub_date = datetime.fromtimestamp(mktime(entry.published_parsed))
                    if pub_date >= cutoff_date:
                        title = entry.title
                        abstract = entry.summary if hasattr(entry, 'summary') else "No abstract available"
                        
                        # Grab the DOI
                        doi = extract_doi(entry)
                        
                        # --- Fallback Scraper Logic ---
                        if len(abstract) < 200 or "Volume" in abstract or "Issue" in abstract or "EarlyView" in abstract or abstract == "No abstract available":
                            print(f"Scraping missing abstract for: {title[:50]}...")
                            scraped_abstract = fetch_full_abstract(entry.link)
                            
                            if scraped_abstract:
                                abstract = scraped_abstract
                            else:
                                abstract = "Abstract could not be scraped. Please visit the article link."
                        # --- End Fallback Scraper ---
                        
                        articles_data.append({
                            "Journal": journal,
                            "Title": title,
                            "Link": entry.link,
                            "Published Date": pub_date.strftime("%Y-%m-%d"),
                            "Abstract": abstract,
                            "Topics": assign_topics(title, abstract),
                            "DOI": doi # Save it to the database
                        })
        except Exception as e:
            print(f"Error fetching {journal}: {e}")

    return pd.DataFrame(articles_data)

if __name__ == "__main__":
    # 1. Fetch the latest articles (we still look back 90 days to catch any stragglers)
    new_articles_df = fetch_recent_articles(JOURNAL_FEEDS, days_back=90)
    
    if not new_articles_df.empty:
        filename = "io_psych_articles.csv"
        
        if os.path.exists(filename):
            # 2. If you already have a database, load it
            existing_df = pd.read_csv(filename)
            
            # 3. Combine the old database with the new articles
            combined_df = pd.concat([existing_df, new_articles_df], ignore_index=True)
            
            # 4. CRITICAL: Drop any duplicates based on the article's Link. 
            # This ensures if we scrape the same article tomorrow, it doesn't get added twice.
            final_df = combined_df.drop_duplicates(subset=['Link'], keep='last')
        else:
            # If no database exists yet, the new data becomes the foundation
            final_df = new_articles_df
            
        # 5. Sort by newest first and save the growing archive
        final_df = final_df.sort_values(by="Published Date", ascending=False)
        final_df.to_csv(filename, index=False)
        print(f"Success! Database updated. It now contains {len(final_df)} total articles.")
    else:
        print("No new articles found in the given timeframe.")