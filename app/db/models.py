"""Mapeamentos ORM separados dos modelos de domínio."""

from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class UserORM(Base):
    """Conta de usuário; campos de autenticação aceitam nulos na migração legada."""

    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)
    email: Mapped[str | None] = mapped_column(String(320))
    email_normalized: Mapped[str | None] = mapped_column(String(320))
    password_hash: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())
    search_criteria: Mapped["SearchCriteriaORM | None"] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True, uselist=False
    )
    professional_profile: Mapped["ProfessionalProfileORM | None"] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True, uselist=False
    )
    auth_sessions: Mapped[list["AuthSessionORM"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )


Index("uq_users_email_normalized", UserORM.email_normalized, unique=True)


class AuthSessionORM(Base):
    """Sessão revogável associada a um usuário autenticado."""

    __tablename__ = "auth_sessions"
    __table_args__ = (Index("ix_auth_sessions_user_id", "user_id"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    csrf_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    user: Mapped[UserORM] = relationship(back_populates="auth_sessions")
    refresh_tokens: Mapped[list["RefreshTokenORM"]] = relationship(
        back_populates="auth_session", cascade="all, delete-orphan", passive_deletes=True
    )


class RefreshTokenORM(Base):
    """Histórico de hashes de refresh token para rotação e detecção de replay."""

    __tablename__ = "refresh_tokens"
    __table_args__ = (
        Index("uq_refresh_tokens_token_hash", "token_hash", unique=True),
        Index("ix_refresh_tokens_session_id", "session_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("auth_sessions.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaced_by_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("refresh_tokens.id", ondelete="SET NULL")
    )

    auth_session: Mapped[AuthSessionORM] = relationship(back_populates="refresh_tokens")


class SearchCriteriaORM(Base):
    """Critérios de busca persistidos, um conjunto por usuário."""

    __tablename__ = "search_criteria"
    __table_args__ = (UniqueConstraint("user_id", name="uq_search_criteria_user"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    professional_area: Mapped[str | None] = mapped_column(String(200))
    desired_title: Mapped[str | None] = mapped_column(String(200))
    work_mode: Mapped[str | None] = mapped_column(String(30))
    location: Mapped[str | None] = mapped_column(String(200))
    seniority: Mapped[str | None] = mapped_column(String(100))
    salary_min: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    salary_max: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))

    user: Mapped[UserORM] = relationship(back_populates="search_criteria")
    skills: Mapped[list["SearchCriteriaSkillORM"]] = relationship(
        back_populates="criteria",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="SearchCriteriaSkillORM.position",
    )


class SearchCriteriaSkillORM(Base):
    """Competência pertencente aos critérios de busca."""

    __tablename__ = "search_criteria_skills"
    __table_args__ = (UniqueConstraint("criteria_id", "name", name="uq_search_skill_name"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    criteria_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("search_criteria.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    position: Mapped[int] = mapped_column(nullable=False, default=0)

    criteria: Mapped[SearchCriteriaORM] = relationship(back_populates="skills")


class ProfessionalProfileORM(Base):
    """Dados escalares do perfil profissional, um por usuário."""

    __tablename__ = "professional_profiles"
    __table_args__ = (UniqueConstraint("user_id", name="uq_professional_profile_user"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str | None] = mapped_column(String(200))
    professional_summary: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(String(200))

    user: Mapped[UserORM] = relationship(back_populates="professional_profile")
    skills: Mapped[list["ProfessionalSkillORM"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan", passive_deletes=True,
        order_by="ProfessionalSkillORM.position",
    )
    education: Mapped[list["EducationORM"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan", passive_deletes=True,
        order_by="EducationORM.position",
    )
    experiences: Mapped[list["ExperienceORM"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan", passive_deletes=True,
        order_by="ExperienceORM.position",
    )
    languages: Mapped[list["LanguageORM"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan", passive_deletes=True,
        order_by="LanguageORM.position",
    )
    projects: Mapped[list["ProjectORM"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan", passive_deletes=True,
        order_by="ProjectORM.position",
    )
    certifications: Mapped[list["CourseCertificationORM"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan", passive_deletes=True,
        order_by="CourseCertificationORM.position",
    )
    links: Mapped[list["ProfessionalLinkORM"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan", passive_deletes=True,
        order_by="ProfessionalLinkORM.position",
    )


class ProfessionalSkillORM(Base):
    """Competência técnica, comportamental ou tecnologia do perfil."""

    __tablename__ = "professional_skills"
    __table_args__ = (UniqueConstraint("profile_id", "category", "name", name="uq_profile_skill"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    profile_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("professional_profiles.id", ondelete="CASCADE"), nullable=False
    )
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    position: Mapped[int] = mapped_column(nullable=False, default=0)

    profile: Mapped[ProfessionalProfileORM] = relationship(back_populates="skills")


class EducationORM(Base):
    __tablename__ = "educations"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    profile_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("professional_profiles.id", ondelete="CASCADE"), nullable=False
    )
    institution: Mapped[str] = mapped_column(String(200), nullable=False)
    degree: Mapped[str | None] = mapped_column(String(200))
    field_of_study: Mapped[str | None] = mapped_column(String(200))
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    description: Mapped[str | None] = mapped_column(Text)
    position: Mapped[int] = mapped_column(nullable=False, default=0)

    profile: Mapped[ProfessionalProfileORM] = relationship(back_populates="education")


class ExperienceORM(Base):
    __tablename__ = "experiences"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    profile_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("professional_profiles.id", ondelete="CASCADE"), nullable=False
    )
    organization: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(200), nullable=False)
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    description: Mapped[str | None] = mapped_column(Text)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    position: Mapped[int] = mapped_column(nullable=False, default=0)

    profile: Mapped[ProfessionalProfileORM] = relationship(back_populates="experiences")


class LanguageORM(Base):
    __tablename__ = "profile_languages"
    __table_args__ = (UniqueConstraint("profile_id", "name", name="uq_profile_language"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    profile_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("professional_profiles.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    proficiency: Mapped[str] = mapped_column(String(30), nullable=False)
    position: Mapped[int] = mapped_column(nullable=False, default=0)

    profile: Mapped[ProfessionalProfileORM] = relationship(back_populates="languages")


class ProjectORM(Base):
    __tablename__ = "profile_projects"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    profile_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("professional_profiles.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(String(1000))
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    position: Mapped[int] = mapped_column(nullable=False, default=0)

    profile: Mapped[ProfessionalProfileORM] = relationship(back_populates="projects")


class CourseCertificationORM(Base):
    __tablename__ = "course_certifications"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    profile_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("professional_profiles.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    issuer: Mapped[str | None] = mapped_column(String(200))
    issue_date: Mapped[date | None] = mapped_column(Date)
    expiration_date: Mapped[date | None] = mapped_column(Date)
    credential_url: Mapped[str | None] = mapped_column(String(1000))
    position: Mapped[int] = mapped_column(nullable=False, default=0)

    profile: Mapped[ProfessionalProfileORM] = relationship(back_populates="certifications")


class ProfessionalLinkORM(Base):
    __tablename__ = "professional_links"
    __table_args__ = (UniqueConstraint("profile_id", "url", name="uq_profile_link_url"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    profile_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("professional_profiles.id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    position: Mapped[int] = mapped_column(nullable=False, default=0)

    profile: Mapped[ProfessionalProfileORM] = relationship(back_populates="links")


class JobVacancyORM(Base):
    """Catálogo compartilhado de vagas, sem owner user_id."""

    __tablename__ = "job_vacancies"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    professional_area: Mapped[str | None] = mapped_column(String(200))
    requirements: Mapped[list["JobRequirementORM"]] = relationship(
        back_populates="vacancy", cascade="all, delete-orphan", passive_deletes=True,
        order_by="JobRequirementORM.position",
    )


class JobRequirementORM(Base):
    __tablename__ = "job_requirements"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    vacancy_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("job_vacancies.id", ondelete="CASCADE"), nullable=False
    )
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    description: Mapped[str] = mapped_column(String(300), nullable=False)
    importance: Mapped[str] = mapped_column(String(30), nullable=False)
    minimum_proficiency: Mapped[str | None] = mapped_column(String(30))
    minimum_years: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    position: Mapped[int] = mapped_column(nullable=False, default=0)

    vacancy: Mapped[JobVacancyORM] = relationship(back_populates="requirements")
