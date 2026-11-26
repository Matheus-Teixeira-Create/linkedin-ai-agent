"""Schemas de entrada e saída dos dados pessoais do usuário autenticado."""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.professional_profile import ProfessionalProfile
from app.models.search_criteria import SearchCriteria


class _StrictPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SearchCriteriaPayload(_StrictPayload):
    professional_area: str | None = Field(default=None, max_length=200)
    desired_title: str | None = Field(default=None, max_length=200)
    work_mode: str | None = Field(default=None, max_length=30)
    location: str | None = Field(default=None, max_length=200)
    seniority: str | None = Field(default=None, max_length=100)
    salary_min: Decimal | None = Field(default=None, max_digits=14, decimal_places=2)
    salary_max: Decimal | None = Field(default=None, max_digits=14, decimal_places=2)
    skills: list[str] | None = None

    @model_validator(mode="after")
    def validate_domain_rules(self) -> "SearchCriteriaPayload":
        SearchCriteria.from_dict(self.model_dump(mode="python"))
        return self


class EducationPayload(_StrictPayload):
    institution: str = Field(max_length=200)
    degree: str | None = Field(default=None, max_length=200)
    field_of_study: str | None = Field(default=None, max_length=200)
    start_date: date | None = None
    end_date: date | None = None
    description: str | None = None


class ExperiencePayload(_StrictPayload):
    organization: str = Field(max_length=200)
    role: str = Field(max_length=200)
    start_date: date | None = None
    end_date: date | None = None
    description: str | None = None
    is_current: bool = False


class LanguagePayload(_StrictPayload):
    name: str = Field(max_length=100)
    proficiency: str = Field(max_length=30)


class ProjectPayload(_StrictPayload):
    name: str = Field(max_length=200)
    description: str | None = None
    url: str | None = Field(default=None, max_length=1000)
    start_date: date | None = None
    end_date: date | None = None


class CourseCertificationPayload(_StrictPayload):
    name: str = Field(max_length=200)
    issuer: str | None = Field(default=None, max_length=200)
    issue_date: date | None = None
    expiration_date: date | None = None
    credential_url: str | None = Field(default=None, max_length=1000)


class ProfessionalLinkPayload(_StrictPayload):
    label: str = Field(max_length=100)
    url: str = Field(max_length=1000)


class ProfessionalProfilePayload(_StrictPayload):
    name: str | None = Field(default=None, max_length=200)
    professional_summary: str | None = None
    location: str | None = Field(default=None, max_length=200)
    technical_skills: list[str] | None = None
    behavioral_skills: list[str] | None = None
    technologies: list[str] | None = None
    education: list[EducationPayload] | None = None
    experience: list[ExperiencePayload] | None = None
    languages: list[LanguagePayload] | None = None
    projects: list[ProjectPayload] | None = None
    courses_certifications: list[CourseCertificationPayload] | None = None
    links: list[ProfessionalLinkPayload] | None = None

    @model_validator(mode="after")
    def validate_domain_rules(self) -> "ProfessionalProfilePayload":
        ProfessionalProfile.from_dict(self.model_dump(mode="python"))
        return self
