import sys
import threading

from django.apps import AppConfig


class ProfessorsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "professors"

    def ready(self):
        # Warm MiniLM in the background at boot (gunicorn only) so it
        # doesn't block worker startup or other requests.
        if "gunicorn" in sys.argv[0]:
            def _warm_encoder():
                try:
                    from sentiment.ml import recommender as ml_recommender
                    ml_recommender.encoder_available()
                except Exception:
                    pass
            threading.Thread(
                target=_warm_encoder, daemon=True, name="warm-minilm-encoder",
            ).start()
