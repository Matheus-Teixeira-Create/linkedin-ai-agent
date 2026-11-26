"""Compara requisitos declarados de uma vaga com um perfil profissional."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
import unicodedata

from app.models.job_vacancy import (
    JobRequirement,
    JobVacancy,
    RequirementCategory,
    RequirementImportance,
)
from app.models.professional_profile import (
    ProfessionalProfile,
    Proficiency,
)


class CompatibilityValidationError(ValueError):
    """Indica que o serviço recebeu tipos incompatíveis."""


class AssessmentStatus(str, Enum):
    """Resultado individual da avaliação de um requisito."""

    MET = "atendido"
    NOT_MET = "nao_atendido"
    NOT_EVALUABLE = "nao_avaliavel"


@dataclass(frozen=True, slots=True)
class RequirementAssessment:
    """Explicação auditável para um requisito da vaga."""

    requirement: JobRequirement
    status: AssessmentStatus
    explanation: str
    evidence: tuple[str, ...] = ()

    @property
    def is_evaluable(self) -> bool:
        return self.status is not AssessmentStatus.NOT_EVALUABLE


@dataclass(frozen=True, slots=True)
class CompatibilityResult:
    """Pontuação, cobertura e explicações da comparação."""

    score: float
    coverage: float
    assessments: tuple[RequirementAssessment, ...]

    @property
    def met(self) -> tuple[RequirementAssessment, ...]:
        return tuple(item for item in self.assessments if item.status is AssessmentStatus.MET)

    @property
    def not_met(self) -> tuple[RequirementAssessment, ...]:
        return tuple(item for item in self.assessments if item.status is AssessmentStatus.NOT_MET)

    @property
    def not_evaluable(self) -> tuple[RequirementAssessment, ...]:
        return tuple(item for item in self.assessments if item.status is AssessmentStatus.NOT_EVALUABLE)


_PROFICIENCY_ORDER = {
    Proficiency.BASIC: 1,
    Proficiency.INTERMEDIATE: 2,
    Proficiency.ADVANCED: 3,
    Proficiency.FLUENT: 4,
    Proficiency.NATIVE: 5,
}
_REQUIRED_WEIGHT = Decimal("2")
_DESIRABLE_WEIGHT = Decimal("1")


class CompatibilityService:
    """Avalia os requisitos sem modificar perfil ou vaga.

    Requisitos obrigatórios têm peso 2 e desejáveis, peso 1. A pontuação é a
    soma dos pesos atendidos dividida pelos pesos avaliáveis. A cobertura é a
    quantidade de requisitos avaliáveis dividida pelo total de requisitos,
    sem ponderação. Quando nenhum requisito pode ser avaliado, ambas as
    métricas são zero e cada requisito permanece explicitamente não avaliável.
    """

    def evaluate(
        self,
        profile: ProfessionalProfile,
        vacancy: JobVacancy,
        *,
        as_of: date | None = None,
    ) -> CompatibilityResult:
        if not isinstance(profile, ProfessionalProfile):
            raise CompatibilityValidationError("profile deve ser ProfessionalProfile.")
        if not isinstance(vacancy, JobVacancy):
            raise CompatibilityValidationError("vacancy deve ser JobVacancy.")
        reference_date = as_of or date.today()
        if isinstance(reference_date, datetime) or not isinstance(reference_date, date):
            raise CompatibilityValidationError("as_of deve ser uma data.")

        assessments = tuple(self._assess(profile, requirement, reference_date) for requirement in vacancy.requirements)
        evaluable = [item for item in assessments if item.is_evaluable]
        total_weight = sum((self._weight(item.requirement) for item in evaluable), Decimal(0))
        achieved_weight = sum(
            (self._weight(item.requirement) for item in evaluable if item.status is AssessmentStatus.MET),
            Decimal(0),
        )
        score = float(achieved_weight / total_weight * 100) if total_weight else 0.0
        coverage = (len(evaluable) / len(assessments) * 100) if assessments else 0.0
        return CompatibilityResult(round(score, 2), round(coverage, 2), assessments)

    @staticmethod
    def _weight(requirement: JobRequirement) -> Decimal:
        return (
            _REQUIRED_WEIGHT
            if requirement.importance is RequirementImportance.REQUIRED
            else _DESIRABLE_WEIGHT
        )

    def _assess(
        self,
        profile: ProfessionalProfile,
        requirement: JobRequirement,
        as_of: date,
    ) -> RequirementAssessment:
        if requirement.category is RequirementCategory.SKILL:
            return self._assess_skill(profile, requirement)
        if requirement.category is RequirementCategory.EXPERIENCE:
            return self._assess_experience(profile, requirement, as_of)
        if requirement.category is RequirementCategory.EDUCATION:
            return self._assess_education(profile, requirement)
        return self._assess_language(profile, requirement)

    def _assess_skill(
        self, profile: ProfessionalProfile, requirement: JobRequirement
    ) -> RequirementAssessment:
        skills = (*profile.technical_skills, *profile.behavioral_skills, *profile.technologies)
        if not skills:
            return self._unknown(requirement, "O perfil não informa competências ou tecnologias.")
        match = next((skill for skill in skills if _normalize(skill) == _normalize(requirement.description)), None)
        if match:
            return self._met(requirement, "Competência declarada no perfil.", (match,))
        return self._unknown(requirement, "O perfil não informa se possui esta competência específica.")

    def _assess_experience(
        self, profile: ProfessionalProfile, requirement: JobRequirement, as_of: date
    ) -> RequirementAssessment:
        if not profile.experience:
            return self._unknown(requirement, "O perfil não informa experiências profissionais.")
        needle = _normalize(requirement.description)
        matches = tuple(
            item
            for item in profile.experience
            if needle in _normalize(f"{item.role} {item.description or ''}")
        )
        if not matches:
            return self._unknown(requirement, "O perfil não informa experiência correspondente a este requisito.")
        evidence = tuple(f"{item.role} — {item.organization}" for item in matches)
        if requirement.minimum_years is None:
            return self._met(requirement, "Experiência correspondente encontrada no perfil.", evidence)
        if any(item.start_date is None for item in matches):
            return self._unknown(requirement, "As datas das experiências correspondentes estão incompletas.", evidence)
        intervals: list[tuple[date, date]] = []
        for item in matches:
            end = as_of if item.is_current else item.end_date
            if end is None:
                return self._unknown(requirement, "O período de uma experiência correspondente não está informado.", evidence)
            assert item.start_date is not None
            intervals.append((item.start_date, min(end, as_of)))
        days = _merged_duration_days(intervals)
        years = Decimal(days) / Decimal("365.2425")
        if years >= requirement.minimum_years:
            return self._met(
                requirement,
                f"Experiência correspondente totaliza aproximadamente {years:.1f} ano(s), considerando períodos sem sobreposição.",
                evidence,
            )
        return self._not_met(
            requirement,
            f"A experiência correspondente documentada totaliza aproximadamente {years:.1f} ano(s); o requisito mínimo é {requirement.minimum_years}.",
            evidence,
        )

    def _assess_education(
        self, profile: ProfessionalProfile, requirement: JobRequirement
    ) -> RequirementAssessment:
        if not profile.education:
            return self._unknown(requirement, "O perfil não informa formação acadêmica.")
        entries = tuple(
            item
            for item in profile.education
            if item.degree or item.field_of_study
        )
        if not entries:
            return self._unknown(requirement, "O perfil não informa curso ou área de estudo da formação.")
        needle = _normalize(requirement.description)
        matches = tuple(
            item
            for item in entries
            if needle in _normalize(f"{item.degree or ''} {item.field_of_study or ''}")
        )
        if matches:
            evidence = tuple(
                " — ".join(value for value in (item.degree, item.field_of_study) if value)
                for item in matches
            )
            return self._met(requirement, "Formação correspondente declarada no perfil.", evidence)
        return self._unknown(requirement, "O perfil não informa formação correspondente a este requisito.")

    def _assess_language(
        self, profile: ProfessionalProfile, requirement: JobRequirement
    ) -> RequirementAssessment:
        if not profile.languages:
            return self._unknown(requirement, "O perfil não informa idiomas.")
        language = next(
            (item for item in profile.languages if _normalize(item.name) == _normalize(requirement.description)),
            None,
        )
        if language is None:
            return self._unknown(requirement, "O perfil não informa se possui este idioma específico.")
        evidence = (f"{language.name}: {language.proficiency.value}",)
        minimum = requirement.minimum_proficiency
        if minimum is None or _PROFICIENCY_ORDER[language.proficiency] >= _PROFICIENCY_ORDER[minimum]:
            return self._met(requirement, "Idioma e proficiência atendem ao requisito declarado.", evidence)
        return self._not_met(
            requirement,
            f"A proficiência informada é {language.proficiency.value}; o mínimo exigido é {minimum.value}.",
            evidence,
        )

    @staticmethod
    def _met(
        requirement: JobRequirement, explanation: str, evidence: tuple[str, ...] = ()
    ) -> RequirementAssessment:
        return RequirementAssessment(requirement, AssessmentStatus.MET, explanation, evidence)

    @staticmethod
    def _not_met(
        requirement: JobRequirement, explanation: str, evidence: tuple[str, ...] = ()
    ) -> RequirementAssessment:
        return RequirementAssessment(requirement, AssessmentStatus.NOT_MET, explanation, evidence)

    @staticmethod
    def _unknown(
        requirement: JobRequirement, explanation: str, evidence: tuple[str, ...] = ()
    ) -> RequirementAssessment:
        return RequirementAssessment(requirement, AssessmentStatus.NOT_EVALUABLE, explanation, evidence)


def _normalize(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value).casefold()
    return " ".join("".join(char for char in folded if not unicodedata.combining(char)).split())


def _merged_duration_days(intervals: list[tuple[date, date]]) -> int:
    """Soma períodos sem contar duas vezes experiências simultâneas."""
    merged: list[list[date]] = []
    for start, end in sorted(intervals):
        if end < start:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return sum((end - start).days for start, end in merged)
