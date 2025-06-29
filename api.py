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
import random

def score_profile_for_job(profile_data, job):
    """
    Fit Score Rubric (Simplified):
    - Education (20%)
    - Career Trajectory (20%)
    - Company Relevance (15%)
    - Experience Match (25%)
    - Location Match (10%)
    - Tenure (10%)
    Each category is scored 0-10, then weighted.
    """
    import random
    score = 0
    breakdown = {}

    # --- Education (20%) ---
    # Elite schools (MIT, Stanford, etc.): 9-10
    # Strong schools: 7-8
    # Standard universities: 5-6
    # Clear progression: 8-10
    elite_schools = set(s.lower() for s in getattr(settings, "elite_schools", []))
    strong_schools = set(s.lower() for s in getattr(settings, "strong_schools", [])) if hasattr(settings, "strong_schools") else set()
    educations = profile_data.get("education") or []
    edu_score = 0
    if educations:
        for edu in educations:
            school = (edu.get("school") or "").lower()
            if any(es in school for es in elite_schools):
                edu_score = max(edu_score, 10)
            elif any(ss in school for ss in strong_schools):
                edu_score = max(edu_score, 8)
            elif school:
                edu_score = max(edu_score, 6)
        # Progression: more than 1 degree or increasing degree level
        if len(educations) > 1:
            edu_score = max(edu_score, 8)
    breakdown["education"] = edu_score if edu_score else 2
    score += breakdown["education"] * 0.20

    # --- Career Trajectory (20%) ---
    # Steady growth: 6-8, Limited progression: 3-5
    experience = profile_data.get("experience") or []
    trajectory_score = 0
    if experience:
        # Steady growth: increasing responsibility or title
        titles = [e.get("title", "").lower() for e in experience if e.get("title")]
        if len(titles) >= 2 and any("lead" in t or "manager" in t or "head" in t for t in titles):
            trajectory_score = 8
        elif len(titles) >= 2:
            trajectory_score = 6
        else:
            trajectory_score = 4
    breakdown["trajectory"] = trajectory_score if trajectory_score else 3
    score += breakdown["trajectory"] * 0.20

    # --- Company Relevance (15%) ---
    # Top tech companies: 9-10, Relevant industry: 7-8, Any experience: 5-6
    top_companies = set(s.lower() for s in getattr(settings, "top_companies", [])) if hasattr(settings, "top_companies") else set()
    relevant_industries = set(s.lower() for s in getattr(settings, "relevant_industries", [])) if hasattr(settings, "relevant_industries") else set()
    cand_company = (profile_data.get("current_company") or "").lower()
    company_score = 0
    if cand_company:
        if any(tc in cand_company for tc in top_companies):
            company_score = 10
        elif any(ri in cand_company for ri in relevant_industries):
            company_score = 8
        else:
            company_score = 6
    elif experience:
        companies = [e.get("company", "").lower() for e in experience if e.get("company")]
        if any(tc in c for tc in top_companies for c in companies):
            company_score = 9
        elif any(ri in c for ri in relevant_industries for c in companies):
            company_score = 7
        elif companies:
            company_score = 5
    breakdown["company"] = company_score if company_score else 3
    score += breakdown["company"] * 0.15

    # --- Experience Match (25%) ---
    # Perfect skill match: 9-10, Strong overlap: 7-8, Some: 5-6
    job_skills = set([s.lower() for s in job.requirements if len(s) < 30])
    cand_skills = set([s.lower() for s in profile_data.get("skills", [])])
    overlap = job_skills & cand_skills
    if len(overlap) >= max(len(job_skills), 3):
        exp_score = 10
    elif len(overlap) >= 2:
        exp_score = 8
    elif len(overlap) == 1:
        exp_score = 6
    else:
        exp_score = 3
    breakdown["experience_match"] = exp_score
    score += exp_score * 0.25

    # --- Location Match (10%) ---
    # Exact city: 10, Same metro: 8, Remote-friendly: 6
    cand_location = (profile_data.get("location") or "").lower()
    job_location = (job.location or "").lower()
    location_score = 2
    if job_location and job_location in cand_location:
        location_score = 10
    elif job_location and any(part in cand_location for part in job_location.split()):
        location_score = 8
    elif "remote" in cand_location or "remote" in job_location:
        location_score = 6
    breakdown["location"] = location_score
    score += location_score * 0.10

    # --- Tenure (10%) ---
    # 2-3 years avg: 9-10, 1-2 years: 6-8, Job hopping: 3-5
    tenure_years = 0
    companies = {}
    for exp in experience:
        company = exp.get("company", "")
        if company:
            companies.setdefault(company, 0)
            companies[company] += 1
    avg_tenure = (sum(companies.values()) / len(companies)) if companies else 0
    if avg_tenure >= 2:
        tenure_score = 10
    elif avg_tenure >= 1:
        tenure_score = 7
    elif avg_tenure > 0:
        tenure_score = 4
    else:
        tenure_score = 2
    breakdown["tenure"] = tenure_score
    score += tenure_score * 0.10

    # Add mild randomness to break ties
    score += random.uniform(0, 1)
    score = round(score, 2)
    for k in breakdown:
        breakdown[k] = round(breakdown[k], 1)
    return score, breakdown


def generate_outreach_message(profile_data, job):
    """
    Personalized outreach: includes name, job title, company, and, if available, a top skill or experience.
    Always generates a message, even for incomplete profiles.
    """
    name = profile_data.get("name") or "there"
    # Try to highlight a relevant skill or experience
    skills = profile_data.get("skills") or []
    experience = profile_data.get("experience") or []
    highlight = ""
    if skills:
        highlight = f" I was impressed by your skill in {skills[0]}."
    elif experience:
        first_exp = experience[0]
        if first_exp.get("title"):
            highlight = f" Your experience as {first_exp['title']} stood out."
    return (
        f"Hi {name}, I came across your profile while searching for talented professionals in {job.title}."
        f" We're looking for someone like you at {job.company}.{highlight} If you're open to new opportunities, I'd love to connect!"
    )


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
