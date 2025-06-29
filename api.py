from fastapi import FastAPI, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from agent import LinkedInSourcingAgent
from config import settings
import uvicorn
import asyncio
import traceback

app = FastAPI(title="LinkedIn Sourcing Agent API", description="Find, score, and message top candidates for any job.")

agent = LinkedInSourcingAgent()

from linkedin_scraper import LinkedInScraper
scraper = LinkedInScraper(use_serpapi=True, use_rapidapi=True)

from fastapi import Query
from pydantic import BaseModel

class LinkedInSearchRequest(BaseModel):
    query: str
    max_results: int = 10

@app.post("/search_linkedin_profiles")
async def search_linkedin_profiles(request: LinkedInSearchRequest):
    import traceback
    try:
        results = await scraper.search_linkedin_profiles(request.query, max_results=request.max_results)
        return {"results": results}
    except Exception as e:
        print(f"Exception in /search_linkedin_profiles for {request.query}: {e}")
        print(traceback.format_exc())
        return {"error": f"Internal server error: {str(e)}", "trace": traceback.format_exc()}, 500

@app.post("/fetch_profile")
def fetch_profile(linkedin_url: str):
    import traceback
    try:
        profile_data = scraper.extract_profile_data(linkedin_url)
        if not profile_data or (isinstance(profile_data, dict) and profile_data.get('error')):
            return {"error": profile_data.get('error', 'Profile not found or could not be scraped.')}, 400
        return profile_data
    except Exception as e:
        print(f"Exception in /fetch_profile for {linkedin_url}: {e}")
        print(traceback.format_exc())
        return {"error": f"Internal server error: {str(e)}", "trace": traceback.format_exc()}, 500

class JobInput(BaseModel):
    job_id: Optional[str] = None
    title: str
    company: str
    location: str
    employment_type: Optional[str] = None
    work_mode: Optional[str] = None
    compensation: Optional[str] = None
    description: str
    responsibilities: Optional[List[str]] = []
    requirements: Optional[List[str]] = []
    interview_process: Optional[List[str]] = []

class BatchJobRequest(BaseModel):
    jobs: List[JobInput]
    top_n: int = 10

@app.post("/candidates")
async def get_candidates(request: BatchJobRequest):
    # Only focus on getting most relevant candidates for each job
    output = []
    for job in request.jobs:
        # Build search query from job title, location, and key requirements
        search_terms = f"{job.title} {job.location} " + " ".join(job.requirements[:3])
        candidates = await scraper.search_linkedin_profiles(search_terms, max_results=request.top_n * 3)
        scored_candidates = []
        for cand in candidates:
            # Extract profile data and score
            profile_data = scraper.extract_profile_data(cand['url'])
            # Score profile for fit (simple example, can be improved)
            fit_score, score_breakdown = score_profile_for_job(profile_data, job)
            scored_candidates.append({
                "name": profile_data.get("name", ""),
                "linkedin_url": cand['url'],
                "fit_score": fit_score,
                "score_breakdown": score_breakdown,
                "outreach_message": generate_outreach_message(profile_data, job)
            })
        # Sort by fit_score and take top N
        scored_candidates.sort(key=lambda x: x["fit_score"], reverse=True)
        top_candidates = scored_candidates[:request.top_n]
        output.append({
            "job_id": job.job_id or job.title.replace(" ", "-").lower(),
            "candidates_found": len(scored_candidates),
            "top_candidates": top_candidates
        })
    return output

# --- Helper functions ---
def score_profile_for_job(profile_data, job):
    # Example scoring logic, can be replaced with your fit algorithm
    score = 0
    breakdown = {}
    # Education
    elite = [school for school in (profile_data.get("education") or []) if any(e in school.get("school", "") for e in settings.elite_schools)]
    breakdown["education"] = 10.0 if elite else 5.0
    score += breakdown["education"] * settings.education_weight
    # Trajectory (years of experience)
    exp = len(profile_data.get("experience") or [])
    breakdown["trajectory"] = min(10.0, exp)
    score += breakdown["trajectory"] * settings.trajectory_weight
    # Company (match to job company)
    breakdown["company"] = 10.0 if job.company.lower() in (profile_data.get("current_company", "").lower()) else 6.0
    score += breakdown["company"] * settings.company_weight
    # Skills
    job_skills = set([s.lower() for s in job.requirements if len(s) < 30])
    cand_skills = set([s.lower() for s in profile_data.get("skills", [])])
    match = len(job_skills & cand_skills)
    breakdown["skills"] = min(10.0, 5.0 + match * 2.0)
    score += breakdown["skills"] * settings.skills_weight
    # Location
    breakdown["location"] = 10.0 if job.location.lower() in (profile_data.get("location", "").lower()) else 5.0
    score += breakdown["location"] * settings.location_weight
    # Tenure
    tenure = 0
    for exp in (profile_data.get("experience") or []):
        if exp.get("company", "").lower() == job.company.lower():
            tenure += 1
    breakdown["tenure"] = min(10.0, tenure)
    score += breakdown["tenure"] * settings.tenure_weight
    # Normalize
    score = round(score, 2)
    for k in breakdown:
        breakdown[k] = round(breakdown[k], 1)
    return score, breakdown

def generate_outreach_message(profile_data, job):
    # Simple example, can be replaced with GPT
    name = profile_data.get("name", "there")
    return f"Hi {name}, I noticed your background in {job.title} and wanted to connect about an opportunity at {job.company}."


async def batch_process_jobs(jobs: List[JobInput], top_n: int):
    # Process jobs in parallel using asyncio
    tasks = [process_single_job(job, top_n) for job in jobs]
    return await asyncio.gather(*tasks)

async def process_single_job(job: JobInput, top_n: int):
    # 1. Search candidates
    candidates = agent.search_linkedin(job.description, max_results=top_n*2)  # fetch extra for scoring
    # 2. Score candidates (fit score, breakdown, confidence)
    scored = agent.score_candidates(candidates, job.description)
    # 3. Multi-source enrichment (GitHub/Twitter)
    for c in scored:
        enrich_with_github_twitter(c)
    # 4. Outreach messages
    messages = agent.generate_outreach(scored[:top_n], job.description)
    # 5. Compose output JSON
    return {
        "job_id": job.job_id or hash(job.description),
        "candidates_found": len(scored),
        "top_candidates": [
            {
                "name": c["name"],
                "linkedin_url": c["linkedin_url"],
                "fit_score": c["fit_score"],
                "score_breakdown": c["score_breakdown"],
                "confidence_level": c["confidence_level"],
                "github_url": c.get("github_url"),
                "twitter_url": c.get("twitter_url"),
                "outreach_message": m["message"]
            }
            for c, m in zip(scored[:top_n], messages)
        ]
    }

def enrich_with_github_twitter(candidate: Dict[str, Any]):
    # Multi-source enrichment (mock or real)
    # GitHub: If github_url present, mock stars/repos
    if candidate.get("github_url"):
        candidate["github_stars"] = 42  # mock
        candidate["github_repos"] = 10  # mock
    # Twitter: If twitter_url present, mock followers
    if candidate.get("twitter_url"):
        candidate["twitter_followers"] = 1234  # mock
    # Personal website: Could scrape for keywords (not implemented)

if __name__ == "__main__":
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
