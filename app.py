from src import config, app
import logging

if __name__ == "__main__":
    if config.ENV == "production":
        from waitress import serve
        logging.basicConfig(level=logging.DEBUG, format='[%(asctime)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M')
        serve(app, host=config.HOST, port=config.PORT)
    else:
        app.run(host=config.HOST,
                port=config.PORT,
                debug=config.DEBUG)