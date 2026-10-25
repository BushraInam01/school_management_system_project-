from django.urls import path
from . import views
app_name="timetable"
urlpatterns=[path("",views.grid,name="grid"),path("slots/",views.SlotList.as_view(),name="slot_list"),path("slots/new/",views.TimeSlotCreate.as_view(),name="slot_create"),path("slots/<int:pk>/edit/",views.TimeSlotUpdate.as_view(),name="slot_update"),path("slots/<int:pk>/delete/",views.TimeSlotDelete.as_view(),name="slot_delete"),path("entries/",views.EntryList.as_view(),name="entry_list"),path("entries/new/",views.EntryCreate.as_view(),name="entry_create"),path("entries/<int:pk>/edit/",views.EntryUpdate.as_view(),name="entry_update"),path("entries/<int:pk>/delete/",views.EntryDelete.as_view(),name="entry_delete")]
