from datetime import date

import pytest

from app.models.professional_profile import (
    CourseCertification,
    Education,
    Experience,
    Language,
    ProfessionalLink,
    ProfessionalProfile,
    ProfileValidationError,
    Proficiency,
    Project,
)
from app.services.professional_profile_service import ProfessionalProfileService


def test_create_profile_allows_no_experience() -> None:
    profile = ProfessionalProfile(name="Ana", education=(Education("Unicamp"),))
    service = ProfessionalProfileService()

    assert service.create(profile).experience == ()
    assert service.get_profile.name == "Ana"


def test_profile_normalizes_skills_and_duplicate_records() -> None:
    profile = ProfessionalProfile(
        technical_skills=(" Python ", "python", "SQL"),
        languages=(Language("Inglês", "avançado"), Language("inglês", "básico")),
    )

    assert profile.technical_skills == ("Python", "SQL")
    assert profile.languages == (Language("Inglês", Proficiency.ADVANCED),)


def test_profile_converts_dates_and_enums_to_simple_values() -> None:
    profile = ProfessionalProfile(
        experience=(Experience("Empresa", "Analista", "2020-01-01", is_current=True),),
        languages=(Language("Português", Proficiency.NATIVE),),
    )

    result = profile.to_dict()
    assert result["experience"][0]["start_date"] == "2020-01-01"
    assert result["languages"][0]["proficiency"] == "nativo"


@pytest.mark.parametrize(
    "builder",
    [
        lambda: ProfessionalProfile(name=8),
        lambda: ProfessionalProfile(languages=(Language("Inglês", "excelente"),)),
        lambda: ProfessionalProfile(links=(ProfessionalLink("GitHub", "javascript:alert(1)"),)),
        lambda: ProfessionalProfile(projects=(Project("Projeto", start_date="2024-02-31"),)),
        lambda: ProfessionalProfile(education=(Education("Faculdade", "Bacharelado", start_date="2024-01-01", end_date="2020-01-01"),)),
        lambda: ProfessionalProfile(technical_skills="Python"),
    ],
)
def test_profile_rejects_invalid_values(builder) -> None:
    with pytest.raises(ProfileValidationError):
        builder()


def test_profile_accepts_valid_nested_entries_and_urls() -> None:
    profile = ProfessionalProfile.from_dict(
        {
            "education": [{"institution": "Unicamp", "start_date": date(2020, 1, 1)}],
            "experience": [{"organization": "Empresa", "role": "Dev", "is_current": True}],
            "projects": [{"name": "Projeto", "url": "https://github.com/exemplo"}],
            "courses_certifications": [{"name": "Curso", "credential_url": "https://exemplo.com/cert"}],
            "links": [{"label": "LinkedIn", "url": "https://linkedin.com/in/exemplo"}],
        }
    )

    assert profile.education[0].institution == "Unicamp"
    assert profile.experience[0].is_current is True


def test_service_updates_and_replaces_without_retaining_old_fields() -> None:
    service = ProfessionalProfileService(ProfessionalProfile(name="Ana", location="Campinas"))
    service.update(professional_summary="Bióloga")
    assert service.get_profile.name == "Ana"

    service.replace({"name": "Bruno"})
    assert service.get_profile.name == "Bruno"
    assert service.get_profile.location is None


def test_service_removes_a_list_item_or_single_field() -> None:
    service = ProfessionalProfileService(
        ProfessionalProfile(technical_skills=("Python",), education=(Education("Unicamp"), Education("USP")))
    )
    service.remove("education", 0)
    service.remove("technical_skills")

    assert service.get_profile.education == (Education("USP"),)
    assert service.get_profile.technical_skills == ()


def test_service_clears_profile() -> None:
    service = ProfessionalProfileService(ProfessionalProfile(name="Ana", projects=(Project("A"),)))

    assert service.clear() == ProfessionalProfile()


def test_service_rejects_invalid_index_and_field() -> None:
    service = ProfessionalProfileService(ProfessionalProfile(name="Ana"))
    with pytest.raises(ProfileValidationError):
        service.remove("education", 0)
    with pytest.raises(ProfileValidationError):
        service.update(naem="Ana")
