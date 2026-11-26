from datetime import date, datetime

import pytest

from app.models.job_vacancy import JobRequirement, JobVacancy
from app.models.professional_profile import (
    Education,
    Experience,
    Language,
    ProfessionalProfile,
    Proficiency,
)
from app.services.compatibility_service import (
    AssessmentStatus,
    CompatibilityService,
    CompatibilityValidationError,
)


def test_score_and_coverage_are_independent_and_unknowns_are_excluded_from_score() -> None:
    profile = ProfessionalProfile(technical_skills=("Python",))
    vacancy = JobVacancy(
        "Desenvolvedor",
        requirements=(
            JobRequirement("competencia", "python"),
            JobRequirement("formacao", "Biologia"),
        ),
    )

    result = CompatibilityService().evaluate(profile, vacancy)

    assert result.score == 100
    assert result.coverage == 50
    assert [item.status for item in result.assessments] == [
        AssessmentStatus.MET,
        AssessmentStatus.NOT_EVALUABLE,
    ]
    assert result.assessments[1] in result.not_evaluable


def test_required_requirements_have_double_weight_of_desirable_ones() -> None:
    profile = ProfessionalProfile(
        technical_skills=("Python",),
        languages=(Language("Inglês", Proficiency.BASIC),),
    )
    vacancy = JobVacancy(
        "Dev",
        requirements=(
            JobRequirement("competencia", "Python", "obrigatorio"),
            JobRequirement("idioma", "Inglês", "desejavel", minimum_proficiency="fluente"),
        ),
    )

    result = CompatibilityService().evaluate(profile, vacancy)

    assert result.score == pytest.approx(200 / 3, abs=0.01)
    assert result.coverage == 100
    assert len(result.met) == 1
    assert len(result.not_met) == 1


def test_skill_comparison_uses_case_and_accent_normalization_and_explains_match() -> None:
    profile = ProfessionalProfile(technical_skills=("  Análise de Dados ",))
    vacancy = JobVacancy(
        "Analista",
        requirements=(JobRequirement("competencia", "ANALISE DE DADOS"),),
    )

    assessment = CompatibilityService().evaluate(profile, vacancy).assessments[0]

    assert assessment.status is AssessmentStatus.MET
    assert assessment.evidence == ("Análise de Dados",)
    assert "declarada" in assessment.explanation


def test_missing_profile_data_is_not_evaluated_or_assumed() -> None:
    profile = ProfessionalProfile()
    vacancy = JobVacancy(
        "Vaga",
        requirements=(
            JobRequirement("competencia", "Python"),
            JobRequirement("experiencia", "Desenvolvedor"),
            JobRequirement("formacao", "Biologia"),
            JobRequirement("idioma", "Inglês", minimum_proficiency="avançado"),
        ),
    )

    result = CompatibilityService().evaluate(profile, vacancy)

    assert result.score == 0
    assert result.coverage == 0
    assert len(result.not_evaluable) == 4
    assert result.met == ()
    assert result.not_met == ()


def test_datetime_is_rejected_for_as_of_instead_of_causing_date_comparison_error() -> None:
    profile = ProfessionalProfile(
        experience=(Experience("Exemplo Ltda.", "Desenvolvedor", date(2020, 1, 1)),)
    )
    vacancy = JobVacancy(
        "Desenvolvedor",
        requirements=(JobRequirement("experiencia", "Desenvolvedor", minimum_years=1),),
    )
    with pytest.raises(CompatibilityValidationError, match="as_of deve ser uma data"):
        CompatibilityService().evaluate(profile, vacancy, as_of=datetime(2025, 1, 1, 12))


def test_date_is_accepted_for_as_of() -> None:
    profile = ProfessionalProfile(
        experience=(Experience("Exemplo Ltda.", "Desenvolvedor", date(2020, 1, 1), is_current=True),)
    )
    vacancy = JobVacancy(
        "Desenvolvedor",
        requirements=(JobRequirement("experiencia", "Desenvolvedor", minimum_years=1),),
    )
    result = CompatibilityService().evaluate(profile, vacancy, as_of=date(2025, 1, 1))
    assert result.score == 100


def test_absent_skill_is_not_evaluated_even_when_other_skills_are_listed() -> None:
    profile = ProfessionalProfile(technical_skills=("Java",))
    vacancy = JobVacancy("Dev", requirements=(JobRequirement("competencia", "Python"),))

    assessment = CompatibilityService().evaluate(profile, vacancy).assessments[0]

    assert assessment.status is AssessmentStatus.NOT_EVALUABLE
    assert "não informa" in assessment.explanation


def test_experience_is_matched_by_role_and_summed_without_overlapping_periods() -> None:
    profile = ProfessionalProfile(
        experience=(
            Experience("Empresa A", "Desenvolvedor Python", "2020-01-01", "2022-01-01"),
            Experience("Empresa B", "Desenvolvedor Python", "2021-01-01", "2023-01-01"),
        )
    )
    vacancy = JobVacancy(
        "Dev",
        requirements=(JobRequirement("experiencia", "Python", minimum_years=2.9),),
    )

    assessment = CompatibilityService().evaluate(profile, vacancy, as_of=date(2024, 1, 1)).assessments[0]

    assert assessment.status is AssessmentStatus.MET
    assert len(assessment.evidence) == 2


def test_experience_years_are_not_evaluated_when_dates_are_missing() -> None:
    profile = ProfessionalProfile(experience=(Experience("Empresa", "Desenvolvedor Python"),))
    vacancy = JobVacancy(
        "Dev",
        requirements=(JobRequirement("experiencia", "Python", minimum_years=1),),
    )

    assessment = CompatibilityService().evaluate(profile, vacancy).assessments[0]

    assert assessment.status is AssessmentStatus.NOT_EVALUABLE
    assert assessment.evidence == ("Desenvolvedor Python — Empresa",)


def test_experience_with_known_shorter_duration_does_not_meet_minimum() -> None:
    profile = ProfessionalProfile(
        experience=(Experience("Empresa", "Desenvolvedor Python", "2023-01-01", "2024-01-01"),)
    )
    vacancy = JobVacancy(
        "Dev",
        requirements=(JobRequirement("experiencia", "Python", minimum_years=2),),
    )

    assessment = CompatibilityService().evaluate(profile, vacancy, as_of=date(2025, 1, 1)).assessments[0]
    assert assessment.status is AssessmentStatus.NOT_MET


def test_education_matches_declared_course_and_area_only() -> None:
    profile = ProfessionalProfile(
        education=(Education("Unicamp", "Bacharelado", "Biologia"),)
    )
    vacancy = JobVacancy("Analista", requirements=(JobRequirement("formacao", "Biologia"),))

    assessment = CompatibilityService().evaluate(profile, vacancy).assessments[0]
    assert assessment.status is AssessmentStatus.MET
    assert assessment.evidence == ("Bacharelado — Biologia",)


def test_unrelated_education_is_not_assumed_to_fail_a_specific_requirement() -> None:
    profile = ProfessionalProfile(education=(Education("Unicamp", "Bacharelado", "Biologia"),))
    vacancy = JobVacancy("Analista", requirements=(JobRequirement("formacao", "Matemática"),))

    assessment = CompatibilityService().evaluate(profile, vacancy).assessments[0]
    assert assessment.status is AssessmentStatus.NOT_EVALUABLE


def test_institution_without_course_or_field_does_not_prove_education_requirement() -> None:
    profile = ProfessionalProfile(education=(Education("Unicamp"),))
    vacancy = JobVacancy("Analista", requirements=(JobRequirement("formacao", "Biologia"),))

    assessment = CompatibilityService().evaluate(profile, vacancy).assessments[0]
    assert assessment.status is AssessmentStatus.NOT_EVALUABLE


@pytest.mark.parametrize(
    ("candidate_level", "minimum_level", "expected"),
    [
        (Proficiency.BASIC, Proficiency.INTERMEDIATE, AssessmentStatus.NOT_MET),
        (Proficiency.ADVANCED, Proficiency.INTERMEDIATE, AssessmentStatus.MET),
    ],
)
def test_language_proficiency_meets_or_falls_below_requirement(
    candidate_level: Proficiency,
    minimum_level: Proficiency,
    expected: AssessmentStatus,
) -> None:
    profile = ProfessionalProfile(languages=(Language("Inglês", candidate_level),))
    vacancy = JobVacancy(
        "Analista",
        requirements=(JobRequirement("idioma", "Ingles", minimum_proficiency=minimum_level),),
    )

    assessment = CompatibilityService().evaluate(profile, vacancy).assessments[0]
    assert assessment.status is expected


def test_unlisted_language_is_not_assumed_missing_when_another_language_is_listed() -> None:
    profile = ProfessionalProfile(languages=(Language("Espanhol", Proficiency.ADVANCED),))
    vacancy = JobVacancy(
        "Analista",
        requirements=(JobRequirement("idioma", "Inglês", minimum_proficiency="fluente"),),
    )
    assessment = CompatibilityService().evaluate(profile, vacancy).assessments[0]
    assert assessment.status is AssessmentStatus.NOT_EVALUABLE


def test_no_requirements_returns_zero_metrics_without_division_error() -> None:
    result = CompatibilityService().evaluate(ProfessionalProfile(), JobVacancy("Vaga"))
    assert result.score == 0
    assert result.coverage == 0
    assert result.assessments == ()


def test_result_metrics_stay_between_zero_and_one_hundred() -> None:
    profile = ProfessionalProfile(technical_skills=("Python",))
    vacancy = JobVacancy(
        "Vaga",
        requirements=tuple(JobRequirement("competencia", f"skill-{index}") for index in range(100)),
    )

    result = CompatibilityService().evaluate(profile, vacancy)
    assert 0 <= result.score <= 100
    assert 0 <= result.coverage <= 100


def test_service_rejects_wrong_input_types() -> None:
    service = CompatibilityService()
    with pytest.raises(CompatibilityValidationError):
        service.evaluate({}, JobVacancy("Vaga"))  # type: ignore[arg-type]
    with pytest.raises(CompatibilityValidationError):
        service.evaluate(ProfessionalProfile(), {})  # type: ignore[arg-type]


def test_evaluation_does_not_mutate_profile_or_vacancy() -> None:
    profile = ProfessionalProfile(technical_skills=("Python",))
    vacancy = JobVacancy("Dev", requirements=(JobRequirement("competencia", "Python"),))
    profile_before, vacancy_before = profile.to_dict(), vacancy.to_dict()

    CompatibilityService().evaluate(profile, vacancy)

    assert profile.to_dict() == profile_before
    assert vacancy.to_dict() == vacancy_before
