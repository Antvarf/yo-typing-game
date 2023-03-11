from rest_framework import permissions, routers
from drf_yasg.views import get_schema_view
from drf_yasg import openapi

from . import views


# schema_view = get_schema_view(
#     openapi.Info(
#         title="Ё api",
#         default_version="v1",
#         description="SOME VERY NICE AND POLITE DESCRIPTION",
#         contact=openapi.Contact(email="warrior@typewars.ru"),
#         ),
#     public=True,
#     permission_classes=(permissions.AllowAny,),
#     )
app_name = 'yo_game'
router = routers.SimpleRouter()
router.register(r'players', views.PlayerViewSet)
urlpatterns = router.urls
