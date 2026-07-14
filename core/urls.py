from django.urls import path
from . import views

app_name = "core"

urlpatterns = [
    path("", views.home, name="home"),
    path("about/", views.about, name="about"),
    path("reviews/add/", views.add_review, name="add_review"),
    path("chat/", views.chat_api, name="chat_api"),
    path("chat/stream/", views.chat_stream_api, name="chat_stream_api"),
]
