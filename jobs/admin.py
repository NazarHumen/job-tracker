from django.contrib import admin
from .models import Company, Skill, Vacancy, Application


# Register your models here.


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_at')

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "Companies"


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "Skills"


@admin.register(Vacancy)
class VacancyAdmin(admin.ModelAdmin):
    list_display = ('title', 'company', 'location', 'salary_text', 'is_active',
                    'parsed_at')
    list_filter = ('is_active', 'company')
    search_fields = ('title', 'company__name')
    filter_horizontal = ('skills',)

    class Meta:
        ordering = ["-parsed_at"]
        verbose_name_plural = "Vacancies"


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ('user', 'vacancy', 'status', 'applied_at', 'updated_at')
    list_filter = ('status', 'user')
    search_fields = ('vacancy__title', 'user__username',)

    class Meta:
        ordering = ["-updated_at"]
        verbose_name_plural = "Applications"
