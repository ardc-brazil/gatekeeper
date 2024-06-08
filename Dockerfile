FROM python:3.10.14-alpine as base

FROM base as builder

RUN mkdir /install
RUN apk update && apk add postgresql-dev gcc python3-dev musl-dev libffi-dev
WORKDIR /install
COPY requirements.txt /requirements.txt
RUN pip install --prefix=/install -r /requirements.txt

FROM base

COPY --from=builder /install /usr/local
COPY . /app
RUN apk --no-cache add libpq
WORKDIR /app
EXPOSE 9092

CMD ["uvicorn", "app.main:fastAPIApp", "--host", "0.0.0.0", "--port", "9092"]
