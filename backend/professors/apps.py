import sys

from django.apps import AppConfig


class ProfessorsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "professors"

    def ready(self):
        # Load MiniLM eagerly at boot (gunicorn only) so the first
        # request doesn't pay the cold-load cost.
        if "gunicorn" in sys.argv[0]:
            try:
                from sentiment.ml import recommender as ml_recommender
                ml_recommender.encoder_available()
            except Exception:
                pass
