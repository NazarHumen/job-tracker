from urllib.parse import urlparse
from uuid import uuid4

from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User
from django.db import transaction

from .models import Application, Company, Skill, Vacancy


def validate_cv_size(cv_file):
    MAX_CV_SIZE = 5 * 1024 * 1024
    if cv_file and hasattr(cv_file, "size") and cv_file.size > MAX_CV_SIZE:
        raise forms.ValidationError("Файл занадто великий (макс. 5 МБ).")
    return cv_file


class ApplicationForm(forms.ModelForm):
    class Meta:
        model = Application
        fields = ["status", "notes", "cv_file"]
        widgets = {
            "status": forms.Select(attrs={"class": "form-select"}),
            "notes": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 5,
                "placeholder": "Особисті нотатки про цю вакансію...",
            }),
            "cv_file": forms.ClearableFileInput(attrs={
                "class": "form-control",
                "accept": "application/pdf",
            }),
        }
        labels = {
            "status": "Статус",
            "notes": "Нотатки",
            "cv_file": "Завантажити резюме (PDF)",
        }
        help_texts = {
            "cv_file": "Тільки PDF, до 5 МБ",
        }

    def clean_cv_file(self):
        return validate_cv_size(self.cleaned_data.get("cv_file"))


class VacancyApplicationCreateForm(forms.Form):
    title = forms.CharField(
        max_length=255,
        label="Назва вакансії",
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Python Developer",
            "autofocus": True,
        }),
    )
    company_name = forms.CharField(
        max_length=255,
        label="Компанія",
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Acme Corp",
        }),
    )
    source_url = forms.URLField(
        required=False,
        label="Посилання на вакансію",
        widget=forms.URLInput(attrs={
            "class": "form-control",
            "placeholder": "https://...",
        }),
        help_text="Якщо є — посилання на оголошення (LinkedIn, Djinni тощо).",
    )
    location = forms.CharField(
        max_length=255,
        required=False,
        label="Локація",
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    salary_text = forms.CharField(
        max_length=100,
        required=False,
        label="Зарплата",
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "$2000",
        }),
    )
    description_text = forms.CharField(
        required=False,
        label="Опис",
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 5}),
    )
    skills = forms.CharField(
        required=False,
        label="Скіли",
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Python, Django, REST",
        }),
        help_text="Через кому.",
    )
    status = forms.ChoiceField(
        choices=Application.Status.choices,
        initial=Application.Status.SAVED,
        label="Статус",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    notes = forms.CharField(
        required=False,
        label="Нотатки",
        widget=forms.Textarea(attrs={
            "class": "form-control",
            "rows": 3,
            "placeholder": "Особисті нотатки про цю вакансію...",
        }),
    )
    cv_file = forms.FileField(
        required=False,
        label="Завантажити резюме (PDF)",
        widget=forms.ClearableFileInput(attrs={
            "class": "form-control",
            "accept": "application/pdf",
        }),
        help_text="Тільки PDF, до 5 МБ.",
    )

    def clean_skills(self):
        raw = self.cleaned_data.get("skills", "")
        return [s.strip() for s in raw.split(",") if s.strip()]

    def clean_cv_file(self):
        cv_file = validate_cv_size(self.cleaned_data.get("cv_file"))
        if cv_file and not cv_file.name.lower().endswith(".pdf"):
            raise forms.ValidationError("Дозволено лише PDF.")
        return cv_file

    @transaction.atomic
    def save(self, user) -> tuple[Application, bool]:
        """
        Створює Company → Vacancy → Skills → Application у транзакції.
        Returns (application, application_was_created).
        """
        data = self.cleaned_data

        company, _ = Company.objects.get_or_create(name=data["company_name"])

        source_url = data.get("source_url") or f"manual://{uuid4().hex}"

        vacancy, vacancy_created = Vacancy.objects.get_or_create(
            source_url=source_url,
            defaults={
                "title": data["title"],
                "company": company,
                "location": data.get("location", ""),
                "salary_text": data.get("salary_text", ""),
                "description_text": data.get("description_text", ""),
            },
        )
        if vacancy_created and data.get("skills"):
            skill_objects = []
            for name in data["skills"]:
                skill, _ = Skill.objects.get_or_create(name=name)
                skill_objects.append(skill)
            vacancy.skills.set(skill_objects)

        application, app_created = Application.objects.get_or_create(
            user=user,
            vacancy=vacancy,
            defaults={
                "status": data["status"],
                "notes": data.get("notes", ""),
                "cv_file": data.get("cv_file"),
            },
        )
        return application, app_created


class ImportVacancyForm(forms.Form):
    url = forms.URLField(
        label="Посилання на вакансію",
        widget=forms.URLInput(attrs={
            "placeholder": "https://www.work.ua/jobs/1234567/",
            "class": "form-control form-control-lg",
            "autofocus": True,
        }),
        help_text="Встав посилання на вакансію з work.ua",
    )

    def clean_url(self) -> str:
        url = self.cleaned_data["url"]
        parsed = urlparse(url)

        if parsed.netloc not in ("work.ua", "www.work.ua"):
            raise forms.ValidationError(
                "Підтримуються лише посилання з work.ua"
            )

        if "/jobs/" not in parsed.path:
            raise forms.ValidationError(
                "Це не схоже на посилання на вакансію. "
                "URL має містити /jobs/<номер>/"
            )

        return url

class RegisterForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'


class LoginForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'
