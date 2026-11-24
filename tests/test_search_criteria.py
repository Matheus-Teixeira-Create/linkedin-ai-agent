from decimal import Decimal

import pytest

from app.models.search_criteria import CriteriaValidationError, SearchCriteria, WorkMode
from app.services.search_criteria_service import SearchCriteriaService


def test_model_normalizes_fields_and_skills() -> None:
    criteria = SearchCriteria(
        professional_area=" Tecnologia ",
        desired_title="Desenvolvedor Python",
        work_mode="hibrido",
        location=" Campinas, SP ",
        seniority="Júnior",
        skills=[" Python ", "SQL", "python"],
    )

    assert criteria.professional_area == "Tecnologia"
    assert criteria.work_mode is WorkMode.HYBRID
    assert criteria.location == "Campinas, SP"
    assert criteria.skills == ("Python", "SQL")


@pytest.mark.parametrize("mode", ["remoto", "presencial", "híbrido", "hibrido"])
def test_model_accepts_supported_work_modes(mode: str) -> None:
    assert SearchCriteria(work_mode=mode).work_mode is not None


def test_salary_values_are_decimal_and_serializable() -> None:
    criteria = SearchCriteria(salary_min="3000.50", salary_max=5000)

    assert criteria.salary_min == Decimal("3000.50")
    assert criteria.to_dict()["salary_min"] == "3000.50"
    assert criteria.to_dict()["salary_max"] == "5000"


@pytest.mark.parametrize(
    ("raw_salary", "expected"),
    [("R$ 3.000,00", Decimal("3000.00")), ("3.000", Decimal("3000")), ("3000,50", Decimal("3000.50"))],
)
def test_salary_values_accept_brazilian_currency_format(raw_salary: str, expected: Decimal) -> None:
    assert SearchCriteria(salary_min=raw_salary).salary_min == expected


@pytest.mark.parametrize(
    "values",
    [
        {"work_mode": "flexível"},
        {"salary_min": -1},
        {"salary_min": "inválido"},
        {"salary_min": 5000, "salary_max": 3000},
        {"professional_area": 7},
        {"skills": "Python"},
        {"unknown": "campo"},
    ],
)
def test_model_rejects_invalid_data(values: dict[str, object]) -> None:
    with pytest.raises(CriteriaValidationError):
        SearchCriteria.from_dict(values)


def test_service_updates_only_provided_fields_and_can_clear_one() -> None:
    service = SearchCriteriaService(SearchCriteria(professional_area="Tecnologia", location="Campinas"))

    updated = service.update(desired_title="Desenvolvedor Python", location=None)

    assert updated.professional_area == "Tecnologia"
    assert updated.desired_title == "Desenvolvedor Python"
    assert updated.location is None

    cleared_skills = service.update(skills=None)
    assert cleared_skills.skills == ()


def test_service_replaces_all_criteria() -> None:
    service = SearchCriteriaService(SearchCriteria(professional_area="Tecnologia"))

    replaced = service.replace({"professional_area": "Biologia", "work_mode": "presencial"})

    assert replaced.professional_area == "Biologia"
    assert replaced.work_mode is WorkMode.ONSITE
    assert replaced.desired_title is None


def test_service_clears_selected_or_all_criteria() -> None:
    service = SearchCriteriaService(
        SearchCriteria(professional_area="Tecnologia", location="Campinas", skills=("Python",))
    )
    service.clear("location")
    assert service.current.professional_area == "Tecnologia"
    assert service.current.location is None

    service.clear()
    assert service.current == SearchCriteria()


def test_service_rejects_unknown_fields() -> None:
    service = SearchCriteriaService()

    with pytest.raises(CriteriaValidationError, match="Campos desconhecidos"):
        service.update(locaton="Campinas")
