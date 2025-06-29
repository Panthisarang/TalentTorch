# 🚀 LinkedIn Sourcing Agent - Synapse Challenge

An autonomous AI agent that sources LinkedIn profiles at scale, scores candidates using a sophisticated fit score algorithm, and generates personalized outreach messages.

## 🌟 Features

### Core Features
- **LinkedIn Profile Discovery**: Intelligent search and extraction of relevant profiles
- **Fit Score Algorithm**: Comprehensive scoring based on education, trajectory, company relevance, skills, location, and tenure
- **Personalized Outreach**: AI-generated messages referencing specific candidate details
- **Batch Processing**: Handle multiple jobs simultaneously with intelligent queuing

### Bonus Features ✅
- **Multi-Source Enhancement**: Combines LinkedIn data with GitHub, Twitter, and personal websites
- **Smart Caching**: Intelligent caching to avoid re-fetching data
- **Batch Processing**: Handle 10+ jobs in parallel with Celery
- **Confidence Scoring**: Shows confidence levels when data is incomplete
- **Modern Web UI**: Beautiful, responsive interface for easy interaction

## 🏗️ Architecture

```
Input Job → Search LinkedIn → Extract Profiles → Score Fit → Generate Messages
     ↓                              ↓                ↓              ↓
   Queue → RapidAPI/Scraping → Parse Data → Fit Algorithm → GPT-4
```

## 🚀 Quick Start

1. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Set Environment Variables**
   ```bash
   cp .env.example .env
   # Edit .env with your API keys
   ```

3. **Start the Application**
   ```bash
   python main.py
   ```

4. **Access the Web Interface**
   ```
   http://localhost:8000
   ```

## 📊 Fit Score Rubric

- **Education (20%)**: Elite schools (9-10), Strong schools (7-8), Standard universities (5-6)
- **Career Trajectory (20%)**: Steady growth (6-8), Limited progression (3-5)
- **Company Relevance (15%)**: Top tech companies (9-10), Relevant industry (7-8)
- **Experience Match (25%)**: Perfect skill match (9-10), Strong overlap (7-8)
- **Location Match (10%)**: Exact city (10), Same metro (8), Remote-friendly (6)
- **Tenure (10%)**: 2-3 years average (9-10), 1-2 years (6-8), Job hopping (3-5)

## 🛠️ Technical Stack

- **Backend**: FastAPI + Python
- **Database**: PostgreSQL with SQLAlchemy
- **Task Queue**: Celery + Redis
- **AI/LLM**: OpenAI GPT-4
- **Web Scraping**: Selenium + BeautifulSoup
- **Frontend**: Modern HTML/CSS/JavaScript with Tailwind CSS

## 📈 Performance Features

- **Intelligent Rate Limiting**: Respects API limits and LinkedIn's terms
- **Smart Caching**: Redis-based caching for search results and profile data
- **Batch Processing**: Process multiple jobs in parallel
- **Error Handling**: Robust error handling and retry mechanisms
- **Data Validation**: Comprehensive input validation and data sanitization

## 🎯 Example Usage

```python
from agent import LinkedInSourcingAgent

# Initialize agent
agent = LinkedInSourcingAgent()

# Search for candidates
job_description = "Senior Backend Engineer at fintech startup..."
candidates = agent.search_linkedin(job_description)

# Score candidates
scored_candidates = agent.score_candidates(candidates, job_description)

# Generate outreach messages
messages = agent.generate_outreach(scored_candidates[:5], job_description)
```

## 📝 License

MIT License - Feel free to use this for your own projects! 