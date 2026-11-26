from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError

from app.db.models import (
    EducationORM,
    JobVacancyORM,
    LanguageORM,
    ProfessionalProfileORM,
    ProfessionalSkillORM,
    SearchCriteriaORM,
    UserORM,
)
from app.models.job_vacancy import JobRequirement, JobVacancy
from app.models.professional_profile import (
    CourseCertification,
    Education,
    Experience,
    Language,
    ProfessionalLink,
    ProfessionalProfile,
    Proficiency,
    Project,
)
from app.models.search_criteria import SearchCriteria, WorkMode
from app.repositories.job_vacancy_repository import JobVacancyRepository
from app.repositories.professional_profile_repository import ProfessionalProfileRepository
from app.repositories.search_criteria_repository import SearchCriteriaRepository


def _create_user(session) -> object:
    user = UserORM()
    session.add(user)
    session.flush()
    session.commit()
    return user.id


def test_search_criteria_round_trip_and_update_are_scoped_to_user(db_session) -> None:
    user_id = _create_user(db_session)
    other_user_id = _create_user(db_session)
    repository = SearchCriteriaRepository()
    criteria = SearchCriteria(
        professional_area="Tecnologia",
        desired_title="Desenvolvedor Python",
        work_mode=WorkMode.REMOTE,
        salary_min=Decimal("3000.50"),
        skills=("Python", "SQL"),
    )

    saved = repository.save(db_session, user_id, criteria)
    assert saved == criteria
    db_session.commit()

    db_session.expire_all()
    loaded = repository.get_by_user_id(db_session, user_id)
    assert loaded == criteria
    assert repository.get_by_user_id(db_session, other_user_id) is None
    db_session.rollback()

    changed = SearchCriteria(location="Campinas", skills=("PostgreSQL",))
    repository.save(db_session, user_id, changed)
    db_session.commit()
    db_session.expire_all()
    assert repository.get_by_user_id(db_session, user_id) == changed
    assert len(db_session.scalars(select(SearchCriteriaORM)).all()) == 1


def test_search_criteria_can_be_saved_again_with_identical_skills(db_session) -> None:
    user_id = _create_user(db_session)
    repository = SearchCriteriaRepository()
    criteria = SearchCriteria(skills=("Python", "SQL"))

    repository.save(db_session, user_id, criteria)
    db_session.commit()
    repository.save(db_session, user_id, criteria)
    db_session.commit()

    assert repository.get_by_user_id(db_session, user_id) == criteria
    rows = db_session.scalars(select(SearchCriteriaORM)).all()
    assert len(rows) == 1
    assert [skill.name for skill in rows[0].skills] == ["Python", "SQL"]


def test_search_criteria_update_keeps_adds_removes_and_orders_skills(db_session) -> None:
    user_id = _create_user(db_session)
    repository = SearchCriteriaRepository()
    repository.save(db_session, user_id, SearchCriteria(skills=("Python", "SQL", "Git")))
    db_session.commit()

    updated = SearchCriteria(skills=("SQL", "Docker", "Python"))
    repository.save(db_session, user_id, updated)
    db_session.commit()

    saved = repository.get_by_user_id(db_session, user_id)
    assert saved == updated
    assert saved.skills == ("SQL", "Docker", "Python")
    rows = db_session.scalars(select(SearchCriteriaORM)).all()
    assert len(rows) == 1
    assert len(rows[0].skills) == len({skill.name for skill in rows[0].skills}) == 3


def test_profile_round_trip_preserves_nested_records_and_domain_types(db_session) -> None:
    user_id = _create_user(db_session)
    repository = ProfessionalProfileRepository()
    profile = ProfessionalProfile(
        name="Ana",
        professional_summary="Analista de dados",
        location="Campinas",
        technical_skills=("Python", "SQL"),
        behavioral_skills=("Comunicação",),
        technologies=("PostgreSQL",),
        education=(Education("Unicamp", "Bacharelado", "Biologia", "2018-01-01", "2022-12-01"),),
        experience=(Experience("Empresa", "Analista", "2023-01-01", is_current=True),),
        languages=(Language("Inglês", Proficiency.ADVANCED),),
        projects=(Project("Portfólio", "Projeto acadêmico", "https://example.org", "2022-01-01"),),
        courses_certifications=(CourseCertification("SQL", "Instituto", "2024-01-01"),),
        links=(ProfessionalLink("GitHub", "https://github.com/example"),),
    )

    assert repository.save(db_session, user_id, profile) == profile
    db_session.commit()

    db_session.expire_all()
    assert repository.get_by_user_id(db_session, user_id) == profile
    assert len(db_session.scalars(select(EducationORM)).all()) == 1


def test_profile_can_be_saved_again_with_identical_skills_and_languages(db_session) -> None:
    user_id = _create_user(db_session)
    repository = ProfessionalProfileRepository()
    profile = ProfessionalProfile(
        technical_skills=("Python", "SQL"),
        languages=(
            Language("Inglês", Proficiency.ADVANCED),
            Language("Português", Proficiency.NATIVE),
        ),
    )

    repository.save(db_session, user_id, profile)
    db_session.commit()
    repository.save(db_session, user_id, profile)
    db_session.commit()

    assert repository.get_by_user_id(db_session, user_id) == profile
    skill_rows = db_session.scalars(select(ProfessionalSkillORM)).all()
    language_rows = db_session.scalars(select(LanguageORM)).all()
    assert [item.name for item in skill_rows] == ["Python", "SQL"]
    assert [item.name for item in language_rows] == ["Inglês", "Português"]


def test_profile_update_keeps_adds_removes_and_orders_skills_and_languages(db_session) -> None:
    user_id = _create_user(db_session)
    repository = ProfessionalProfileRepository()
    repository.save(
        db_session,
        user_id,
        ProfessionalProfile(
            technical_skills=("Python", "SQL", "Git"),
            languages=(
                Language("Inglês", Proficiency.ADVANCED),
                Language("Espanhol", Proficiency.INTERMEDIATE),
            ),
        ),
    )
    db_session.commit()

    updated = ProfessionalProfile(
        technical_skills=("SQL", "Python", "Docker"),
        languages=(
            Language("Espanhol", Proficiency.ADVANCED),
            Language("Inglês", Proficiency.FLUENT),
            Language("Francês", Proficiency.BASIC),
        ),
    )
    repository.save(db_session, user_id, updated)
    db_session.commit()

    saved = repository.get_by_user_id(db_session, user_id)
    assert saved == updated
    assert saved.technical_skills == ("SQL", "Python", "Docker")
    assert tuple(item.name for item in saved.languages) == ("Espanhol", "Inglês", "Francês")
    skill_rows = db_session.scalars(select(ProfessionalSkillORM)).all()
    language_rows = db_session.scalars(select(LanguageORM)).all()
    assert len(skill_rows) == len({(item.category, item.name) for item in skill_rows}) == 3
    assert len(language_rows) == len({item.name for item in language_rows}) == 3


def test_replacing_lists_remains_rollback_safe(db_session) -> None:
    user_id = _create_user(db_session)
    criteria_repository = SearchCriteriaRepository()
    profile_repository = ProfessionalProfileRepository()
    original_criteria = SearchCriteria(skills=("Python", "SQL"))
    original_profile = ProfessionalProfile(
        technical_skills=("Python", "SQL"),
        languages=(Language("Inglês", Proficiency.ADVANCED),),
    )
    criteria_repository.save(db_session, user_id, original_criteria)
    profile_repository.save(db_session, user_id, original_profile)
    db_session.commit()

    with pytest.raises(RuntimeError, match="forçar rollback"):
        with db_session.begin():
            criteria_repository.save(db_session, user_id, SearchCriteria(skills=("Go",)))
            profile_repository.save(
                db_session,
                user_id,
                ProfessionalProfile(technical_skills=("Go",), languages=()),
            )
            raise RuntimeError("forçar rollback")

    assert criteria_repository.get_by_user_id(db_session, user_id) == original_criteria
    assert profile_repository.get_by_user_id(db_session, user_id) == original_profile


def test_user_data_is_not_visible_to_another_user(db_session) -> None:
    owner_id = _create_user(db_session)
    other_id = _create_user(db_session)
    criteria_repo = SearchCriteriaRepository()
    profile_repo = ProfessionalProfileRepository()
    criteria_repo.save(db_session, owner_id, SearchCriteria(desired_title="Dev"))
    profile_repo.save(db_session, owner_id, ProfessionalProfile(name="Ana"))
    db_session.commit()

    assert criteria_repo.get_by_user_id(db_session, other_id) is None
    assert profile_repo.get_by_user_id(db_session, other_id) is None
    assert criteria_repo.get_by_user_id(db_session, owner_id).desired_title == "Dev"


def test_missing_user_id_is_never_replaced_by_a_default_user(db_session) -> None:
    with pytest.raises(ValueError, match="user_id é obrigatório"):
        SearchCriteriaRepository().save(db_session, None, SearchCriteria())
    with pytest.raises(ValueError, match="user_id é obrigatório"):
        ProfessionalProfileRepository().save(db_session, None, ProfessionalProfile())
    assert db_session.scalar(select(UserORM)) is None


def test_foreign_keys_reject_records_for_nonexistent_users(db_session) -> None:
    with pytest.raises(IntegrityError):
        with db_session.begin():
            SearchCriteriaRepository().save(db_session, uuid4(), SearchCriteria())
    assert db_session.scalar(select(SearchCriteriaORM)) is None


def test_user_deletion_cascades_owned_profile_and_criteria(db_session) -> None:
    user_id = _create_user(db_session)
    SearchCriteriaRepository().save(db_session, user_id, SearchCriteria(skills=("Python",)))
    ProfessionalProfileRepository().save(
        db_session, user_id, ProfessionalProfile(education=(Education("Unicamp"),))
    )
    db_session.commit()
    db_session.expire_all()
    db_session.rollback()
    db_session.delete(db_session.get(UserORM, user_id))
    db_session.commit()
    db_session.expire_all()
    assert db_session.scalars(select(SearchCriteriaORM)).all() == []
    assert db_session.scalars(select(ProfessionalProfileORM)).all() == []
    assert db_session.scalars(select(EducationORM)).all() == []


def test_job_vacancy_catalog_is_shared_and_round_trips_requirements(db_session) -> None:
    repository = JobVacancyRepository()
    vacancy = JobVacancy(
        "Desenvolvedor Python",
        "Tecnologia",
        (
            JobRequirement("competencia", "Python", "obrigatorio"),
            JobRequirement("experiencia", "Python", "desejavel", minimum_years=2),
        ),
    )
    vacancy_id = repository.create(db_session, vacancy)
    db_session.commit()
    db_session.expire_all()

    assert repository.get_by_id(db_session, vacancy_id) == vacancy
    assert repository.list_all(db_session) == ((vacancy_id, vacancy),)
    row = db_session.get(JobVacancyORM, vacancy_id)
    assert row is not None
    assert not hasattr(row, "user_id")


def test_transaction_rollback_removes_user_and_all_related_records(database_engine) -> None:
    from sqlalchemy.orm import Session

    user_id = uuid4()
    with pytest.raises(RuntimeError, match="forçar rollback"):
        with Session(database_engine) as session:
            with session.begin():
                session.add(UserORM(id=user_id))
                SearchCriteriaRepository().save(session, user_id, SearchCriteria(skills=("Python",)))
                raise RuntimeError("forçar rollback")
    with Session(database_engine) as verification:
        assert verification.get(UserORM, user_id) is None
        assert verification.scalars(select(SearchCriteriaORM)).all() == []
