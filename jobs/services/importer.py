from django.db import transaction
from django.contrib.auth.models import User
from jobs.models import Company, Skill, Vacancy, Application
from jobs.services.work_ua import WorkUaParser


@transaction.atomic
def import_vacancy_from_url(url: str, user: User) -> Application:
    """
    Парсить вакансію з work.ua і створює всі потрібні записи:
    Company → Skill → Vacancy → Application.

    Returns: Application що було створено (або вже існувало).
    """
    parser = WorkUaParser()
    data = parser.parse_vacancy(url)

    company, _ = Company.objects.get_or_create(
        name=data.company_name,
        defaults={"work_ua_url": data.company_url},
    )

    skills = []
    for skill_name in data.skills:
        skill, _ = Skill.objects.get_or_create(name=skill_name)
        skills.append(skill)

    vacancy, vacancy_created = Vacancy.objects.get_or_create(
        source_url=data.source_url,
        defaults={
            "title": data.title,
            "company": company,
            "location": data.location,
            "hr_name": data.hr_name,
            "phone": data.phone,
            "salary_text": data.salary_text,
            "description_text": data.description_text,
        },
    )
    if vacancy_created:
        vacancy.skills.set(skills)

    application, _ = Application.objects.get_or_create(
        user=user,
        vacancy=vacancy,
        defaults={"status": Application.Status.SAVED},
    )
    return application
