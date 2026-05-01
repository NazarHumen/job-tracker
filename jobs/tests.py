from django.db import IntegrityError, transaction
from django.test import TestCase
from django.contrib.auth.models import User
from django.urls import reverse

from .forms import ImportVacancyForm
from .models import Application, Company, Vacancy


class ImportFormTest(TestCase):
    def test_rejects_non_work_ua_url(self):
        form = ImportVacancyForm(data={"url": "https://linkedin.com/jobs/123"})
        self.assertFalse(form.is_valid())

    def test_accepts_valid_work_ua_url(self):
        form = ImportVacancyForm(
            data={"url": "https://www.work.ua/jobs/12345/"})
        self.assertTrue(form.is_valid())


class ApplicationOwnershipTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner", password="pass12345")
        self.intruder = User.objects.create_user(
            username="intruder", password="pass12345")

        company = Company.objects.create(name="Acme")
        vacancy = Vacancy.objects.create(
            source_url="https://www.work.ua/jobs/1/",
            title="Django Dev",
            company=company,
        )
        self.application = Application.objects.create(
            user=self.owner, vacancy=vacancy)

    def test_edit_forbidden_for_non_owner(self):
        self.client.login(username="intruder", password="pass12345")
        response = self.client.get(
            reverse("application_edit", args=[self.application.pk]))
        self.assertEqual(response.status_code, 403)

    def test_edit_post_forbidden_for_non_owner(self):
        self.client.login(username="intruder", password="pass12345")
        response = self.client.post(
            reverse("application_edit", args=[self.application.pk]),
            data={"status": Application.Status.REJECTED, "notes": "hacked"},
        )
        self.assertEqual(response.status_code, 403)
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, Application.Status.SAVED)
        self.assertEqual(self.application.notes, "")

    def test_delete_forbidden_for_non_owner(self):
        self.client.login(username="intruder", password="pass12345")
        response = self.client.post(
            reverse("application_delete", args=[self.application.pk]))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(
            Application.objects.filter(pk=self.application.pk).exists())

    def test_owner_can_access_edit(self):
        self.client.login(username="owner", password="pass12345")
        response = self.client.get(
            reverse("application_edit", args=[self.application.pk]))
        self.assertEqual(response.status_code, 200)


class ApplicationUniqueTogetherTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="alice", password="pass12345")
        company = Company.objects.create(name="Acme")
        self.vacancy = Vacancy.objects.create(
            source_url="https://www.work.ua/jobs/1/",
            title="Django Dev",
            company=company,
        )

    def test_same_user_same_vacancy_raises_integrity_error(self):
        Application.objects.create(user=self.user, vacancy=self.vacancy)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Application.objects.create(
                    user=self.user, vacancy=self.vacancy)

    def test_different_users_can_share_vacancy(self):
        other = User.objects.create_user(username="bob", password="pass12345")
        Application.objects.create(user=self.user, vacancy=self.vacancy)
        Application.objects.create(user=other, vacancy=self.vacancy)
        self.assertEqual(
            Application.objects.filter(vacancy=self.vacancy).count(), 2)
