from app import create_app
from utils.logger import init_logger, get_logger

init_logger()
logger = get_logger()

app = create_app()

if __name__ == "__main__":
    logger.info("Starting Solid Info API server...")
    app.run(host="0.0.0.0", port=5060, debug=False)
