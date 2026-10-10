from django.urls import path

from . import orders_api, views

app_name = "exchange"

urlpatterns = [
    path("ping/", views.PingView.as_view(), name="ping"),
    path("catalog/", views.CatalogUploadView.as_view(), name="catalog"),
    path("products/<uuid:ext_id>/image/", views.ProductImageView.as_view(), name="product_image"),
    path("orders/new/", orders_api.NewOrdersView.as_view(), name="orders_new"),
    path("orders/ack/", orders_api.OrdersAckView.as_view(), name="orders_ack"),
    path("orders/status/", orders_api.OrdersStatusView.as_view(), name="orders_status"),
    path("leads/new/", orders_api.NewLeadsView.as_view(), name="leads_new"),
    path("leads/ack/", orders_api.LeadsAckView.as_view(), name="leads_ack"),
    path("leads/<int:pk>/file/", orders_api.LeadFileView.as_view(), name="lead_file"),
]
