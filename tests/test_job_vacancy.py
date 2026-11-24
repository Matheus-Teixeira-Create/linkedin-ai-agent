from decimal import Decimal

import pytest

from app.models.job_vacancy import (
    JobRequirement,
    JobVacancy,
    RequirementCategory,
    RequirementImportance,
    VacancyValidationError,
)


def test_vacancy_accepts_typed_requirements_and_normalizes_duplicates() -> None:
    vacancy = JobVacancy(
        "Desenvolvedor Python",
        professional_area=" Tecnologia ",
        requirements=(
            JobRequirement("competencia", "Python"),
            JobRequirement("competencia", "Python"),
        ),
    )

    assert vacancy.professional_area == "Tecnologia"
    assert vacancy.requirements == (
        JobRequirement(RequirementCategory.SKILL, "Python", RequirementImportance.REQUIRED),
    )


def test_vacancy_from_dict_validates_nested_requirements_and_serializes() -> None:
    vacancy = JobVacancy.from_dict(
        {
            "title": "Analista",
            "requirements": [
                {
                    "category": "idioma",
                    "description": "Inglês",
                    "importance": "desejavel",
                    "minimum_proficiency": "avançado",
                },
                {
                    "category": "experiencia",
                    "description": "Python",
                    "minimum_years": 2,
                },
            ],
        }
    )

    result = vacancy.to_dict()
    assert result["requirements"][0]["minimum_proficiency"] == "avançado"
    assert result["requirements"][1]["minimum_years"] == "2"
    assert result["requirements"][0]["importance"] == "desejavel"


@pytest.mark.parametrize(
    "values",
    [
        {},
        {"title": " "},
        {"title": "Dev", "unknown": True},
        {"title": "Dev", "requirements": "Python"},
        {"title": "Dev", "requirements": [{"category": "invalid", "description": "x"}]},
        {"title": "Dev", "requirements": [{"category": "competencia", "description": " "}]},
        {
            "title": "Dev",
            "requirements": [
                {"category": "competencia", "description": "Python", "minimum_years": 2}
            ],
        },
        {
            "title": "Dev",
            "requirements": [
                {"category": "idioma", "description": "Inglês", "minimum_proficiency": "excelente"}
            ],
        },
        {
            "title": "Dev",
            "requirements": [
                {"category": "experiencia", "description": "Python", "minimum_years": -1}
            ],
        },
    ],
)
def test_vacancy_rejects_invalid_data(values: dict[str, object]) -> None:
    with pytest.raises(VacancyValidationError):
        JobVacancy.from_dict(values)


def test_experience_years_are_decimal_and_finite() -> None:
    requirement = JobRequirement("experiencia", "Python", minimum_years="2.5")
    assert requirement.minimum_years == Decimal("2.5")


def test_vacancy_without_requirements_is_valid() -> None:
    assert JobVacancy("Vaga sem requisitos estruturados").requirements == ()
