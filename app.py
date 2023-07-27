from app import create_app

# app = create_app()

if __name__ == '__main__':
    # app.run(host='localhost', port=8000)
    create_app = create_app()
    create_app.run()
else:
    gunicorn_app = create_app()
