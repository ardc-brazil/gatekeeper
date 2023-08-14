from app import create_app

app = create_app()

@app.get("/")
async def root():
    return {"message": "Hello World"}

# if __name__ == '__main__':
#     app.run(host='localhost', port=8080)
