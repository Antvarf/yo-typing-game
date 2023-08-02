from rest_framework import routers

from . import views

app_name = 'yo_game'

router = routers.SimpleRouter()
router.register(r'players', views.PlayerViewSet)
router.register(r'sessions', views.SessionViewSet)
urlpatterns = router.urls
