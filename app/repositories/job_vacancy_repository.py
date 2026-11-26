"""Persistência de catálogo compartilhado de vagas."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import JobRequirementORM, JobVacancyORM
from app.models.job_vacancy import JobRequirement, JobVacancy


class JobVacancyRepository:
    """Gerencia vagas sem associação de propriedade a um usuário."""

    def create(self, session: Session, vacancy: JobVacancy) -> UUID:
        if not isinstance(vacancy, JobVacancy):
            raise TypeError("vacancy deve ser JobVacancy.")
        row = self._from_domain(vacancy)
        session.add(row)
        session.flush()
        return row.id

    def get_by_id(self, session: Session, vacancy_id: UUID) -> JobVacancy | None:
        row = session.get(JobVacancyORM, vacancy_id)
        return self._to_domain(row) if row else None

    def list_all(self, session: Session) -> tuple[tuple[UUID, JobVacancy], ...]:
        rows = session.scalars(select(JobVacancyORM).order_by(JobVacancyORM.title)).all()
        return tuple((row.id, self._to_domain(row)) for row in rows)

    def delete(self, session: Session, vacancy_id: UUID) -> bool:
        row = session.get(JobVacancyORM, vacancy_id)
        if row is None:
            return False
        session.delete(row)
        session.flush()
        return True

    @staticmethod
    def _from_domain(vacancy: JobVacancy) -> JobVacancyORM:
        return JobVacancyORM(
            title=vacancy.title,
            professional_area=vacancy.professional_area,
            requirements=[
                JobRequirementORM(
                    category=item.category.value,
                    description=item.description,
                    importance=item.importance.value,
                    minimum_proficiency=(
                        item.minimum_proficiency.value if item.minimum_proficiency else None
                    ),
                    minimum_years=item.minimum_years,
                    position=index,
                )
                for index, item in enumerate(vacancy.requirements)
            ],
        )

    @staticmethod
    def _to_domain(row: JobVacancyORM) -> JobVacancy:
        return JobVacancy(
            title=row.title,
            professional_area=row.professional_area,
            requirements=tuple(
                JobRequirement(
                    category=item.category,
                    description=item.description,
                    importance=item.importance,
                    minimum_proficiency=item.minimum_proficiency,
                    minimum_years=item.minimum_years,
                )
                for item in row.requirements
            ),
        )
