import sys
import threading

from django.apps import AppConfig


class ProfessorsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "professors"

    def ready(self):
        # Warm MiniLM in the background at boot (gunicorn only), delayed
        # a few seconds so it doesn't compete with the first request.
        if "gunicorn" in sys.argv[0]:
            def _warm_encoder():
                try:
                    from sentiment.ml import recommender as ml_recommender
                    ml_recommender.encoder_available()
                except Exception:
                    pass
            # Wait a few seconds so this doesn't compete with the first
            # request a fresh instance receives.
            threading.Timer(5.0, _warm_encoder).start()
