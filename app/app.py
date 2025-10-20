from flask import Flask
from app.core import blueprint

def create_app(config=None):
    app = Flask(__name__)
    app.register_blueprint(blueprint)
    if config:
        app.config.update(config)
    if not app.logger.handlers:
        import logging
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s - %(message)s")
        )
        app.logger.addHandler(handler)
    app.logger.setLevel('INFO')
    return app

if __name__ == "__main__":
    application = create_app()
    application.run(debug=True)
