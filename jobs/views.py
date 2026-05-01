from django.db.models import Q
from django.shortcuts import render, redirect
from django.contrib.auth import login
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from .models import Application
from .services.work_ua import WorkUaParseError
from .services.importer import import_vacancy_from_url
from django.shortcuts import get_object_or_404
from django.http import HttpResponseForbidden
from .forms import ImportVacancyForm, ApplicationForm, \
    VacancyApplicationCreateForm, RegisterForm
from django.core.paginator import Paginator


# Create your views here.


def home(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'jobs/home.html')


@login_required
def dashboard(request):
    query = request.GET.get("q", "").strip()

    applications = (
        Application.objects
        .filter(user=request.user)
        .select_related("vacancy", "vacancy__company")
        .prefetch_related("vacancy__skills")
    )

    if query:
        applications = applications.filter(
            Q(vacancy__title__icontains=query)
            | Q(vacancy__company__name__icontains=query)
            | Q(notes__icontains=query)
        )

    paginator = Paginator(applications, 6)
    page_number = request.GET.get('page')
    applications = paginator.get_page(page_number)

    params = request.GET.copy()
    params.pop("page", None)
    querystring = params.urlencode()

    return render(request, "jobs/dashboard.html", {
        "applications": applications,
        "query": query,
        "querystring": querystring,
    })


@login_required
def import_vacancy(request):
    if request.method == "POST":
        form = ImportVacancyForm(request.POST)
        if form.is_valid():
            url = form.cleaned_data["url"]
            try:
                application = import_vacancy_from_url(url, request.user)
            except WorkUaParseError as e:
                messages.error(request, f"Не вдалося імпортувати: {e}")
            else:
                messages.success(
                    request,
                    f"Вакансія «{application.vacancy.title}» додана!"
                )
                return redirect("dashboard")
    else:
        form = ImportVacancyForm()

    return render(request, "jobs/import.html", {"form": form})


@login_required
def application_create(request):
    if request.method == "POST":
        form = VacancyApplicationCreateForm(request.POST, request.FILES)
        if form.is_valid():
            application, created = form.save(user=request.user)
            if created:
                messages.success(
                    request,
                    f"Вакансію «{application.vacancy.title}» додано."
                )
            else:
                messages.warning(
                    request,
                    "У тебе вже є запис для цієї вакансії."
                )
            return redirect("application_detail", pk=application.pk)
    else:
        form = VacancyApplicationCreateForm()

    return render(request, "jobs/application_create.html", {"form": form})


@login_required
def application_detail(request, pk):
    application = get_object_or_404(Application, pk=pk)

    if application.user != request.user:
        return HttpResponseForbidden("Це не твій запис.")

    return render(request, "jobs/application_detail.html", {
        "application": application,
    })


@login_required
def application_edit(request, pk):
    application = get_object_or_404(Application, pk=pk)

    if application.user != request.user:
        return HttpResponseForbidden("Це не твій запис.")

    if request.method == "POST":
        form = ApplicationForm(request.POST, request.FILES,
                               instance=application)
        if form.is_valid():
            form.save()
            messages.success(request, "Зміни збережено.")
            return redirect("application_detail", pk=application.pk)
    else:
        form = ApplicationForm(instance=application)

    return render(request, "jobs/application_form.html", {
        "form": form,
        "application": application,
    })


@login_required
def application_delete(request, pk):
    application = get_object_or_404(Application, pk=pk)

    if application.user != request.user:
        return HttpResponseForbidden("Це не твій запис.")

    if request.method == "POST":
        vacancy_title = application.vacancy.title
        application.delete()
        messages.success(request, f"Видалено: {vacancy_title}")
        return redirect("dashboard")

    return render(request, "jobs/application_confirm_delete.html", {
        "application": application,
    })


def register(request):
    if request.user.is_authenticated:
        return redirect('home')
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, 'Account created successfully!')
            return redirect('home')
    else:
        form = RegisterForm()
    return render(request, 'registration/register.html', {'form': form})
