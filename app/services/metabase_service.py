"""
app/services/metabase_service.py
──────────────────────────────────
Async version of the metabase service.
Fetches the candidate's full profile from PostgreSQL, scoped to a user_id.
"""
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Education, ExperienceBullet, PersonalInfo, Project,
    ProjectBullet, Skill, WorkExperience,
)

logger = logging.getLogger(__name__)


class MetabaseService:

    async def get_full_profile_async(
        self, db: AsyncSession, user_id: int
    ) -> Dict[str, Any]:
        """
        Build and return the complete candidate profile dict for a given user.
        Used by the ARQ worker task as context for AI tailoring.
        """
        profile = {
            "personal":   await self._get_personal(db, user_id),
            "skills":     await self._get_skills(db, user_id),
            "experience": await self._get_experience(db, user_id),
            "projects":   await self._get_projects(db, user_id),
            "education":  await self._get_education(db, user_id),
        }
        logger.info(
            "Profile loaded for user %d — %d skills, %d roles, %d projects",
            user_id,
            len(profile["skills"]),
            len(profile["experience"]),
            len(profile["projects"]),
        )
        return profile

    async def _get_personal(self, db: AsyncSession, user_id: int) -> Optional[Dict]:
        result = await db.execute(
            select(PersonalInfo).where(PersonalInfo.user_id == user_id)
        )
        info = result.scalar_one_or_none()
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

    async def _get_skills(self, db: AsyncSession, user_id: int) -> List[Dict]:
        result = await db.execute(
            select(Skill)
            .where(Skill.user_id == user_id)
            .order_by(Skill.is_primary.desc(), Skill.years_experience.desc())
        )
        return [
            {
                "name":             s.name,
                "category":         s.category,
                "proficiency":      s.proficiency,
                "years_experience": s.years_experience,
                "keywords":         s.keywords or [],
                "is_primary":       s.is_primary,
            }
            for s in result.scalars().all()
        ]

    async def _get_experience(self, db: AsyncSession, user_id: int) -> List[Dict]:
        result = await db.execute(
            select(WorkExperience)
            .where(WorkExperience.user_id == user_id)
            .order_by(WorkExperience.is_current.desc(), WorkExperience.start_date.desc())
        )
        exps = result.scalars().all()
        output = []
        for exp in exps:
            # Bullets are loaded eagerly (lazy="selectin" in model)
            bullets_sorted = sorted(
                exp.bullets, key=lambda b: b.impact_score, reverse=True
            )
            output.append({
                "company":    exp.company,
                "role":       exp.role,
                "location":   exp.location,
                "start_date": exp.start_date,
                "end_date":   exp.end_date or "Present",
                "is_current": exp.is_current,
                "tech_stack": exp.tech_stack or [],
                "bullets": [
                    {
                        "text":         b.bullet,
                        "keywords":     b.keywords or [],
                        "impact_score": b.impact_score,
                    }
                    for b in bullets_sorted
                ],
            })
        return output

    async def _get_projects(self, db: AsyncSession, user_id: int) -> List[Dict]:
        result = await db.execute(
            select(Project)
            .where(Project.user_id == user_id)
            .order_by(Project.is_featured.desc())
        )
        output = []
        for proj in result.scalars().all():
            output.append({
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
                "bullets": [
                    {"text": b.bullet, "keywords": b.keywords or []}
                    for b in proj.bullets
                ],
            })
        return output

    async def _get_education(self, db: AsyncSession, user_id: int) -> List[Dict]:
        result = await db.execute(
            select(Education).where(Education.user_id == user_id)
        )
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
            for e in result.scalars().all()
        ]


metabase_service = MetabaseService()
