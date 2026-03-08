"""
Metabase Service
-----------------
Fetches and structures the candidate's full profile from SQLite.
Ranks skills/projects/experience by relevance for the AI tailoring stage.
"""
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.db.models import (
    PersonalInfo, Skill, Project, ProjectBullet,
    WorkExperience, ExperienceBullet, Education
)

logger = logging.getLogger(__name__)


class MetabaseService:

    def get_full_profile(self, db: Session) -> Dict[str, Any]:
        """
        Build and return the complete candidate profile dict.
        Used by the AI agent as context for tailoring.
        """
        profile = {
            "personal":   self._get_personal(db),
            "skills":     self._get_skills(db),
            "experience": self._get_experience(db),
            "projects":   self._get_projects(db),
            "education":  self._get_education(db),
        }
        logger.info(
            f"Profile loaded — {len(profile['skills'])} skills, "
            f"{len(profile['experience'])} roles, "
            f"{len(profile['projects'])} projects"
        )
        return profile

    # ── Personal Info ──────────────────────────────────────────────────────────

    def _get_personal(self, db: Session) -> Optional[Dict]:
        info = db.query(PersonalInfo).first()
        if not info:
            return None
        return {
            "full_name":            info.full_name,
            "email":                info.email,
            "phone":                info.phone,
            "location":             info.location,
            "linkedin":             info.linkedin,
            "github":               info.github,
            "portfolio":            info.portfolio,
            "professional_summary": info.professional_summary,
        }

    # ── Skills ─────────────────────────────────────────────────────────────────

    def _get_skills(self, db: Session) -> List[Dict]:
        skills = db.query(Skill).order_by(
            Skill.is_primary.desc(),
            Skill.years_experience.desc()
        ).all()
        return [
            {
                "name":             s.name,
                "category":         s.category,
                "proficiency":      s.proficiency,
                "years_experience": s.years_experience,
                "keywords":         s.keywords or [],
                "is_primary":       s.is_primary,
            }
            for s in skills
        ]

    # ── Work Experience ────────────────────────────────────────────────────────

    def _get_experience(self, db: Session) -> List[Dict]:
        exps = db.query(WorkExperience).order_by(
            WorkExperience.is_current.desc(),
            WorkExperience.start_date.desc()
        ).all()

        result = []
        for exp in exps:
            # Sort bullets by impact score descending
            bullets = (
                db.query(ExperienceBullet)
                .filter(ExperienceBullet.experience_id == exp.id)
                .order_by(ExperienceBullet.impact_score.desc())
                .all()
            )
            result.append({
                "company":    exp.company,
                "role":       exp.role,
                "location":   exp.location,
                "start_date": exp.start_date,
                "end_date":   exp.end_date or "Present",
                "is_current": exp.is_current,
                "tech_stack": exp.tech_stack or [],
                "bullets":    [
                    {
                        "text":         b.bullet,
                        "keywords":     b.keywords or [],
                        "impact_score": b.impact_score,
                    }
                    for b in bullets
                ],
            })
        return result

    # ── Projects ───────────────────────────────────────────────────────────────

    def _get_projects(self, db: Session) -> List[Dict]:
        projects = db.query(Project).order_by(
            Project.is_featured.desc()
        ).all()

        result = []
        for proj in projects:
            bullets = (
                db.query(ProjectBullet)
                .filter(ProjectBullet.project_id == proj.id)
                .all()
            )
            result.append({
                "title":             proj.title,
                "description":       proj.description,
                "short_description": proj.short_description,
                "tech_stack":        proj.tech_stack or [],
                "impact":            proj.impact,
                "github_url":        proj.github_url,
                "live_url":          proj.live_url,
                "start_date":        proj.start_date,
                "end_date":          proj.end_date,
                "is_featured":       proj.is_featured,
                "bullets":           [
                    {
                        "text":     b.bullet,
                        "keywords": b.keywords or [],
                    }
                    for b in bullets
                ],
            })
        return result

    # ── Education ──────────────────────────────────────────────────────────────

    def _get_education(self, db: Session) -> List[Dict]:
        edus = db.query(Education).all()
        return [
            {
                "institution":         e.institution,
                "degree":              e.degree,
                "field":               e.field,
                "start_year":          e.start_year,
                "end_year":            e.end_year,
                "gpa":                 e.gpa,
                "honors":              e.honors,
                "relevant_coursework": e.relevant_coursework or [],
            }
            for e in edus
        ]


metabase_service = MetabaseService()
