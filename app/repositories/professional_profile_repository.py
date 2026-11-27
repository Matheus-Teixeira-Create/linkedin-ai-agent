"""Persistência do perfil profissional e de seus registros por usuário."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from app.db.models import (
    CourseCertificationORM,
    EducationORM,
    ExperienceORM,
    LanguageORM,
    ProfessionalLinkORM,
    ProfessionalProfileORM,
    ProfessionalSkillORM,
    ProjectORM,
)
from app.models.professional_profile import (
    CourseCertification,
    Education,
    Experience,
    Language,
    ProfessionalLink,
    ProfessionalProfile,
    Project,
)


class ProfessionalProfileRepository:
    """Persiste um perfil por usuário e reaproveita a validação do domínio."""

    @staticmethod
    def _validate_user_id(user_id: UUID | None) -> None:
        if user_id is None:
            raise ValueError("user_id é obrigatório para persistir o perfil.")

    def get_by_user_id(self, session: Session, user_id: UUID) -> ProfessionalProfile | None:
        self._validate_user_id(user_id)
        row = session.scalar(
            select(ProfessionalProfileORM).where(ProfessionalProfileORM.user_id == user_id)
        )
        versions = session.info.setdefault("personal_data_versions", {})
        versions[(ProfessionalProfileORM, user_id)] = row.version if row else None
        return self._to_domain(row) if row else None

    def save(
        self, session: Session, user_id: UUID, profile: ProfessionalProfile
    ) -> ProfessionalProfile:
        self._validate_user_id(user_id)
        if not isinstance(profile, ProfessionalProfile):
            raise TypeError("profile deve ser ProfessionalProfile.")
        row = session.scalar(
            select(ProfessionalProfileORM).where(ProfessionalProfileORM.user_id == user_id)
        )
        versions = session.info.get("personal_data_versions", {})
        version_key = (ProfessionalProfileORM, user_id)
        if version_key in versions:
            expected_version = versions.pop(version_key)
            if (row is None) != (expected_version is None) or (
                row is not None and row.version != expected_version
            ):
                raise StaleDataError("O perfil foi alterado durante a requisição.")
        if row is None:
            row = ProfessionalProfileORM(user_id=user_id)
            session.add(row)
        else:
            # Força uma escrita versionada mesmo quando só os registros filhos mudaram.
            row.version += 1

        row.name = profile.name
        row.professional_summary = profile.professional_summary
        row.location = profile.location
        row.skills.clear()
        row.education.clear()
        row.experiences.clear()
        row.languages.clear()
        row.projects.clear()
        row.certifications.clear()
        row.links.clear()
        # Persiste a remoção dos órfãos antes de inserir substitutos sujeitos
        # às mesmas constraints únicas, sem confirmar a transação do chamador.
        session.flush()
        row.skills = [
            *(ProfessionalSkillORM(category="technical", name=value, position=index)
              for index, value in enumerate(profile.technical_skills)),
            *(ProfessionalSkillORM(category="behavioral", name=value, position=index)
              for index, value in enumerate(profile.behavioral_skills)),
            *(ProfessionalSkillORM(category="technology", name=value, position=index)
              for index, value in enumerate(profile.technologies)),
        ]
        row.education = [
            EducationORM(
                institution=item.institution, degree=item.degree, field_of_study=item.field_of_study,
                start_date=item.start_date, end_date=item.end_date, description=item.description,
                position=index,
            )
            for index, item in enumerate(profile.education)
        ]
        row.experiences = [
            ExperienceORM(
                organization=item.organization, role=item.role, start_date=item.start_date,
                end_date=item.end_date, description=item.description, is_current=item.is_current,
                position=index,
            )
            for index, item in enumerate(profile.experience)
        ]
        row.languages = [
            LanguageORM(name=item.name, proficiency=item.proficiency.value, position=index)
            for index, item in enumerate(profile.languages)
        ]
        row.projects = [
            ProjectORM(
                name=item.name, description=item.description, url=item.url,
                start_date=item.start_date, end_date=item.end_date, position=index,
            )
            for index, item in enumerate(profile.projects)
        ]
        row.certifications = [
            CourseCertificationORM(
                name=item.name, issuer=item.issuer, issue_date=item.issue_date,
                expiration_date=item.expiration_date, credential_url=item.credential_url,
                position=index,
            )
            for index, item in enumerate(profile.courses_certifications)
        ]
        row.links = [
            ProfessionalLinkORM(label=item.label, url=item.url, position=index)
            for index, item in enumerate(profile.links)
        ]
        session.flush()
        return self._to_domain(row)

    def delete_by_user_id(self, session: Session, user_id: UUID) -> bool:
        self._validate_user_id(user_id)
        row = session.scalar(
            select(ProfessionalProfileORM).where(ProfessionalProfileORM.user_id == user_id)
        )
        if row is None:
            return False
        session.delete(row)
        session.flush()
        return True

    @staticmethod
    def _to_domain(row: ProfessionalProfileORM) -> ProfessionalProfile:
        groups: dict[str, list[str]] = {"technical": [], "behavioral": [], "technology": []}
        for item in row.skills:
            groups[item.category].append(item.name)
        return ProfessionalProfile(
            name=row.name,
            professional_summary=row.professional_summary,
            location=row.location,
            technical_skills=tuple(groups["technical"]),
            behavioral_skills=tuple(groups["behavioral"]),
            technologies=tuple(groups["technology"]),
            education=tuple(
                Education(
                    institution=item.institution, degree=item.degree, field_of_study=item.field_of_study,
                    start_date=item.start_date, end_date=item.end_date, description=item.description,
                )
                for item in row.education
            ),
            experience=tuple(
                Experience(
                    organization=item.organization, role=item.role, start_date=item.start_date,
                    end_date=item.end_date, description=item.description, is_current=item.is_current,
                )
                for item in row.experiences
            ),
            languages=tuple(
                Language(name=item.name, proficiency=item.proficiency) for item in row.languages
            ),
            projects=tuple(
                Project(
                    name=item.name, description=item.description, url=item.url,
                    start_date=item.start_date, end_date=item.end_date,
                )
                for item in row.projects
            ),
            courses_certifications=tuple(
                CourseCertification(
                    name=item.name, issuer=item.issuer, issue_date=item.issue_date,
                    expiration_date=item.expiration_date, credential_url=item.credential_url,
                )
                for item in row.certifications
            ),
            links=tuple(ProfessionalLink(label=item.label, url=item.url) for item in row.links),
        )
