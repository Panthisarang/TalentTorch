from sqlalchemy import Column, Integer, String, Float, Text, DateTime, JSON, ForeignKey, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
from typing import Optional, Dict, Any

Base = declarative_base()


class Job(Base):
    __tablename__ = "jobs"
    
    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(String, unique=True, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    company = Column(String, nullable=False)
    location = Column(String, nullable=False)
    salary_range = Column(String)
    requirements = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String, default="pending")  # pending, processing, completed, failed
    
    # Relationships
    candidates = relationship("Candidate", back_populates="job")


class Candidate(Base):
    __tablename__ = "candidates"
    
    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id"))
    name = Column(String, nullable=False)
    linkedin_url = Column(String, nullable=False, unique=True)
    headline = Column(String)
    current_company = Column(String)
    location = Column(String)
    education = Column(JSON)
    experience = Column(JSON)
    skills = Column(JSON)
    github_url = Column(String)
    twitter_url = Column(String)
    personal_website = Column(String)
    extracted_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    job = relationship("Job", back_populates="candidates")
    scores = relationship("CandidateScore", back_populates="candidate")


class CandidateScore(Base):
    __tablename__ = "candidate_scores"
    
    id = Column(Integer, primary_key=True, index=True)
    candidate_id = Column(Integer, ForeignKey("candidates.id"))
    overall_score = Column(Float, nullable=False)
    education_score = Column(Float)
    trajectory_score = Column(Float)
    company_score = Column(Float)
    skills_score = Column(Float)
    location_score = Column(Float)
    tenure_score = Column(Float)
    score_breakdown = Column(JSON)
    confidence_level = Column(Float, default=1.0)
    scored_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    candidate = relationship("Candidate", back_populates="scores")


class OutreachMessage(Base):
    __tablename__ = "outreach_messages"
    
    id = Column(Integer, primary_key=True, index=True)
    candidate_id = Column(Integer, ForeignKey("candidates.id"))
    message_type = Column(String, default="linkedin")  # linkedin, email, etc.
    message_content = Column(Text, nullable=False)
    personalization_level = Column(Float, default=1.0)
    generated_at = Column(DateTime, default=datetime.utcnow)
    sent = Column(Boolean, default=False)
    sent_at = Column(DateTime)


class CacheEntry(Base):
    __tablename__ = "cache_entries"
    
    id = Column(Integer, primary_key=True, index=True)
    cache_key = Column(String, unique=True, index=True)
    cache_value = Column(JSON)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


# Pydantic models for API requests/responses
from pydantic import BaseModel
from typing import List, Optional, Dict, Any


class JobRequest(BaseModel):
    title: str
    description: str
    company: str
    location: str
    salary_range: Optional[str] = None
    requirements: Optional[Dict[str, Any]] = None


class JobResponse(BaseModel):
    job_id: str
    title: str
    company: str
    location: str
    status: str
    candidates_found: int
    created_at: datetime
    
    class Config:
        from_attributes = True


class CandidateResponse(BaseModel):
    name: str
    linkedin_url: str
    headline: Optional[str] = None
    current_company: Optional[str] = None
    location: Optional[str] = None
    overall_score: Optional[float] = None
    score_breakdown: Optional[Dict[str, float]] = None
    confidence_level: Optional[float] = None
    
    class Config:
        from_attributes = True


class OutreachResponse(BaseModel):
    candidate_name: str
    linkedin_url: str
    message: str
    personalization_level: float
    
    class Config:
        from_attributes = True


class SearchResult(BaseModel):
    job_id: str
    candidates_found: int
    top_candidates: List[CandidateResponse]
    processing_time: float
    cache_hit: bool = False 