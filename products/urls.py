from django.urls import path
from whatmobile import scrape_views as whatmobile_scrape_views

from . import views, scrape_views

app_name = "products"

urlpatterns = [
    path("", views.product_list, name="list"),
    path("compare/", views.compare, name="compare"),
    path("compare/results/", views.compare_results, name="compare_results"),
    path("scrape/", scrape_views.scrape_page, name="scrape"),
    path("scrape/start/", scrape_views.scrape_start, name="scrape_start"),
    path("scrape/progress/", scrape_views.scrape_progress, name="scrape_progress"),
    path("scrape/whatmobile/start/", whatmobile_scrape_views.whatmobile_scrape_start, name="whatmobile_scrape_start"),
    path("scrape/whatmobile/progress/", whatmobile_scrape_views.whatmobile_scrape_progress, name="whatmobile_scrape_progress"),
    path("favorites/", views.favorites_list, name="favorites"),
    path("<int:product_id>/favorite/", views.toggle_favorite, name="toggle_favorite"),
    path("<int:product_id>/notify/", views.toggle_price_alert, name="toggle_price_alert"),
    path("<slug:slug>/", views.product_detail, name="detail"),
]
