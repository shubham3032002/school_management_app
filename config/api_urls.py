from django.urls import path, include

urlpatterns = [
    path("auth/", include("apps.accounts.urls")),
    path("", include("apps.profiles.urls")),
    path("", include("apps.academics.urls")),
    path("timetable/", include("apps.timetable.urls")),
    path("attendance/", include("apps.attendance.urls")),
    path("", include("apps.homework.urls")),
    path("", include("apps.exams.urls")),
    path("", include("apps.fees.urls")),
    path("", include("apps.communication.urls")),
    path("reports/", include("apps.reports.urls")),
]
