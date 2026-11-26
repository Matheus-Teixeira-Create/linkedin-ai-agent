"""Rotas de dados pessoais limitadas ao usuário identificado pelo token."""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from app.api.dependencies import get_current_principal, get_db_session, require_csrf
from app.models.professional_profile import ProfessionalProfile
from app.models.search_criteria import SearchCriteria
from app.repositories.professional_profile_repository import ProfessionalProfileRepository
from app.repositories.search_criteria_repository import SearchCriteriaRepository
from app.schemas.personal_data import ProfessionalProfilePayload, SearchCriteriaPayload
from app.services.authentication_service import AuthenticatedPrincipal


router = APIRouter(prefix="/me", tags=["dados pessoais"])


def _criteria_response(criteria: SearchCriteria) -> SearchCriteriaPayload:
    return SearchCriteriaPayload.model_validate(criteria.to_dict())


def _profile_response(profile: ProfessionalProfile) -> ProfessionalProfilePayload:
    return ProfessionalProfilePayload.model_validate(profile.to_dict())


def _invalid_personal_data() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="Os dados informados são inválidos.",
    )


def _write_conflict() -> HTTPException:
    """Retorna conflito genérico para corrida ou atualização obsoleta."""
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Os dados foram alterados simultaneamente. Recarregue e tente novamente.",
    )


@router.get("/search-criteria", response_model=SearchCriteriaPayload)
def get_search_criteria(
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> SearchCriteriaPayload:
    criteria = SearchCriteriaRepository().get_by_user_id(session, principal.user.id)
    if criteria is None:
        raise HTTPException(status_code=404, detail="Critérios de busca não encontrados.")
    return _criteria_response(criteria)


@router.put("/search-criteria", response_model=SearchCriteriaPayload)
def replace_search_criteria(
    payload: SearchCriteriaPayload,
    principal: AuthenticatedPrincipal = Depends(require_csrf),
    session: Session = Depends(get_db_session),
) -> SearchCriteriaPayload:
    try:
        criteria = SearchCriteria.from_dict(payload.model_dump(mode="python"))
    except ValueError:
        raise _invalid_personal_data() from None
    try:
        saved = SearchCriteriaRepository().save(session, principal.user.id, criteria)
    except (IntegrityError, StaleDataError):
        raise _write_conflict() from None
    return _criteria_response(saved)


@router.patch("/search-criteria", response_model=SearchCriteriaPayload)
def update_search_criteria(
    payload: SearchCriteriaPayload,
    principal: AuthenticatedPrincipal = Depends(require_csrf),
    session: Session = Depends(get_db_session),
) -> SearchCriteriaPayload:
    repository = SearchCriteriaRepository()
    current = repository.get_by_user_id(session, principal.user.id)
    if current is None:
        raise HTTPException(status_code=404, detail="Critérios de busca não encontrados.")
    values = current.to_dict()
    values.update(payload.model_dump(exclude_unset=True, mode="python"))
    try:
        updated = SearchCriteria.from_dict(values)
    except ValueError:
        raise _invalid_personal_data() from None
    try:
        saved = repository.save(session, principal.user.id, updated)
    except (IntegrityError, StaleDataError):
        raise _write_conflict() from None
    return _criteria_response(saved)


@router.delete("/search-criteria", status_code=status.HTTP_204_NO_CONTENT)
def delete_search_criteria(
    principal: AuthenticatedPrincipal = Depends(require_csrf),
    session: Session = Depends(get_db_session),
) -> Response:
    try:
        SearchCriteriaRepository().delete_by_user_id(session, principal.user.id)
    except (IntegrityError, StaleDataError):
        raise _write_conflict() from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/professional-profile", response_model=ProfessionalProfilePayload)
def get_professional_profile(
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> ProfessionalProfilePayload:
    profile = ProfessionalProfileRepository().get_by_user_id(session, principal.user.id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Perfil profissional não encontrado.")
    return _profile_response(profile)


@router.put("/professional-profile", response_model=ProfessionalProfilePayload)
def replace_professional_profile(
    payload: ProfessionalProfilePayload,
    principal: AuthenticatedPrincipal = Depends(require_csrf),
    session: Session = Depends(get_db_session),
) -> ProfessionalProfilePayload:
    try:
        profile = ProfessionalProfile.from_dict(payload.model_dump(mode="python"))
    except ValueError:
        raise _invalid_personal_data() from None
    try:
        saved = ProfessionalProfileRepository().save(session, principal.user.id, profile)
    except (IntegrityError, StaleDataError):
        raise _write_conflict() from None
    return _profile_response(saved)


@router.patch("/professional-profile", response_model=ProfessionalProfilePayload)
def update_professional_profile(
    payload: ProfessionalProfilePayload,
    principal: AuthenticatedPrincipal = Depends(require_csrf),
    session: Session = Depends(get_db_session),
) -> ProfessionalProfilePayload:
    repository = ProfessionalProfileRepository()
    current = repository.get_by_user_id(session, principal.user.id)
    if current is None:
        raise HTTPException(status_code=404, detail="Perfil profissional não encontrado.")
    values = current.to_dict()
    values.update(payload.model_dump(exclude_unset=True, mode="python"))
    try:
        updated = ProfessionalProfile.from_dict(values)
    except ValueError:
        raise _invalid_personal_data() from None
    try:
        saved = repository.save(session, principal.user.id, updated)
    except (IntegrityError, StaleDataError):
        raise _write_conflict() from None
    return _profile_response(saved)


@router.delete("/professional-profile", status_code=status.HTTP_204_NO_CONTENT)
def delete_professional_profile(
    principal: AuthenticatedPrincipal = Depends(require_csrf),
    session: Session = Depends(get_db_session),
) -> Response:
    try:
        ProfessionalProfileRepository().delete_by_user_id(session, principal.user.id)
    except (IntegrityError, StaleDataError):
        raise _write_conflict() from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)
