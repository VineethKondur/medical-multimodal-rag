from django.urls import path
from .views import upload_and_index, query_document, ui

urlpatterns = [
    path("", ui, name="ui"),
    path("api/upload/", upload_and_index, name="upload_api"),
    path("api/query/", query_document, name="query_api"),
]