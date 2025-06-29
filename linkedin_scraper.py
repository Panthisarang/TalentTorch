import time
import random
import logging
import asyncio
import requests
from typing import List, Dict, Any, Optional
from urllib.parse import quote_plus, urlparse
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
from googlesearch import search as google_search

from config import settings
from database import db_manager

try:
    from serpapi import GoogleSearch as SerpAPIClient
    SERPAPI_AVAILABLE = True
except ImportError:
    SERPAPI_AVAILABLE = False

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class LinkedInScraper:
    def __init__(
        self,
        use_rapidapi: bool = False,
        use_serpapi: bool = False,
        proxies: Optional[List[str]] = None
    ):
        self.ua = UserAgent()
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": self.ua.random,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Connection": "keep-alive",
        })

        self.proxies = proxies or []
        self.proxy_index = 0

        self.use_rapidapi = use_rapidapi and bool(getattr(settings, "rapidapi_key", None))
        self.rapidapi_key = getattr(settings, "rapidapi_key", None)
        self.rapidapi_hosts = [
            "linkedin-profile-scraper4.p.rapidapi.com",
            "fresh-linkedin-profile-data.p.rapidapi.com"
        ]

        self.use_serpapi = (
            use_serpapi
            and SERPAPI_AVAILABLE
            and bool(getattr(settings, "serpapi_key", None))
        )
        self.serpapi_key = getattr(settings, "serpapi_key", None)

        self.rate_limit_delay = 2  # seconds

    def _get_proxy(self) -> Optional[Dict[str, str]]:
        if not self.proxies:
            return None
        url = self.proxies[self.proxy_index % len(self.proxies)]
        self.proxy_index += 1
        return {"http": url, "https": url}

    async def _search_google_async(self, query: str, max_results: int):
        return await asyncio.get_event_loop().run_in_executor(
            None, self._search_google, query, max_results
        )

    async def _search_rapidapi_async(self, query: str, max_results: int):
        return await asyncio.get_event_loop().run_in_executor(
            None, self._search_rapidapi, query, max_results
        )

    async def search_linkedin_profiles(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """
        Parallel Google + RapidAPI searches, falling back to direct LinkedIn search.
        Caches results in Redis/SQLite via db_manager.
        """
        cache_key = f"linkedin_search:{hash(query)}"
        cached = db_manager.get_cache(cache_key)
        if cached:
            logger.info(f"Cache hit for query '{query}'")
            return cached

        async def _gather():
            tasks = [self._search_google_async(query, max_results)]
            if self.use_rapidapi:
                tasks.append(self._search_rapidapi_async(query, max_results))
            results = await asyncio.gather(*tasks, return_exceptions=True)

            seen = set()
            out = []
            for res in results:
                if isinstance(res, list):
                    for profile in res:
                        url = profile.get("url") or profile.get("linkedin_url")
                        if url and url not in seen:
                            seen.add(url)
                            out.append(profile)
                            if len(out) >= max_results:
                                return out
            return out

        try:
            profiles = await _gather()
        except Exception as e:
            logger.warning(f"Async gather failed: {e}")
            profiles = []

        # If nothing yet, try to force-add SerpAPI raw results if available
        if not profiles and self.use_serpapi:
            try:
                serpapi_q = f"{query} site:linkedin.com/in"
                import requests
                params = {
                    "engine": "google",
                    "q": serpapi_q,
                    "api_key": self.serpapi_key,
                    "num": max_results
                }
                response = requests.get("https://serpapi.com/search", params=params)
                raw = response.json()
                print("SERPAPI RAW RESPONSE (fallback):", raw)
                forced_profiles = []
                for item in raw.get("organic_results", []):
                    link = item.get("link")
                    if link:
                        forced_profiles.append({
                            "url": link,
                            "title": item.get("title", ""),
                            "description": item.get("snippet", ""),
                            "source": "serpapi"
                        })
                        if len(forced_profiles) >= max_results:
                            break
                if forced_profiles:
                    profiles = forced_profiles
                    print("FORCED SERPAPI PROFILES (fallback):", profiles)
            except Exception as e:
                print("SERPAPI fallback error:", e)

        # If still nothing, try direct LinkedIn search
        if not profiles:
            logger.info("No results from APIs, falling back to direct LinkedIn search")
            profiles = self._search_direct(query, max_results)

        # Ensure at least a dummy result
        if not profiles:
            profiles = [{"url": "", "name": "No candidates found", "source": "fallback"}]

        db_manager.set_cache(cache_key, profiles)
        return profiles[:max_results]

    def _search_google(self, query: str, max_results: int) -> List[Dict[str, str]]:
        """Use either SerpAPI or googlesearch-python to hit Google."""
        search_query = f"{query} site:linkedin.com/in"
        logger.info(f"Google search: {search_query}")
        time.sleep(random.uniform(5, 10))

        proxies = self._get_proxy()
        results: List[Dict[str, str]] = []

        if self.use_serpapi:
            if not SERPAPI_AVAILABLE:
                raise ImportError("Please `pip install google-search-results` for SerpAPI support")
            if not self.serpapi_key:
                raise ValueError("`settings.serpapi_key` not set")
            serpapi_q = f"{query} site:linkedin.com/in"
            client = SerpAPIClient({"engine": "google", "q": serpapi_q, "api_key": self.serpapi_key, "num": max_results})
            data = client.get_dict()
            # DEBUG PRINT: raw SerpAPI response
            print("SERPAPI RAW RESPONSE:", data)
            for item in data.get("organic_results", []):
                link = item.get("link")
                if link:
                    results.append({
                        "url": link,
                        "title": item.get("title", ""),
                        "description": item.get("snippet", ""),
                        "source": "serpapi"
                    })
                    if len(results) >= max_results:
                        break
            # DEBUG PRINT: parsed profiles
            print("SERPAPI PARSED PROFILES:", results)
        else:
            for url in google_search(search_query, num_results=max_results, proxies=proxies):
                if "linkedin.com/in/" in url:
                    results.append({"url": url, "source": "google_search"})
                    if len(results) >= max_results:
                        break
        print("GOOGLE SEARCH FINAL PROFILES:", results)
        return results

    def _search_rapidapi(self, query: str, max_results: int) -> List[Dict[str, str]]:
        """Rotate through RapidAPI hosts, gathering up to `max_results` profiles."""
        if not self.use_rapidapi:
            return []
        profiles = []
        for host in self.rapidapi_hosts:
            url = f"https://{host}/search"
            headers = {
                "x-rapidapi-key": self.rapidapi_key,
                "x-rapidapi-host": host
            }
            params = {"query": query, "limit": max_results}
            try:
                resp = self.session.get(url, headers=headers, params=params, timeout=10)
                resp.raise_for_status()
                data = resp.json().get("data", [])
                for p in data:
                    public_id = p.get("public_id", "")
                    profiles.append({
                        "url": f"https://www.linkedin.com/in/{public_id}",
                        "name": p.get("full_name", ""),
                        "headline": p.get("headline", ""),
                        "source": f"rapidapi:{host}"
                    })
                    if len(profiles) >= max_results:
                        return profiles
            except Exception as e:
                logger.error(f"RapidAPI host {host} error: {e}")
        return profiles

    def _search_direct(self, query: str, max_results: int) -> List[Dict[str, str]]:
        """Simple LinkedIn people search page scrape (best‐effort)."""
        logger.info(f"Direct LinkedIn search for '{query}'")
        url = "https://www.linkedin.com/search/results/people/"
        params = {"keywords": query, "origin": "GLOBAL_SEARCH_HEADER"}
        headers = {
            "User-Agent": self.ua.random,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9"
        }

        try:
            resp = self.session.get(url, params=params, headers=headers, timeout=10)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            out = []
            for a in soup.select('a.app-aware-link[href*="/in/"]'):
                href = a["href"].split("?")[0]
                full = href if href.startswith("http") else "https://linkedin.com" + href
                out.append({"url": full, "source": "direct_linkedin"})
                if len(out) >= max_results:
                    break
            return out
        except Exception as e:
            logger.error(f"Direct search failed: {e}")
            return []

    def _extract_search_terms(self, job_description: str) -> Dict[str, str]:
        """Extract key search terms from job description"""
        # Simple keyword extraction - in production, use NLP
        keywords = []

        
        # Common job titles
        job_titles = [
            "software engineer", "backend engineer", "frontend engineer", "full stack engineer",
            "data scientist", "machine learning engineer", "devops engineer", "product manager",
            "designer", "researcher", "analyst"
        ]
        
        # Common skills
        skills = [
            "python", "javascript", "java", "react", "node.js", "aws", "docker", "kubernetes",
            "machine learning", "ai", "data science", "sql", "postgresql", "mongodb"
        ]
        
        # Extract job title
        job_title = None
        for title in job_titles:
            if title.lower() in job_description.lower():
                job_title = title
                break
        
        # Extract skills
        found_skills = []
        for skill in skills:
            if skill.lower() in job_description.lower():
                found_skills.append(skill)
        
        # Extract location (simple regex)
        location_match = re.search(r'(?:in|at|based in)\s+([A-Za-z\s,]+?)(?:\s|$|\.)', job_description, re.IGNORECASE)
        location = location_match.group(1).strip() if location_match else ""
        
        return {
            "job_title": job_title or "software engineer",
            "skills": found_skills[:3],  # Top 3 skills
            "location": location,
            "company_type": self._extract_company_type(job_description)
        }
    
    def _extract_company_type(self, description: str) -> str:
        """Extract company type from description"""
        company_types = {
            "startup": ["startup", "early stage", "seed", "series a", "series b"],
            "fintech": ["fintech", "financial", "banking", "payments", "crypto"],
            "ai": ["ai", "artificial intelligence", "machine learning", "ml"],
            "saas": ["saas", "software as a service", "b2b", "enterprise"]
        }
        
        description_lower = description.lower()
        for company_type, keywords in company_types.items():
            if any(keyword in description_lower for keyword in keywords):
                return company_type
        
        return "tech"
    
    def _google_search_strategy(self, search_terms: Dict[str, str], max_results: int) -> List[Dict[str, Any]]:
        """Search using Google with site:linkedin.com/in"""
        candidates = []
        
        # Build search query
        query_parts = [f'site:linkedin.com/in "{search_terms["job_title"]}"']
        
        if search_terms["skills"]:
            query_parts.append(f'"{search_terms["skills"][0]}"')
        
        if search_terms["location"]:
            query_parts.append(f'"{search_terms["location"]}"')
        
        if search_terms["company_type"] != "tech":
            query_parts.append(f'"{search_terms["company_type"]}"')
        
        query = " ".join(query_parts)
        
        # Google search URL (in production, use Google Search API)
        search_url = f"https://www.google.com/search?q={quote_plus(query)}&num={max_results}"
        
        try:
            response = self.session.get(search_url)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract LinkedIn URLs from search results
            for link in soup.find_all('a', href=True):
                href = link['href']
                if 'linkedin.com/in/' in href:
                    # Extract LinkedIn URL
                    linkedin_match = re.search(r'https?://[^/]*linkedin\.com/in/[^/\s]+', href)
                    if linkedin_match:
                        linkedin_url = linkedin_match.group(0)
                        
                        # Extract name from link text or URL
                        name = link.get_text().strip()
                        if not name or len(name) < 2:
                            name = linkedin_url.split('/in/')[-1].replace('-', ' ').title()
                        
                        candidates.append({
                            "name": name,
                            "linkedin_url": linkedin_url,
                            "source": "google_search"
                        })
            
            time.sleep(self.rate_limit_delay)
            
        except Exception as e:
            print(f"Google search failed: {e}")
        
        return candidates
    
    def _rapidapi_strategy(self, search_terms: Dict[str, str], max_results: int) -> List[Dict[str, Any]]:
        """Search using RapidAPI LinkedIn API"""
        if not settings.rapidapi_key:
            return []
        
        candidates = []
        
        headers = {
            'X-RapidAPI-Key': settings.rapidapi_key,
            'X-RapidAPI-Host': settings.rapidapi_host
        }
        
        try:
            # Search for profiles
            search_url = "https://linkedin-profile-data.p.rapidapi.com/search"
            
            params = {
                'query': f'{search_terms["job_title"]} {search_terms["location"]}',
                'limit': max_results
            }
            
            response = self.session.get(search_url, headers=headers, params=params)
            response.raise_for_status()
            
            data = response.json()
            
            if 'data' in data:
                for profile in data['data']:
                    candidates.append({
                        "name": profile.get('name', 'Unknown'),
                        "linkedin_url": profile.get('linkedin_url', ''),
                        "headline": profile.get('headline', ''),
                        "current_company": profile.get('company', ''),
                        "location": profile.get('location', ''),
                        "source": "rapidapi"
                    })
            
            time.sleep(self.rate_limit_delay)
            
        except Exception as e:
            print(f"RapidAPI search failed: {e}")
        
        return candidates
    
    def _direct_linkedin_strategy(self, search_terms: Dict[str, str], max_results: int) -> List[Dict[str, Any]]:
        """Direct LinkedIn search (limited due to anti-bot measures)"""
        # This is a simplified version - in production, you'd need more sophisticated handling
        candidates = []
        
        # Generate some sample profiles for demonstration
        sample_profiles = [
            {
                "name": "Sarah Johnson",
                "linkedin_url": "https://linkedin.com/in/sarah-johnson-ai",
                "headline": "Senior ML Engineer at TechCorp",
                "current_company": "TechCorp",
                "location": "San Francisco, CA",
                "source": "sample"
            },
            {
                "name": "Michael Chen",
                "linkedin_url": "https://linkedin.com/in/michael-chen-dev",
                "headline": "Backend Engineer | Python | AWS",
                "current_company": "StartupXYZ",
                "location": "Mountain View, CA",
                "source": "sample"
            },
            {
                "name": "Emily Rodriguez",
                "linkedin_url": "https://linkedin.com/in/emily-rodriguez",
                "headline": "Software Engineer | Full Stack | React",
                "current_company": "FinTech Inc",
                "location": "New York, NY",
                "source": "sample"
            }
        ]
        
        return sample_profiles[:max_results]
    
    def _deduplicate_candidates(self, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove duplicate candidates based on LinkedIn URL"""
        seen_urls = set()
        unique_candidates = []
        
        for candidate in candidates:
            url = candidate.get('linkedin_url', '')
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_candidates.append(candidate)
        
        return unique_candidates
    
    def extract_profile_data(self, linkedin_url: str) -> Dict[str, Any]:
        """
        Scrape public LinkedIn profile data using requests and BeautifulSoup.
        """
        cache_key = f"profile_data:{hash(linkedin_url)}"
        cached_data = db_manager.get_cache(cache_key)
        if cached_data:
            return cached_data

        headers = {
            'User-Agent': self.ua.random,
            'Accept-Language': 'en-US,en;q=0.9',
        }
        profile_data = {
            "linkedin_url": linkedin_url,
            "name": "",
            "headline": "",
            "current_company": "",
            "location": "",
            "education": [],
            "experience": [],
            "skills": [],
            "github_url": "",
            "twitter_url": "",
            "personal_website": ""
        }
        try:
            resp = self.session.get(linkedin_url, headers=headers, timeout=20)
            if resp.status_code != 200:
                raise Exception(f"Failed to fetch profile: {resp.status_code}")
            soup = BeautifulSoup(resp.text, 'html.parser')
            # Name
            name_tag = soup.find('h1')
            if name_tag:
                profile_data["name"] = name_tag.get_text(strip=True)
            # Headline
            headline_tag = soup.find('div', class_=lambda x: x and 'text-body-medium' in x)
            if headline_tag:
                profile_data["headline"] = headline_tag.get_text(strip=True)
            # Location
            loc_tag = soup.find('span', class_=lambda x: x and 'text-body-small' in x)
            if loc_tag:
                profile_data["location"] = loc_tag.get_text(strip=True)
            # Experience (simple)
            exp_section = soup.find('section', {'id': 'experience'})
            if exp_section:
                jobs = exp_section.find_all('li')
                for job in jobs:
                    title = job.find('span', {'class': 'mr1'})
                    company = job.find('span', {'class': 't-14'})
                    if title or company:
                        profile_data['experience'].append({
                            'title': title.get_text(strip=True) if title else '',
                            'company': company.get_text(strip=True) if company else ''
                        })
            # Education (simple)
            edu_section = soup.find('section', {'id': 'education'})
            if edu_section:
                schools = edu_section.find_all('li')
                for school in schools:
                    school_name = school.find('span', {'class': 'mr1'})
                    degree = school.find('span', {'class': 't-14'})
                    if school_name or degree:
                        profile_data['education'].append({
                            'school': school_name.get_text(strip=True) if school_name else '',
                            'degree': degree.get_text(strip=True) if degree else ''
                        })
            # Skills (public profiles rarely show, but attempt)
            skills_section = soup.find('section', {'id': 'skills'})
            if skills_section:
                skills = [s.get_text(strip=True) for s in skills_section.find_all('span', {'class': 'mr1'})]
                profile_data['skills'] = skills
            # Social links (try to extract from summary/about)
            about_section = soup.find('section', {'id': 'about'})
            if about_section:
                about_text = about_section.get_text()
                github_match = re.search(r"https?://github.com/\w+", about_text)
                twitter_match = re.search(r"https?://twitter.com/\w+", about_text)
                web_match = re.search(r"https?://[\w.-]+\.[a-z]{2,}", about_text)
                if github_match:
                    profile_data['github_url'] = github_match.group(0)
                if twitter_match:
                    profile_data['twitter_url'] = twitter_match.group(0)
                if web_match and not github_match and not twitter_match:
                    profile_data['personal_website'] = web_match.group(0)
            db_manager.set_cache(cache_key, profile_data)
            return profile_data
        except Exception as e:
            print(f"Profile extraction failed for {linkedin_url}: {e}")
            return profile_data

    def _extract_public_id(self, url: str) -> Optional[str]:
        try:
            parsed = urlparse(url)
            if 'linkedin.com/in/' not in url:
                return None
            path_parts = [p for p in parsed.path.split('/') if p]
            if not path_parts:
                return None
            public_id = path_parts[-1]
            if '?' in public_id:
                public_id = public_id.split('?')[0]
            return public_id
        except Exception:
            return None

    def _find_github(self, profile: dict) -> str:
        # Try to extract a GitHub URL from the profile's websites or summary
        websites = profile.get("websites", [])
        for w in websites:
            if "github.com" in w:
                return w
        summary = profile.get("summary", "")
        match = re.search(r"https?://github.com/\w+", summary)
        return match.group(0) if match else ""

    def _find_twitter(self, profile: dict) -> str:
        # Try to extract a Twitter URL from the profile's websites or summary
        websites = profile.get("websites", [])
        for w in websites:
            if "twitter.com" in w:
                return w
        summary = profile.get("summary", "")
        match = re.search(r"https?://twitter.com/\w+", summary)
        return match.group(0) if match else ""

    def _find_website(self, profile: dict) -> str:
        websites = profile.get("websites", [])
        for w in websites:
            if "github.com" not in w and "twitter.com" not in w:
                return w
        return ""

    def score_profile(self, profile_data: dict, job_description: str) -> float:
        """
        Score a LinkedIn profile for relevance to a job description.
        This is a basic example; you can expand with NLP or more advanced logic.
        """
        score = 0
        if not profile_data or not job_description:
            return score
        # Lowercase everything for matching
        jd = job_description.lower()
        # Score headline and skills
        if profile_data.get("headline") and any(skill.lower() in jd for skill in profile_data.get("skills", [])):
            score += 30
        # Score experience
        for exp in profile_data.get("experience", []):
            title = exp.get("title", "").lower()
            company = exp.get("companyName", "").lower()
            if title and title in jd:
                score += 15
            if company and company in jd:
                score += 10
        # Score education
        for edu in profile_data.get("education", []):
            school = edu.get("schoolName", "").lower()
            if school and school in jd:
                score += 5
        # Score for location match
        location = profile_data.get("location", "").lower()
        if location and location in jd:
            score += 10
        # Cap score at 100
        return min(score, 100)