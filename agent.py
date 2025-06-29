from typing import List, Dict, Any
from config import settings
from linkedin_scraper import LinkedInScraper
import openai
import random

class LinkedInSourcingAgent:
    def __init__(self):
        self.scraper = LinkedInScraper()
        openai.api_key = settings.openai_api_key

    def search_linkedin(self, job_description: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """
        Search for LinkedIn profiles matching the job description.
        """
        return self.scraper.search_linkedin_profiles(job_description, max_results)

    def score_candidates(self, candidates: List[Dict[str, Any]], job_description: str) -> List[Dict[str, Any]]:
        """
        Score candidates using the fit score rubric.
        """
        scored = []
        for c in candidates:
            profile = self.scraper.extract_profile_data(c.get("linkedin_url", ""))
            score, breakdown, confidence = self._fit_score(profile, job_description)
            scored.append({
                **profile,
                "fit_score": score,
                "score_breakdown": breakdown,
                "confidence_level": confidence
            })
        # Sort by score
        scored.sort(key=lambda x: x["fit_score"], reverse=True)
        return scored

    def _fit_score(self, profile: Dict[str, Any], job_description: str):
        # Simplified rubric using settings weights
        weights = settings
        breakdown = {}
        confidence = 1.0
        # Education
        education_score = 5
        if profile.get("education"):
            school = profile["education"][0].get("school", "")
            if school in weights.elite_schools:
                education_score = 9
            elif school:
                education_score = 7
        breakdown["education"] = education_score
        # Trajectory (mock: if >1 experience entries and increasing responsibility)
        trajectory_score = 8 if profile.get("experience") and len(profile["experience"]) > 1 else 6
        breakdown["trajectory"] = trajectory_score
        # Company
        company_score = 5
        if profile.get("current_company") in weights.top_tech_companies:
            company_score = 9
        elif profile.get("current_company"):
            company_score = 7
        breakdown["company"] = company_score
        # Skills
        skills_score = 5
        if profile.get("skills"):
            # crude match: count overlap
            job_skills = [s.lower() for s in ["python", "machine learning", "llm", "deep learning", "backend", "api"] if s in job_description.lower()]
            overlap = len(set([s.lower() for s in profile["skills"]]) & set(job_skills))
            if overlap >= 3:
                skills_score = 9
            elif overlap == 2:
                skills_score = 7
            elif overlap == 1:
                skills_score = 6
        breakdown["skills"] = skills_score
        # Location
        location_score = 6
        if profile.get("location") and profile["location"] in job_description:
            location_score = 10
        breakdown["location"] = location_score
        # Tenure
        tenure_score = 7
        if profile.get("experience"):
            tenure = profile["experience"][0].get("duration", "")
            if "2 years" in tenure or "3 years" in tenure:
                tenure_score = 9
            elif "1 year" in tenure:
                tenure_score = 6
            elif "months" in tenure:
                tenure_score = 4
        breakdown["tenure"] = tenure_score
        # Weighted sum
        score = (
            education_score * weights.education_weight +
            trajectory_score * weights.trajectory_weight +
            company_score * weights.company_weight +
            skills_score * weights.skills_weight +
            location_score * weights.location_weight +
            tenure_score * weights.tenure_weight
        )
        # Confidence: penalize missing data
        missing = sum(1 for v in [profile.get("education"), profile.get("experience"), profile.get("skills")] if not v)
        confidence = max(0.5, 1.0 - 0.15 * missing)
        return round(score, 2), breakdown, confidence

    def generate_outreach(self, candidates: List[Dict[str, Any]], job_description: str) -> List[Dict[str, Any]]:
        """
        Generate personalized outreach messages for candidates.
        """
        messages = []
        for c in candidates:
            message = self._generate_message(c, job_description)
            messages.append({
                "candidate": c["name"],
                "linkedin_url": c["linkedin_url"],
                "message": message
            })
        return messages

    def _generate_message(self, candidate: Dict[str, Any], job_description: str) -> str:
        # Use OpenAI if key provided, else template
        if settings.openai_api_key:
            prompt = (
                f"Write a concise, professional LinkedIn message to {candidate['name']} for the following job: {job_description}. "
                f"Highlight their background: {candidate['headline']}, {candidate['current_company']}, {candidate['education']}, {candidate['skills']}. "
                "Explain why they're a great fit."
            )
            try:
                response = openai.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=120
                )
                return response.choices[0].message.content.strip()
            except Exception as e:
                return f"Hi {candidate['name']}, we'd love to connect about a new opportunity! (OpenAI error: {e})"
        else:
            # Fallback template
            return (
                f"Hi {candidate['name']}, I came across your profile and was impressed by your experience at {candidate.get('current_company', 'your company')}. "
                f"Your background in {', '.join(candidate.get('skills', []))} and education at {candidate.get('education', [{}])[0].get('school', 'your school')} "
                f"seems like a great fit for our role: {job_description[:40]}... Let me know if you’re open to chat!"
            )
