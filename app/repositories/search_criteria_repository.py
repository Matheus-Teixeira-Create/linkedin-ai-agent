"""Persistência de critérios de busca, sempre delimitados por usuário."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import SearchCriteriaORM, SearchCriteriaSkillORM
from app.models.search_criteria import SearchCriteria


class SearchCriteriaRepository:
    """Converte critérios de domínio para registros relacionais e vice-versa."""

    @staticmethod
    def _validate_user_id(user_id: UUID | None) -> None:
        if user_id is None:
            raise ValueError("user_id é obrigatório para persistir critérios.")

    def get_by_user_id(self, session: Session, user_id: UUID) -> SearchCriteria | None:
        self._validate_user_id(user_id)
        row = session.scalar(select(SearchCriteriaORM).where(SearchCriteriaORM.user_id == user_id))
        return self._to_domain(row) if row else None

    def save(self, session: Session, user_id: UUID, criteria: SearchCriteria) -> SearchCriteria:
        self._validate_user_id(user_id)
        if not isinstance(criteria, SearchCriteria):
            raise TypeError("criteria deve ser SearchCriteria.")
        row = session.scalar(select(SearchCriteriaORM).where(SearchCriteriaORM.user_id == user_id))
        if row is None:
            row = SearchCriteriaORM(user_id=user_id)
            session.add(row)
        row.skills.clear()
        row.professional_area = criteria.professional_area
        row.desired_title = criteria.desired_title
        row.work_mode = criteria.work_mode.value if criteria.work_mode else None
        row.location = criteria.location
        row.seniority = criteria.seniority
        row.salary_min = criteria.salary_min
        row.salary_max = criteria.salary_max
        # Exclui os órfãos antes de inserir os novos itens que podem ter os
        # mesmos nomes. O flush continua dentro da transação do chamador.
        session.flush()
        row.skills = [
            SearchCriteriaSkillORM(name=name, position=index)
            for index, name in enumerate(criteria.skills)
        ]
        session.flush()
        return self._to_domain(row)

    def delete_by_user_id(self, session: Session, user_id: UUID) -> bool:
        self._validate_user_id(user_id)
        row = session.scalar(select(SearchCriteriaORM).where(SearchCriteriaORM.user_id == user_id))
        if row is None:
            return False
        session.delete(row)
        session.flush()
        return True

    @staticmethod
    def _to_domain(row: SearchCriteriaORM) -> SearchCriteria:
        return SearchCriteria(
            professional_area=row.professional_area,
            desired_title=row.desired_title,
            work_mode=row.work_mode,
            location=row.location,
            seniority=row.seniority,
            salary_min=row.salary_min,
            salary_max=row.salary_max,
            skills=tuple(skill.name for skill in row.skills),
        )
