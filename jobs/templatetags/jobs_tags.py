from django import template

from jobs.models import Application

register = template.Library()

STATUS_COLORS = {
    Application.Status.SAVED: "secondary",
    Application.Status.INTERVIEW: "info",
    Application.Status.TEST_TASK: "primary",
    Application.Status.OFFER: "warning",
    Application.Status.ACCEPTED: "success",
    Application.Status.REJECTED: "danger",
    Application.Status.WITHDRAWN: "dark",
}


@register.filter
def status_color(status):
    return STATUS_COLORS.get(status, "secondary")
