from django.db import models
from django.contrib.auth.models import User
from django.core.validators import FileExtensionValidator


def user_cv_upload_path(instance, filename):
    return f"cv_resumes/user_{instance.user_id}/{filename}"


class Company(models.Model):
    name = models.CharField(max_length=255, unique=True)
    work_ua_url = models.URLField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Skill(models.Model):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Vacancy(models.Model):
    source_url = models.URLField(unique=True)
    title = models.CharField(max_length=255)
    company = models.ForeignKey(Company, on_delete=models.CASCADE,
                                related_name='vacancies')
    location = models.CharField(max_length=255, blank=True)
    hr_name = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=50, blank=True)
    salary_text = models.CharField(max_length=100, blank=True)
    description_text = models.TextField(blank=True)
    skills = models.ManyToManyField(Skill, related_name='vacancies',
                                    blank=True)
    parsed_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-parsed_at']

    def __str__(self):
        return f"{self.title} - {self.company.name}"


class Application(models.Model):
    class Status(models.TextChoices):
        SAVED = "saved", "Збережено"
        INTERVIEW = "interview", "Технічна співбесіда"
        TEST_TASK = "test_task", "Тестове завдання"
        OFFER = "offer", "Отримано оффер"
        ACCEPTED = "accepted", "Прийняв оффер"
        REJECTED = "rejected", "Відмова"
        WITHDRAWN = "withdrawn", "Сам відкликав"

    user = models.ForeignKey(User, on_delete=models.CASCADE,
                             related_name='applications')
    vacancy = models.ForeignKey(Vacancy, on_delete=models.CASCADE,
                                related_name='applications')
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.SAVED,
    )
    applied_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    notes = models.TextField(blank=True)
    cv_file = models.FileField(
        upload_to=user_cv_upload_path,
        blank=True,
        null=True,
        validators=[FileExtensionValidator(allowed_extensions=["pdf"])],
    )

    class Meta:
        ordering = ['-updated_at']
        unique_together = ['user', 'vacancy']

    def __str__(self):
        return f"{self.user.username} - {self.vacancy.title} ({self.get_status_display()})"
