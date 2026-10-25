from django.urls import path
from . import views
app_name="fees"
urlpatterns=[path("",views.list_fees,name="list"),path("summary/",views.summary,name="summary"),path("structures/",views.structure_list,name="structure_list"),path("structures/new/",views.FeeStructureCreate.as_view(),name="structure_create"),path("structures/<int:pk>/edit/",views.FeeStructureUpdate.as_view(),name="structure_edit"),path("structures/<int:pk>/delete/",views.FeeStructureDelete.as_view(),name="structure_delete"),path("payments/new/",views.PaymentCreate.as_view(),name="payment_create"),path("student/<int:student_id>/",views.student_fees,name="student"),path("receipt/<int:payment_id>/",views.receipt,name="receipt"),path("receipt/<int:payment_id>/pdf/",views.receipt_pdf,name="receipt_pdf")]
